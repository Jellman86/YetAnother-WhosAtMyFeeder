"""No module under backend/app may be reachable from nothing that runs.

`ruff` catches unused names; nothing caught an unused *file* until a router nobody
mounted was found by hand. This test is the gate for that class.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from dead_modules_check import find_orphans  # noqa: E402


def _write(root: Path, rel: str, body: str = "") -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")


def test_a_module_nothing_imports_is_reported(tmp_path: Path):
    _write(tmp_path, "app/__init__.py")
    _write(tmp_path, "app/main.py", "from app.routers import events\n")
    _write(tmp_path, "app/routers/__init__.py")
    _write(tmp_path, "app/routers/events.py", "from .helpers import shape\n")
    _write(tmp_path, "app/routers/helpers.py", "def shape(): ...\n")
    _write(tmp_path, "app/routers/stream.py", "# superseded, never mounted\n")

    assert find_orphans(tmp_path) == ["app.routers.stream"]


def test_a_module_named_only_in_a_string_counts_as_launched(tmp_path: Path):
    _write(tmp_path, "app/__init__.py")
    _write(tmp_path, "app/main.py", 'cmd = ["-m", "app.services.worker_process"]\n')
    _write(tmp_path, "app/services/__init__.py")
    _write(tmp_path, "app/services/worker_process.py", "")

    assert find_orphans(tmp_path) == []


def test_a_module_only_a_test_imports_is_still_dead(tmp_path: Path):
    _write(tmp_path, "app/__init__.py")
    _write(tmp_path, "app/main.py", "")
    _write(tmp_path, "app/legacy.py", "")
    _write(tmp_path, "tests/test_legacy.py", "from app.legacy import thing\n")

    assert find_orphans(tmp_path) == ["app.legacy"]


def test_relative_imports_from_a_package_init_are_followed(tmp_path: Path):
    _write(tmp_path, "app/__init__.py")
    _write(tmp_path, "app/main.py", "from app.services import audio\n")
    _write(tmp_path, "app/services/__init__.py", "from .audio import service\n")
    _write(tmp_path, "app/services/audio.py", "from ..config import x\n")
    _write(tmp_path, "app/config.py", "x = 1\n")

    assert find_orphans(tmp_path) == []


def test_a_repo_root_script_is_an_entrypoint_too(tmp_path: Path):
    """scripts/ at the repository root imports app modules and is run by hand."""
    backend = tmp_path / "backend"
    _write(backend, "app/__init__.py")
    _write(backend, "app/main.py", "")
    _write(backend, "app/utils/__init__.py")
    _write(backend, "app/utils/soak_harness.py", "")
    _write(tmp_path, "scripts/run_soak.py", "from app.utils.soak_harness import evaluate\n")

    assert find_orphans(backend) == []


def test_the_real_backend_has_no_orphaned_modules():
    assert find_orphans() == []
