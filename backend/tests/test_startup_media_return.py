"""Files an interrupted age cleanup set aside go back before anything reads the media cache (#1109)."""

import ast
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app import main as main_module

MAIN = Path(main_module.__file__)


def _awaited_startup_phases() -> list[tuple[str, str]]:
    """(phase name, action) for each phase the real lifespan awaits outside test mode, in order."""
    tree = ast.parse(MAIN.read_text(encoding="utf-8"))
    lifespan = next(
        node for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef) and node.name == "lifespan"
    )
    test_mode_branch = next(
        node
        for node in lifespan.body
        if isinstance(node, ast.If) and isinstance(node.test, ast.Name) and node.test.id == "test_mode"
    )
    phases: list[tuple[str, str]] = []
    # Only statements of the startup branch itself: a phase moved into test mode, wrapped in a
    # background task or nested in a helper is not one that startup waits for.
    for statement in test_mode_branch.orelse:
        if not (isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Await)):
            continue
        call = statement.value.value
        if isinstance(call, ast.Call) and getattr(call.func, "id", None) == "_run_lifecycle_phase":
            name, action = call.args[1], call.args[2]
            phases.append((ast.literal_eval(name), ast.unparse(action)))
    return phases


def test_startup_returns_interrupted_age_cleanup_right_after_the_database_and_before_every_other_phase():
    phases = _awaited_startup_phases()
    assert [name for name, _action in phases[:2]] == ["db_init", "media_cache_return_interrupted_cleanup"]
    assert phases[1][1] == "_return_interrupted_age_cleanup"
    # Every media reader and writer starts in a later phase.
    later = {name for name, _action in phases[2:]}
    assert {"bird_scan_start", "media_storage_start", "favorite_archive_start", "mqtt_service_task_start"} <= later


@pytest.mark.asyncio
async def test_the_startup_phase_returns_set_aside_files_under_the_housekeeping_lock(monkeypatch):
    held: list[bool] = []
    media = main_module.media_cache

    async def returned() -> int:
        held.append(media.housekeeping_lock.locked())
        return 0

    monkeypatch.setattr(media, "return_age_staged_files", AsyncMock(side_effect=returned))
    await main_module._return_interrupted_age_cleanup()
    assert held == [True]
