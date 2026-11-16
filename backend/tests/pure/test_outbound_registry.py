"""Every request that leaves the network is in the registry About's privacy list is held to.

Reviews of "What leaves your network" kept finding requests nobody had listed.
This guard makes an unlisted one fail here instead. It reads the syntax tree of
every module in `backend/app` and holds what it finds to
`backend/outbound_requests.json`:

- **Dependencies.** Every package in `backend/requirements-*.txt` is classified
  in the registry as able to talk to another machine or not, so a new SDK
  cannot arrive unclassified.
- **Imports.** A module that imports an outbound library, under any name
  (`import x as y`, `from x import y`, `from urllib import request`), is
  registered: under the entries it sends for, as a client of an address the
  owner enters, or as sending nothing, with the reason.
- **Borrowed clients.** A module that sends through a client another module
  made (`from app.services.x import http_client`, or `service.client.get(...)`)
  is registered under an entry.
- **Helpers.** A module that calls a helper which downloads or deletes on its
  own (`ensure_model`, `download_model`, `forget_installation`) is registered
  under an entry.
- **Hosts.** An outside host written in the code belongs to an entry, or is
  listed as not contacted, with the reason.

What it cannot see is recorded in the registry's `manual_review`, and tested
here to be there.
"""

import ast
import json
from pathlib import Path
import re

BACKEND = Path(__file__).resolve().parents[2]
APP = BACKEND / "app"
REGISTRY = json.loads((BACKEND / "outbound_requests.json").read_text("utf-8"))
ENTRIES = REGISTRY["entries"]
GROUPS = {"server", "browser", "on_demand"}

# Helpers that send a request themselves when called, without the caller holding a client.
OUTBOUND_HELPERS = frozenset({"ensure_model", "download_model", "forget_installation"})
# asyncio's own ways of opening a connection, which need no client library.
NETWORK_CALLS = frozenset(REGISTRY["network_calls"])
DYNAMIC_IMPORTS = frozenset({"importlib.import_module", "__import__"})
_HOST = re.compile(r"https?://([A-Za-z0-9.-]+\.[a-z]{2,})")


def _outbound_roots(registry: dict = REGISTRY) -> frozenset[str]:
    """The dotted names an outbound library is imported under."""
    packaged = {name for package in registry["dependencies"]["outbound"] for name in package["imports"]}
    return frozenset(packaged | set(registry["other_outbound_imports"]))


def _is_under(origin: str, roots: frozenset[str]) -> bool:
    return any(origin == root or origin.startswith(root + ".") for root in roots)


