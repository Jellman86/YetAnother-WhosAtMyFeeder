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
        # Every `root.attr` reached from a bound name, to find `service.client`.
        self.attribute_reads: set[tuple[str, str]] = set()
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
        root = node.value
        while isinstance(root, ast.Attribute):
            self.attribute_reads.add((self._root_name(root), root.attr))
            root = root.value
        self.attribute_reads.add((self._root_name(node), node.attr))
        self.generic_visit(node)

    @staticmethod
    def _root_name(node: ast.Attribute) -> str:
        value: ast.AST = node
        while isinstance(value, ast.Attribute):
            value = value.value
        return value.id if isinstance(value, ast.Name) else ""

    def visit_Call(self, node: ast.Call) -> None:
        called = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", None)
        if called in OUTBOUND_HELPERS:
            self.helper_calls.add(called)
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str):
            self.hosts.update(_HOST.findall(node.value))

    roots: frozenset[str] = frozenset()

    def imports_an_outbound_library(self) -> bool:
        return any(_is_under(origin, self.roots) for origin in self.bound.values())


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


def borrows_a_client(module: ModuleFacts, facts: dict[str, ModuleFacts]) -> bool:
    """Whether the module sends through a client that another app module built."""
    by_name = {other.name: other for other in facts.values()}
    for local, origin in module.bound.items():
        owner_name, _, imported = origin.rpartition(".")
        owner = by_name.get(owner_name)
        if owner is None or owner is module:
            continue
        # `from app.services.x import http_client`: the client itself.
        if imported in owner.module_clients:
            return True
        # `from app.services.x import service` then `service.client...`: a client an object holds.
        if any(root == local and attribute in owner.attribute_clients for root, attribute in module.attribute_reads):
            return True
    # `import app.services.x as x` then `x.http_client...`.
    for local, origin in module.bound.items():
        owner = by_name.get(origin)
        if owner is not None and owner is not module:
            if any(root == local and attribute in owner.module_clients for root, attribute in module.attribute_reads):
                return True
    return False


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


def test_it_does_not_mistake_an_ordinary_use_of_a_service_for_a_borrowed_client():
    ordinary = (
        "from app.services.notification_service import notification_service\n\n\n"
        "async def announce():\n    return await notification_service.send_detection()\n"
    )
    assert _with({"app/services/announcer.py": ordinary}) == {
        "modules that import an outbound library": [],
        "modules that send through another module's client or helper": [],
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
