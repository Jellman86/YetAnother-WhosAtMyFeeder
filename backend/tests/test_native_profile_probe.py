import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.services import native_profile_probe as probe


@pytest.fixture
def guarded_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(probe, "memory_budget", lambda: 1024**3)
    monkeypatch.setattr(probe, "available_memory", lambda: 8 * 1024**3)
    monkeypatch.setattr(probe, "group_usage", lambda _group: (0, 0))
    monkeypatch.setattr(probe, "_POLL_SECONDS", 0.001)
    monkeypatch.setattr(probe, "reap", AsyncMock())
    return tmp_path


@pytest.mark.asyncio
async def test_cancellation_during_spawn_reaps_child_before_removing_uploads(monkeypatch, guarded_environment):
    entered = asyncio.Event()
    allow_spawn = asyncio.Event()
    child = AsyncMock(pid=123456)

    async def spawn(*_args, **_kwargs):
        entered.set()
        await allow_spawn.wait()
        return child

    monkeypatch.setattr(probe.asyncio, "create_subprocess_exec", spawn)
    job = asyncio.create_task(probe.run_profile_probe({}, [b"one", b"two", b"three"], b"clip", lambda: None))
    await entered.wait()
    job.cancel()
    await asyncio.sleep(0)
    try:
        assert not job.done()
    finally:
        allow_spawn.set()
        await asyncio.gather(job, return_exceptions=True)
    probe.reap.assert_awaited_once_with(child)
    assert not list(guarded_environment.rglob("photo-*.image"))


@pytest.mark.asyncio
async def test_repeated_cancellation_finishes_reaping_and_deletes_private_uploads(monkeypatch, guarded_environment):
    entered = asyncio.Event()
    cleaning = asyncio.Event()
    finish_cleanup = asyncio.Event()
    child = AsyncMock(pid=123456)

    async def communicate(_payload):
        entered.set()
        await asyncio.Future()

    child.communicate.side_effect = communicate
    monkeypatch.setattr(probe.asyncio, "create_subprocess_exec", AsyncMock(return_value=child))

    async def reap(_child):
        cleaning.set()
        await finish_cleanup.wait()

    monkeypatch.setattr(probe, "reap", reap)
    job = asyncio.create_task(probe.run_profile_probe({}, [b"one", b"two", b"three"], b"clip", lambda: None))
    await entered.wait()
    job.cancel()
    await cleaning.wait()
    job.cancel()
    await asyncio.sleep(0)
    assert not job.done()
    finish_cleanup.set()
    await asyncio.gather(job, return_exceptions=True)
    assert not list(guarded_environment.rglob("photo-*.image"))


@pytest.mark.asyncio
async def test_pressure_aborts_probe_and_reaps_child(monkeypatch, guarded_environment):
    running = asyncio.Event()
    child = AsyncMock(pid=123456)

    async def communicate(_payload):
        running.set()
        await asyncio.Future()

    child.communicate.side_effect = communicate
    monkeypatch.setattr(probe.asyncio, "create_subprocess_exec", AsyncMock(return_value=child))
    with pytest.raises(ValueError, match="Live work"):
        await probe.run_profile_probe(
            {}, [b"one", b"two", b"three"], b"clip", lambda: "Live work needs capacity" if running.is_set() else None
        )
    probe.reap.assert_awaited_once_with(child)
    assert not list(guarded_environment.rglob("photo-*.image"))


@pytest.mark.asyncio
async def test_report_success_waits_for_process_group_reaping(monkeypatch, guarded_environment):
    child = AsyncMock(pid=123456, returncode=0)

    async def communicate(payload):
        Path(json.loads(payload)["result"]).write_text('{"finite": true}')

    child.communicate.side_effect = communicate
    monkeypatch.setattr(probe.asyncio, "create_subprocess_exec", AsyncMock(return_value=child))
    assert await probe.run_profile_probe({}, [b"one", b"two", b"three"], b"clip", lambda: None) == {"finite": True}
    probe.reap.assert_awaited_once_with(child)
    assert not list(guarded_environment.rglob("photo-*.image"))