class ModuleFacts(ast.NodeVisitor):
    """What one module's syntax tree says about sending requests."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.package = name.rsplit(".", 1)[0]
        # Local name -> the dotted thing it stands for: "request" -> "urllib.request".
        self.bound: dict[str, str] = {}
        self.hosts: set[str] = set()
        self.helper_calls: set[str] = set()
        # Names this module binds to a client it builds: `http_client = httpx.AsyncClient()`.
        self.module_clients: set[str] = set()
        # Attributes its objects hold a client under: `self.client = httpx.AsyncClient()`.
        self.attribute_clients: set[str] = set()
        # Every attribute chain that starts at an imported name, resolved to where it leads:
        # `notifications.notification_service.client.get` ->
        # "app.services.notification_service.notification_service.client.get".
        self.chains: set[str] = set()
        # Calls that open a connection whatever object they are made on.
        self.network_calls: set[str] = set()
        # An import whose module name is computed, so its target cannot be read here.
        self.imports_by_computed_name = False
        self._depth = 0

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            # `import a.b` binds `a`; `import a.b as c` binds `c` to `a.b`.
            self.bound[alias.asname or alias.name.split(".")[0]] = (
                alias.name if alias.asname else alias.name.split(".")[0]
            )
            if not alias.asname:
                self.bound[alias.name] = alias.name

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        base = node.module or ""
        if node.level:
            parent = self.name.rsplit(".", node.level)[0]
            base = f"{parent}.{base}" if base else parent
        for alias in node.names:
            self.bound[alias.asname or alias.name] = f"{base}.{alias.name}"

    def _origin(self, node: ast.AST) -> str | None:
        """The dotted origin of `name.a.b`, when `name` was imported."""
        parts: list[str] = []
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if isinstance(node, ast.Name) and node.id in self.bound:
            return ".".join([self.bound[node.id], *reversed(parts)])
        return None

    def _builds_a_client(self, value: ast.AST, roots: frozenset[str]) -> bool:
        return isinstance(value, ast.Call) and _is_under(self._origin(value.func) or "", roots)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._depth += 1
        self.generic_visit(node)
        self._depth -= 1

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Assign(self, node: ast.Assign) -> None:
        self._record_assignment(node.targets, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self._record_assignment([node.target], node.value)
        self.generic_visit(node)

    def _record_assignment(self, targets: list[ast.expr], value: ast.AST) -> None:
        if not self._builds_a_client(value, self.roots):
            return
        for target in targets:
            if isinstance(target, ast.Name) and self._depth == 0:
                self.module_clients.add(target.id)
            elif isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self":
                self.attribute_clients.add(target.attr)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        origin = self._origin(node)
        if origin:
            self.chains.add(origin)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        called = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", None)
        origin = self._origin(node.func) or (
            self.bound.get(called, called) if isinstance(node.func, ast.Name) else None
        )
        if called in OUTBOUND_HELPERS:
            self.helper_calls.add(called)
        # `asyncio.open_connection(...)`, `loop.create_connection(...)`: the loop is not an import,
        # so these are matched by the name of the call.
        if called in NETWORK_CALLS:
            self.network_calls.add(called)
        if origin in DYNAMIC_IMPORTS:
            target = node.args[0] if node.args else None
            if isinstance(target, ast.Constant) and isinstance(target.value, str):
                # A name written out is an import like any other.
                self.bound[f"<imported by name: {target.value}>"] = target.value
            else:
                self.imports_by_computed_name = True
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str):
            self.hosts.update(_HOST.findall(node.value))

    roots: frozenset[str] = frozenset()

    def imports_an_outbound_library(self) -> bool:
        return bool(self.network_calls) or any(_is_under(origin, self.roots) for origin in self.bound.values())


def _module_name(path: str) -> str:
    return path.removesuffix(".py").removesuffix("/__init__").replace("/", ".")


def analyse(sources: dict[str, str], registry: dict = REGISTRY) -> dict[str, ModuleFacts]:
    """Each module's facts, keyed by its path under `backend/`."""
    roots = _outbound_roots(registry)
    facts: dict[str, ModuleFacts] = {}
    for path, source in sources.items():
        module = ModuleFacts(_module_name(path))
        module.roots = roots
        module.visit(ast.parse(source, filename=path))
        facts[path] = module
    return facts


def _resolve(origin: str, by_name: dict[str, ModuleFacts], hops: int = 6) -> tuple[ModuleFacts, list[str]] | None:
    """The app module a dotted origin leads into, and the attributes read from it.

    `app.services.x.service.client.get` is module `app.services.x` and `["service", "client",
    "get"]`. A name the module only re-exports is followed to the module that defines it.
    """
    parts = origin.split(".")
    for cut in range(len(parts), 0, -1):
        owner = by_name.get(".".join(parts[:cut]))
        if owner is None:
            continue
        rest = parts[cut:]
        if rest and rest[0] in owner.bound and hops > 0:
            onward = _resolve(".".join([owner.bound[rest[0]], *rest[1:]]), by_name, hops - 1)
            if onward is not None and onward[0] is not owner:
                return onward
        return owner, rest
    return None


