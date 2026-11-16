"""Every request that leaves the network is in the registry About's privacy list is held to.

Reviews of "What leaves your network" kept finding requests nobody had listed.
This guard makes an unlisted one fail here instead. It is deliberately narrow:
it reads source text, not behaviour, and asks three things of `backend/app`.

- A module that imports a library able to send a request (an HTTP client, SMTP,
  MQTT, a provider SDK) is registered: under the entries it makes requests for,
  as a client of an address the owner enters, or as sending nothing, with the
  reason.
- A module that calls a helper which downloads or deletes on its own
  (`ensure_model`, `download_model`, `forget_installation`) is registered under
  an entry.
- An outside host written in the code belongs to an entry, or is listed as not
  contacted, with the reason.

It cannot see a request added inside a module that is already registered when
the host is not written out; the module list names where a reviewer has to look.
"""

import json
from pathlib import Path
import re

BACKEND = Path(__file__).resolve().parents[2]
APP = BACKEND / "app"
REGISTRY = json.loads((BACKEND / "outbound_requests.json").read_text("utf-8"))

# Libraries that can open a connection to another machine.
OUTBOUND_LIBRARIES = (
    "httpx",
    "aiohttp",
    "requests",
    "urllib.request",
    "urllib3",
    "websockets",
    "socket",
    "aiosmtplib",
    "smtplib",
    "aiomqtt",
    "paho",
    "openai",
    "anthropic",
    "google",
    "google_auth_oauthlib",
    "huggingface_hub",
)
_IMPORT = re.compile(
    r"^\s*(?:import|from)\s+(" + "|".join(re.escape(name) for name in OUTBOUND_LIBRARIES) + r")(?:\.|\s|$)",
    re.MULTILINE,
)
# Helpers that send a request themselves when called, without the caller holding a client.
OUTBOUND_HELPERS = ("ensure_model", "download_model", "forget_installation")
_HELPER_CALL = re.compile(r"(?<!def )\b(" + "|".join(OUTBOUND_HELPERS) + r")\(")
_HOST = re.compile(r"https?://([A-Za-z0-9.-]+\.[a-z]{2,})")

ENTRIES = REGISTRY["entries"]
GROUPS = {"server", "browser", "on_demand"}


def _sources() -> dict[str, str]:
    return {path.relative_to(BACKEND).as_posix(): path.read_text("utf-8") for path in sorted(APP.rglob("*.py"))}


def _entry_modules() -> set[str]:
    return {module for entry in ENTRIES for module in entry["modules"]}


def _registered_modules() -> set[str]:
    return (
        _entry_modules()
        | {item["module"] for item in REGISTRY["owner_addresses"]}
        | {item["module"] for item in REGISTRY["no_request"]}
    )


def test_every_module_that_can_send_a_request_is_registered():
    able = {module for module, source in _sources().items() if _IMPORT.search(source)}

    assert sorted(able - _registered_modules()) == [], (
        "These modules import a library that can send a request and are not in backend/outbound_requests.json. "
        "List each under the entry it sends for (and add the row to About), under owner_addresses, or under "
        "no_request with the reason."
    )


def test_every_module_that_calls_a_downloading_helper_is_registered_under_an_entry():
    callers = {module for module, source in _sources().items() if _HELPER_CALL.search(source)}

    assert sorted(callers - _entry_modules()) == []


def test_every_outside_host_in_the_code_belongs_to_an_entry():
    known = {host for entry in ENTRIES for host in entry["hosts"]}
    not_contacted = {item["host"] for item in REGISTRY["hosts_not_contacted"]}
    written = {host for source in _sources().values() for host in _HOST.findall(source)}

    assert sorted(written - known - not_contacted) == [], (
        "These hosts are written in backend/app and belong to no entry of backend/outbound_requests.json."
    )


def test_the_registry_lists_nothing_that_is_no_longer_there():
    sources = _sources()
    written = {host for source in sources.values() for host in _HOST.findall(source)}
    able = {module for module, source in sources.items() if _IMPORT.search(source)}
    callers = {module for module, source in sources.items() if _HELPER_CALL.search(source)}

    assert sorted(_registered_modules() - set(sources)) == [], "a registered module no longer exists"
    assert sorted(_registered_modules() - able - callers) == [], "a registered module can no longer send a request"
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


def test_the_guard_itself_sees_a_new_client_and_a_new_host():
    """The patterns are what the guard rests on, so they are tested on what they must catch."""
    assert _IMPORT.search("import httpx\n")
    assert _IMPORT.search("    from google.oauth2 import credentials\n")
    assert _IMPORT.search("from aiosmtplib import SMTP\n")
    assert not _IMPORT.search("import httpx_helpers_of_our_own\n")
    assert not _IMPORT.search("# import httpx is not needed here\nimport json\n")
    assert _HELPER_CALL.search("await service.ensure_model(variant)")
    assert not _HELPER_CALL.search("async def ensure_model(self, variant):")
    assert _HOST.findall('URL = "https://api.example.org/v1"') == ["api.example.org"]
