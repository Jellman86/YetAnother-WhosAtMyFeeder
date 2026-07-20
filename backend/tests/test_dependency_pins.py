from pathlib import Path
import re


def _pinned_version(content: str, package_name: str) -> str | None:
    pattern = re.compile(rf"^{re.escape(package_name)}==([^\s;#]+)", re.MULTILINE)
    match = pattern.search(content)
    return match.group(1) if match else None


def _version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def _load_requirements() -> str:
    backend_root = Path(__file__).resolve().parents[1]
    pending = [backend_root / "requirements.txt"]
    seen: set[Path] = set()
    contents: list[str] = []

    while pending:
        requirements = pending.pop()
        if requirements in seen:
            continue
        seen.add(requirements)
        content = requirements.read_text(encoding="utf-8")
        contents.append(content)
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("-r "):
                pending.append(requirements.parent / stripped.removeprefix("-r ").strip())

    return "\n".join(contents)


def test_openvino_version_constraint():
    content = _load_requirements()
    openvino_lines = [line.strip() for line in content.splitlines() if line.strip().startswith("openvino")]
    assert openvino_lines, "openvino requirement missing"
    assert all(line.partition(";")[0].strip() == "openvino>=2026.2.1,<2027.0" for line in openvino_lines)


def test_msal_pin_is_compatible_with_cryptography_pin():
    content = _load_requirements()
    cryptography_version = _pinned_version(content, "cryptography")
    msal_version = _pinned_version(content, "msal")

    assert cryptography_version, "cryptography pin missing"

    if msal_version and _version_tuple(cryptography_version) >= (44, 0, 0):
        assert _version_tuple(msal_version) >= (1, 34, 0), (
            "msal must be >=1.34.0 when cryptography is pinned to >=44; "
            "older msal releases cap cryptography below 44 and break CI installs"
        )