def borrows_a_client(module: ModuleFacts, facts: dict[str, ModuleFacts]) -> bool:
    """Whether the module reaches a client that another app module built, however it gets there.

    By name (`from x import http_client`), through a re-export, through a module alias, or through
    a service object that holds one (`module.service.client.get(...)`): every imported name and
    every attribute chain is resolved to the module it leads into, and that module's clients are
    looked for along the way.
    """
    by_name = {other.name: other for other in facts.values()}
    for origin in set(module.bound.values()) | module.chains:
        resolved = _resolve(origin, by_name)
        if resolved is None:
            continue
        owner, attributes = resolved
        if owner is module or not attributes:
            continue
        if attributes[0] in owner.module_clients or any(name in owner.attribute_clients for name in attributes[1:]):
            return True
    return False


def _sender_modules(registry: dict) -> set[str]:
    """Modules registered as making requests themselves: for an entry, or to an address the owner enters."""
    return _entry_modules(registry) | {item["module"] for item in registry["owner_addresses"]}


def callers_of_senders(facts: dict[str, ModuleFacts], registry: dict) -> dict[str, list[str]]:
    """Each module that reaches into a registered sender, and the senders it reaches.

    A registered sender's functions are requests waiting to be called: `weather_service.fetch()`
    from a new module sends the feeder's coordinates as surely as an HTTP client would. Every
    import and attribute chain is resolved, through aliases and re-exports, to the sender it
    leads into.
    """
    by_name = {module.name: module for module in facts.values()}
    path_of = {module.name: path for path, module in facts.items()}
    senders = _sender_modules(registry)
    reached: dict[str, list[str]] = {}
    for path, module in facts.items():
        used: set[str] = set()
        for origin in set(module.bound.values()) | module.chains:
            parts = origin.split(".")
            # The module named on the way, and the one a re-export leads on to.
            direct = next(
                (".".join(parts[:cut]) for cut in range(len(parts), 0, -1) if ".".join(parts[:cut]) in by_name), None
            )
            resolved = _resolve(origin, by_name)
            for name in {direct, resolved[0].name if resolved else None}:
                if name and name != module.name and path_of[name] in senders:
                    used.add(path_of[name])
        if used:
            reached[path] = sorted(used)
    return reached


def unreviewed_callers(facts: dict[str, ModuleFacts], registry: dict) -> list[str]:
    """Caller and sender pairs nobody has reviewed: `caller -> sender`."""
    reviewed = registry["reviewed_callers"]["callers"]
    senders = _sender_modules(registry)
    return sorted(
        f"{caller} -> {sender}"
        for caller, reached in callers_of_senders(facts, registry).items()
        # A sender calling another sender is already a registered place to look.
        if caller not in senders
        for sender in reached
        if sender not in reviewed.get(caller, [])
    )


def able_to_send(facts: dict[str, ModuleFacts]) -> set[str]:
    return {path for path, module in facts.items() if module.imports_an_outbound_library()}


def sending_through_others(facts: dict[str, ModuleFacts]) -> set[str]:
    return {path for path, module in facts.items() if module.helper_calls or borrows_a_client(module, facts)}


def _sources() -> dict[str, str]:
    return {path.relative_to(BACKEND).as_posix(): path.read_text("utf-8") for path in sorted(APP.rglob("*.py"))}


def _entry_modules(registry: dict = REGISTRY) -> set[str]:
    return {module for entry in registry["entries"] for module in entry["modules"]}


def _registered_modules(registry: dict = REGISTRY) -> set[str]:
    return (
        _entry_modules(registry)
        | {item["module"] for item in registry["owner_addresses"]}
        | {item["module"] for item in registry["no_request"]}
    )


def unregistered(sources: dict[str, str], registry: dict = REGISTRY) -> dict[str, list[str]]:
    """Everything in the sources that the registry does not account for; empty when it holds."""
    facts = analyse(sources, registry)
    known_hosts = {host for entry in registry["entries"] for host in entry["hosts"]}
    known_hosts |= {item["host"] for item in registry["hosts_not_contacted"]}
    written = {host for module in facts.values() for host in module.hosts}
    return {
        "modules that import an outbound library": sorted(able_to_send(facts) - _registered_modules(registry)),
        "modules that send through another module's client or helper": sorted(
            sending_through_others(facts)
            - _entry_modules(registry)
            - {i["module"] for i in registry["owner_addresses"]}
        ),
        "modules that import by a computed name": sorted(
            {path for path, module in facts.items() if module.imports_by_computed_name}
            - {item["module"] for item in registry["dynamic_imports"]}
        ),
        "callers of a registered sender that nobody reviewed": unreviewed_callers(facts, registry),
        "hosts": sorted(written - known_hosts),
    }