@pytest.mark.asyncio
async def test_insufficient_memory_never_spawns_or_stages_inputs(monkeypatch, guarded_environment):
    spawn = AsyncMock()
    monkeypatch.setattr(probe.asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setattr(probe, "available_memory", lambda: 512 * 1024**2)
    with pytest.raises(ValueError, match="memory headroom"):
        await probe.run_profile_probe({}, [b"one", b"two", b"three"], b"clip", lambda: None)
    spawn.assert_not_awaited()
    assert not list(guarded_environment.rglob("photo-*.image"))


@pytest.mark.asyncio
async def test_failed_reaping_retains_inputs_and_reports_cleanup_lockout(monkeypatch, guarded_environment):
    child = AsyncMock(pid=123456, returncode=0)

    async def communicate(payload):
        Path(json.loads(payload)["result"]).write_text("{}")

    child.communicate.side_effect = communicate
    monkeypatch.setattr(probe.asyncio, "create_subprocess_exec", AsyncMock(return_value=child))
    monkeypatch.setattr(probe, "reap", AsyncMock(side_effect=probe.ProbeCleanupFailed("pending")))
    with pytest.raises(probe.ProbeCleanupFailed):
        await probe.run_profile_probe({}, [b"one", b"two", b"three"], b"clip", lambda: None)
    assert len(list(guarded_environment.rglob("photo-*.image"))) == 3


@pytest.mark.asyncio
async def test_reaping_kills_the_owned_process_group(tmp_path):
    import sys

    child = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        'import subprocess,sys,time; subprocess.Popen([sys.executable,"-c","import time; time.sleep(10)"]); print("ready",flush=True); time.sleep(10)',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        assert await asyncio.wait_for(child.stdout.readline(), 3) == b"ready\n"
        await probe.reap(child)
        assert child.returncode is not None
        assert probe.group_usage(child.pid)[1] == 0
    finally:
        if child.returncode is None:
            await probe.reap(child)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["signal", "observation"])
async def test_unverifiable_reaping_requires_cleanup_lockout(monkeypatch, failure):
    from unittest.mock import Mock

    child = AsyncMock(pid=123456)
    monkeypatch.setattr(probe.os, "killpg", Mock(side_effect=PermissionError() if failure == "signal" else None))
    monkeypatch.setattr(probe, "group_usage", Mock(side_effect=ValueError("unobservable")))
    with pytest.raises(probe.ProbeCleanupFailed):
        await probe.reap(child)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure,message",
    [
        ({"reason": "invalid_clip"}, "readable short clip"),
        ({"reason": "crop_check_failed"}, "crop detector"),
        ({"reason": "device_failure", "device_code": "CL_OUT_OF_RESOURCES"}, "CL_OUT_OF_RESOURCES"),
    ],
)
async def test_failed_child_reports_only_allow_listed_actionable_causes(
    monkeypatch, guarded_environment, failure, message
):
    child = AsyncMock(pid=123456, returncode=1)

    async def communicate(payload):
        Path(json.loads(payload)["result"]).write_text(json.dumps({"failure": failure}))

    child.communicate.side_effect = communicate
    monkeypatch.setattr(probe.asyncio, "create_subprocess_exec", AsyncMock(return_value=child))
    with pytest.raises(ValueError, match=message):
        await probe.run_profile_probe({}, [b"one", b"two", b"three"], b"clip", lambda: None)
    probe.reap.assert_awaited_once_with(child)
    assert not list(guarded_environment.rglob("photo-*.image"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "report",
    [
        None,
        "broken json",
        "x" * 65537,
        "[]",
        '{"failure":{"reason":"DUMMY-private-detail"}}',
        '{"failure":{"reason":"device_failure","device_code":"DUMMY-private-detail"}}',
        '{"failure":{"reason":"invalid_clip","message":"DUMMY-private-detail"}}',
        '{"finite":true,"pipeline_checked":true}',
    ],
)
async def test_unknown_or_missing_failure_report_never_exposes_child_details(monkeypatch, guarded_environment, report):
    child = AsyncMock(pid=123456, returncode=1)

    async def communicate(payload):
        if report is not None:
            Path(json.loads(payload)["result"]).write_text(report)

    child.communicate.side_effect = communicate
    monkeypatch.setattr(probe.asyncio, "create_subprocess_exec", AsyncMock(return_value=child))
    with pytest.raises(ValueError) as error:
        await probe.run_profile_probe({}, [b"one", b"two", b"three"], b"clip", lambda: None)
    assert "DUMMY" not in str(error.value)
    assert "remains blocked" in str(error.value)
    assert not list(guarded_environment.rglob("photo-*.image"))


@pytest.mark.asyncio
async def test_a_failure_report_cannot_be_treated_as_success_on_zero_exit(monkeypatch, guarded_environment):
    child = AsyncMock(pid=123456, returncode=0)

    async def communicate(payload):
        Path(json.loads(payload)["result"]).write_text('{"finite":true,"failure":{"reason":"invalid_clip"}}')

    child.communicate.side_effect = communicate
    monkeypatch.setattr(probe.asyncio, "create_subprocess_exec", AsyncMock(return_value=child))
    with pytest.raises(ValueError, match="invalid report"):
        await probe.run_profile_probe({}, [b"one", b"two", b"three"], b"clip", lambda: None)
    probe.reap.assert_awaited_once_with(child)