FIX = (
    "Not in backend/outbound_requests.json. List each module under the entry it sends for (and add the row to "
    "About, with its wording in every locale), under owner_addresses, or under no_request with the reason."
)


def test_the_backend_sends_nothing_the_registry_does_not_list():
    assert unregistered(_sources()) == {
        "modules that import an outbound library": [],
        "modules that send through another module's client or helper": [],
        "modules that import by a computed name": [],
        "callers of a registered sender that nobody reviewed": [],
        "hosts": [],
    }, FIX


def _requirements() -> set[str]:
    packages: set[str] = set()
    for path in sorted(BACKEND.glob("requirements*.txt")):
        for line in path.read_text("utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if not line or line.startswith("-"):
                continue
            packages.add(re.split(r"[<>=!~;\[\s]", line, maxsplit=1)[0])
    return packages


_PIP = re.compile(r"\b(?:uv\s+)?pip3?\s+(?:install|wheel)\b(.*)")
_TAKES_A_VALUE = frozenset(
    "-r --requirement -c --constraint -f --find-links -i --index-url --extra-index-url -t --target "
    "-w --wheel-dir --prefix --root --python --platform --abi --implementation --python-version".split()
)


def _package_name(requirement: str) -> str:
    return re.split(r"[<>=!~;\[\s@]", requirement.strip().strip("'\""), maxsplit=1)[0]


def dockerfile_packages(text: str) -> set[str]:
    """Packages a Dockerfile names on a `pip install` or `pip wheel` line, beside its requirement files."""
    packages: set[str] = set()
    for line in re.sub(r"\\\s*\n", " ", text).splitlines():
        for command in re.split(r"&&|\|\||;", line):
            found = _PIP.search(command)
            if not found:
                continue
            skip = False
            for token in found.group(1).split():
                if skip:
                    skip = False
                elif token in _TAKES_A_VALUE:
                    skip = True
                elif not token.startswith("-") and "$" not in token and "/" not in token:
                    packages.add(_package_name(token))
    return packages - {""}


def pyproject_packages(text: str) -> set[str]:
    """Packages a pyproject.toml declares, under any of the tables an installer reads."""
    import tomllib

    data = tomllib.loads(text)
    project = data.get("project", {})
    listed: list[str] = list(project.get("dependencies", []))
    for group in project.get("optional-dependencies", {}).values():
        listed += group
    for group in data.get("dependency-groups", {}).values():
        listed += [item for item in group if isinstance(item, str)]
    poetry = data.get("tool", {}).get("poetry", {})
    named = set(poetry.get("dependencies", {})) | set(poetry.get("dev-dependencies", {}))
    for group in poetry.get("group", {}).values():
        named |= set(group.get("dependencies", {}))
    listed += list(data.get("tool", {}).get("uv", {}).get("dev-dependencies", []))
    return ({_package_name(item) for item in listed} | named) - {"python", ""}


def declared_packages() -> set[str]:
    """Every package named anywhere the images or an installer would take one from."""
    repository = BACKEND.parent
    packages = _requirements()
    for dockerfile in [
        *repository.glob("Dockerfile*"),
        *repository.glob("*/Dockerfile*"),
        *repository.glob("docker/**/Dockerfile*"),
    ]:
        packages |= dockerfile_packages(dockerfile.read_text("utf-8"))
    for pyproject in [repository / "pyproject.toml", BACKEND / "pyproject.toml"]:
        if pyproject.is_file():
            packages |= pyproject_packages(pyproject.read_text("utf-8"))
    return packages


def test_every_dependency_is_classified_as_outbound_or_not():
    dependencies = REGISTRY["dependencies"]
    outbound = [package["package"] for package in dependencies["outbound"]]
    not_outbound = [package["package"] for package in dependencies["not_outbound"]]
    classified = outbound + not_outbound

    assert len(classified) == len(set(classified)), "a package is classified twice"
    assert sorted(_requirements() - set(classified)) == [], (
        "New dependencies. Classify each in backend/outbound_requests.json: under dependencies.outbound with the "
        "names it is imported under if it can talk to another machine, else under not_outbound with the reason."
    )
    assert sorted(set(classified) - _requirements()) == [], (
        "the registry classifies a package that is no longer required"
    )
    assert all(package["imports"] and package["what"].strip() for package in dependencies["outbound"])
    assert all(package["reason"].strip() for package in dependencies["not_outbound"])


def test_the_registry_lists_nothing_that_is_no_longer_there():
    sources = _sources()
    facts = analyse(sources)
    written = {host for module in facts.values() for host in module.hosts}
    sending = able_to_send(facts) | sending_through_others(facts)

    assert sorted(_registered_modules() - set(sources)) == [], "a registered module no longer exists"
    assert sorted(_registered_modules() - sending) == [], "a registered module can no longer send a request"
    assert sorted({item["host"] for item in REGISTRY["hosts_not_contacted"]} - written) == []
    backend_hosts = {host for entry in ENTRIES if entry["group"] != "browser" for host in entry["hosts"]}
    assert sorted(backend_hosts - written) == [], "an entry names a host the code no longer mentions"


def test_each_entry_is_complete_and_named_once():
    keys = [entry["key"] for entry in ENTRIES]

    assert len(keys) == len(set(keys))
    for entry in ENTRIES:
        assert entry["group"] in GROUPS, entry["key"]
        assert entry["what"].strip(), entry["key"]
        # A server or on-demand request is made by code here; a browser request is made by the SPA.
        assert bool(entry["modules"]) == (entry["group"] != "browser"), entry["key"]
    for item in REGISTRY["no_request"] + REGISTRY["hosts_not_contacted"]:
        assert item["reason"].strip()
    assert all(item["service"].strip() for item in REGISTRY["owner_addresses"])


def test_what_the_guard_cannot_see_is_written_down_for_reviewers():
    notes = " ".join(REGISTRY["manual_review"])

    assert "already registered" in notes and "not written as a literal" in notes
    assert "subprocess" in notes
    assert "What a request carries" in notes


# ---- The guard itself, on the additions it has to catch -------------------------------------------


def _with(new_modules: dict[str, str], registry: dict = REGISTRY) -> dict[str, list[str]]:
    """The real backend plus new modules, as the guard would see them on a branch that adds them."""
    return unregistered({**_sources(), **new_modules}, registry)


def test_it_catches_the_standard_library_imported_piece_by_piece():
    found = _with(
        {
            "app/services/new_fetcher.py": (
                "from urllib import request\n\n\n"
                "def fetch():\n    return request.urlopen('https://api.inaturalist.org/v1/taxa')\n"
            )
        }
    )
    assert found["modules that import an outbound library"] == ["app/services/new_fetcher.py"]


def test_it_catches_a_library_imported_under_another_name():
    for source in (
        "import httpx as web\n",
        "from httpx import AsyncClient as Client\n",
        "import urllib.request\n",
        "from . import sibling\nimport http.client\n",
        "def late():\n    import aiosmtplib\n",
    ):
        assert _with({"app/services/renamed.py": source})["modules that import an outbound library"] == [
            "app/services/renamed.py"
        ], source


def test_it_catches_a_downloader_that_borrows_another_modules_client():
    borrowed_by_name = (
        "from app.services.garden_notification_transport import http_client\n\n\n"
        "async def download(url):\n    return await http_client.get(url)\n"
    )
    held_by_an_object = (
        "from app.services.notification_service import notification_service\n\n\n"
        "async def download(url):\n    return await notification_service.client.get(url)\n"
    )
    through_the_module = (
        "import app.services.garden_notification_transport as transport\n\n\n"
        "async def download(url):\n    return await transport.http_client.get(url)\n"
    )
    for source in (borrowed_by_name, held_by_an_object, through_the_module):
        found = _with({"app/services/new_downloader.py": source})
        assert found["modules that send through another module's client or helper"] == [
            "app/services/new_downloader.py"
        ], source
        # It imports no outbound library of its own, which is why the import rule alone missed it.
        assert found["modules that import an outbound library"] == []


def test_an_ordinary_use_of_a_service_is_a_caller_to_review_not_a_borrowed_client():
    ordinary = (
        "from app.services.notification_service import notification_service\n\n\n"
        "async def announce():\n    return await notification_service.send_detection()\n"
    )
    assert _with({"app/services/announcer.py": ordinary}) == {
        "modules that import an outbound library": [],
        "modules that send through another module's client or helper": [],
        "modules that import by a computed name": [],
        "callers of a registered sender that nobody reviewed": [
            "app/services/announcer.py -> app/services/notification_service.py"
        ],
        "hosts": [],
    }


def test_it_catches_a_new_sdk_because_its_dependency_must_be_classified_first():
    caller = "import cohere\n\n\ndef ask(prompt):\n    return cohere.Client().chat(message=prompt)\n"
    # Unclassified, the import says nothing yet: the dependency test is what fails (below).
    assert "cohere" not in {name for package in REGISTRY["dependencies"]["outbound"] for name in package["imports"]}
    # Once classified as outbound, its caller has to be registered like any other.
    classified = json.loads(json.dumps(REGISTRY))
    classified["dependencies"]["outbound"].append({"package": "cohere", "imports": ["cohere"], "what": "LLM SDK"})
    assert _with({"app/services/new_llm.py": caller}, classified)["modules that import an outbound library"] == [
        "app/services/new_llm.py"
    ]


def test_an_unclassified_requirement_is_found(tmp_path, monkeypatch):
    for name in ("requirements-base.txt", "requirements-dev.txt"):
        (tmp_path / name).write_text((BACKEND / name).read_text("utf-8"), "utf-8")
    (tmp_path / "requirements-base.txt").write_text(
        (BACKEND / "requirements-base.txt").read_text("utf-8") + "\ncohere>=5.0  # a new SDK\n", "utf-8"
    )
    monkeypatch.setattr(__import__(__name__, fromlist=["BACKEND"]), "BACKEND", tmp_path)

    classified = {p["package"] for kind in ("outbound", "not_outbound") for p in REGISTRY["dependencies"][kind]}
    assert _requirements() - classified == {"cohere"}


def test_it_catches_a_new_host_and_a_new_helper_caller():
    found = _with(
        {
            "app/services/new_reporter.py": (
                "from app.services.telemetry_service import telemetry_service\n\n\n"
                "ENDPOINT = 'https://collector.example.org/v1'\n\n\n"
                "async def forget():\n    await telemetry_service.forget_installation('id')\n"
            )
        }
    )
    assert found["hosts"] == ["collector.example.org"]
    assert found["modules that send through another module's client or helper"] == ["app/services/new_reporter.py"]


def test_it_catches_a_client_reached_through_a_module_alias_and_a_service_object():
    """`module.service.client`: two attributes deep from the import, which a one-step check missed."""
    for source in (
        "import app.services.notification_service as notifications\n\n\n"
        "async def download(url):\n    return await notifications.notification_service.client.get(url)\n",
        "import app.services.notification_service\n\n\n"
        "async def download(url):\n"
        "    return await app.services.notification_service.notification_service.client.get(url)\n",
        "from app.services import notification_service as module\n\n\n"
        "async def download(url):\n    return await module.notification_service.client.get(url)\n",
    ):
        found = _with({"app/services/new_downloader.py": source})
        assert found["modules that send through another module's client or helper"] == [
            "app/services/new_downloader.py"
        ], source


def test_it_catches_a_client_re_exported_by_a_module_that_did_not_build_it():
    found = _with(
        {
            "app/services/shared_clients.py": "from app.services.garden_notification_transport import http_client\n",
            "app/services/new_downloader.py": (
                "from app.services.shared_clients import http_client\n\n\n"
                "async def download(url):\n    return await http_client.get(url)\n"
            ),
        }
    )
    assert "app/services/new_downloader.py" in found["modules that send through another module's client or helper"]


def test_it_catches_a_connection_opened_through_asyncio():
    for source in (
        "import asyncio\n\n\nasync def dial(host, port):\n    return await asyncio.open_connection(host, port)\n",
        "from asyncio import open_connection\n\n\nasync def dial(host, port):\n    return await open_connection(host, port)\n",
        "import asyncio\n\n\nasync def dial(host, port, factory):\n"
        "    return await asyncio.get_running_loop().create_connection(factory, host, port)\n",
        "import asyncio\n\n\nasync def dial(factory):\n"
        "    return await asyncio.get_running_loop().create_datagram_endpoint(factory, remote_addr=('h', 1))\n",
    ):
        assert _with({"app/services/dialler.py": source})["modules that import an outbound library"] == [
            "app/services/dialler.py"
        ], source


def test_asyncio_used_for_anything_else_is_not_a_connection():
    ordinary = "import asyncio\n\n\nasync def wait():\n    await asyncio.sleep(1)\n    await asyncio.to_thread(print)\n"
    assert _with({"app/services/waiter.py": ordinary})["modules that import an outbound library"] == []


def test_it_reads_an_import_made_by_name_when_the_name_is_written_out():
    for source in (
        "import importlib\n\nclient = importlib.import_module('httpx')\n",
        "client = __import__('aiosmtplib')\n",
        "from importlib import import_module\n\nclient = import_module('urllib.request')\n",
    ):
        assert _with({"app/services/late_import.py": source})["modules that import an outbound library"] == [
            "app/services/late_import.py"
        ], source


def test_an_import_by_a_computed_name_has_to_be_acknowledged_in_the_registry():
    computed = "import importlib\n\n\ndef load(name):\n    return importlib.import_module(name)\n"
    found = _with({"app/services/plugin_loader.py": computed})
    assert found["modules that import by a computed name"] == ["app/services/plugin_loader.py"]
    # The one the backend has today is acknowledged, with the reason.
    assert unregistered(_sources())["modules that import by a computed name"] == []
    assert all(item["reason"].strip() for item in REGISTRY["dynamic_imports"])


# ---- Dependencies declared anywhere a package can be installed from ----------------------------------


def test_packages_installed_by_a_dockerfile_are_read():
    dockerfile = (
        "FROM python:3.13\n"
        "RUN pip install --no-cache-dir --find-links /wheels \\\n"
        "        -r /requirements/requirements-base.txt \\\n"
        "        cohere==5.1 'boto3>=1.34' && rm -rf /tmp/x\n"
        "RUN python -m pip install --upgrade pip; pip3 install -c constraints.txt websockets[speedups]\n"
        "RUN uv pip install --system qdrant-client\n"
        "RUN pip wheel --wheel-dir /wheels -r requirements.txt\n"
    )
    assert dockerfile_packages(dockerfile) == {"cohere", "boto3", "pip", "websockets", "qdrant-client"}


def test_packages_declared_in_pyproject_are_read():
    pyproject = (
        "[project]\nname = 'x'\ndependencies = ['cohere>=5', 'httpx']\n"
        "[project.optional-dependencies]\ncloud = ['boto3 ; python_version > \"3.9\"']\n"
        "[dependency-groups]\ndev = ['pytest']\n"
        "[tool.poetry.dependencies]\npython = '^3.13'\nqdrant-client = '^1.9'\n"
        "[tool.ruff]\nline-length = 120\n"
    )
    assert pyproject_packages(pyproject) == {"cohere", "httpx", "boto3", "pytest", "qdrant-client"}
    assert pyproject_packages("[tool.ruff]\nline-length = 120\n") == set()


def test_every_package_the_images_or_pyproject_install_is_classified_too():
    dependencies = REGISTRY["dependencies"]
    classified = {package["package"] for kind in ("outbound", "not_outbound") for package in dependencies[kind]}
    # pip is the installer itself, upgraded in place by some images.
    declared = declared_packages() - {"pip", "setuptools", "wheel"}

    assert sorted(declared - classified) == [], (
        "A Dockerfile or pyproject.toml installs a package backend/outbound_requests.json does not classify."
    )
    assert _requirements() <= declared_packages()


def test_the_blind_spots_are_each_named_for_reviewers():
    notes = " ".join(REGISTRY["manual_review"])

    # Each of these is something the guard cannot see; removing the note has to fail here.
    assert "importlib.import_module" in notes and "computed" in notes
    assert "getattr" in notes
    assert "apt" in notes and "base image" in notes
    assert "outside backend/app" in notes and "custom_components" in notes
    # And the guarantee is stated as what it is.
    assert "does not prove" in REGISTRY["about"]


# ---- Callers of a registered sender ------------------------------------------------------------------


def test_a_new_caller_of_a_registered_sender_has_to_be_reviewed():
    """The sender is registered; its new caller is where a new request, with new data, now starts."""
    for source in (
        "from app.services.weather_service import weather_service\n\n\n"
        "async def report(lat, lon):\n    return await weather_service.get_current_weather(lat, lon)\n",
        "import app.services.weather_service as weather\n\n\n"
        "async def report(lat, lon):\n    return await weather.weather_service.get_current_weather(lat, lon)\n",
        "import importlib\n\nweather = importlib.import_module('app.services.weather_service')\n",
        "from app.services.frigate_client import frigate_client\n\n\n"
        "async def read(event):\n    return await frigate_client.get_event(event)\n",
    ):
        found = _with({"app/services/new_caller.py": source})
        assert len(found["callers of a registered sender that nobody reviewed"]) == 1, source
        assert found["callers of a registered sender that nobody reviewed"][0].startswith(
            "app/services/new_caller.py -> "
        )


def test_a_sender_reached_through_a_re_export_is_still_a_sender():
    found = _with(
        {
            "app/services/facade.py": "from app.services.weather_service import weather_service\n",
            "app/services/new_caller.py": (
                "from app.services.facade import weather_service\n\n\n"
                "async def report(lat, lon):\n    return await weather_service.get_current_weather(lat, lon)\n"
            ),
        }
    )
    assert (
        "app/services/new_caller.py -> app/services/weather_service.py"
        in (found["callers of a registered sender that nobody reviewed"])
    )


def test_a_reviewed_caller_that_reaches_a_sender_it_did_not_before_is_reviewed_again():
    reviewed = REGISTRY["reviewed_callers"]["callers"]
    caller = next(path for path, senders in reviewed.items() if "app/services/weather_service.py" not in senders)
    extended = _sources()[caller] + "\nfrom app.services.weather_service import weather_service as _new_reach\n"

    assert _with({caller: extended})["callers of a registered sender that nobody reviewed"] == [
        f"{caller} -> app/services/weather_service.py"
    ]


def test_the_reviewed_callers_list_holds_nothing_stale():
    facts = analyse(_sources())
    senders = _sender_modules(REGISTRY)
    actual = {
        caller: reached for caller, reached in callers_of_senders(facts, REGISTRY).items() if caller not in senders
    }

    assert REGISTRY["reviewed_callers"]["callers"] == actual, (
        "backend/outbound_requests.json reviewed_callers must list exactly the modules that call into a "
        "registered sender, each with the senders it reaches. Review what the new call sends before adding it."
    )
    assert REGISTRY["reviewed_callers"]["about"].strip()
