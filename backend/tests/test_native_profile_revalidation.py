import asyncio
import signal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.native_crash_quarantine import NativeCrashQuarantine, NativeCrashQuarantinedError
from app.services.native_profile_revalidation import NativeProfileRevalidation, RevalidationContext


@pytest.fixture
def environment(tmp_path):
    profile = {"model_id": "bird", "provider": "intel_gpu", "model_sha256": "weights", "runtime_signature": "runtime"}
    policy = NativeCrashQuarantine(lambda: dict(profile), root=tmp_path / "incidents")
    policy.record(profile, -signal.SIGSEGV)
    restore = AsyncMock()
    cleanup = AsyncMock()
    context = RevalidationContext(dict(profile), policy, restore, cleanup, "subprocess")

    def getter():
        return context

    probe = AsyncMock(
        return_value={
            "profile_fingerprint": policy._key(profile),
            "active_provider": "intel_gpu",
            "model_sha256": "weights",
            "images_checked": 3,
            "video_frames_checked": 3,
            "finite": True,
            "nondegenerate": True,
            "pipeline_checked": True,
        }
    )
    runner = NativeProfileRevalidation(context_getter=getter, probe=probe, audit_root=tmp_path / "audit")
    return SimpleNamespace(
        profile=profile,
        policy=policy,
        restore=restore,
        cleanup=cleanup,
        context=context,
        probe=probe,
        runner=runner,
        root=tmp_path,
    )


async def start(env):
    return await env.runner.start(env.policy._key(env.profile), [b"image1", b"image2", b"image3"], b"clip")


async def finish(env):
    await env.runner.wait()
    return env.runner.status()


@pytest.mark.asyncio
async def test_success_releases_only_after_probe_reaping_and_restore(environment):
    e = environment
    original = next((e.root / "incidents").glob("*.json")).read_bytes()

    async def restore():
        with pytest.raises(NativeCrashQuarantinedError):
            e.policy.guard(e.profile)

    e.context.restore = restore
    await start(e)
    status = await finish(e)
    assert status.state == "succeeded"
    e.cleanup.assert_awaited_once()
    e.probe.assert_awaited_once()
    assert e.policy.guard(e.profile) == e.profile
    assert next((e.root / "incidents").glob("*.json")).read_bytes() == original
    assert list((e.root / "audit").glob("*.json"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        {"finite": False},
        {"nondegenerate": False},
        {"pipeline_checked": False},
        {"images_checked": 0},
        {"video_frames_checked": 0},
        {"active_provider": "cpu"},
        {"model_sha256": "different"},
        {"profile_fingerprint": "different"},
    ],
)
async def test_invalid_probe_never_releases_profile(environment, change):
    e = environment
    e.probe.return_value.update(change)
    await start(e)
    assert (await finish(e)).state == "failed"
    e.restore.assert_not_awaited()
    with pytest.raises(NativeCrashQuarantinedError):
        e.policy.guard(e.profile)


@pytest.mark.asyncio
async def test_profile_change_during_restore_cannot_release_old_or_new_profile(environment):
    e = environment

    async def restore():
        e.context.profile = e.profile | {"model_id": "changed"}

    e.context.restore = restore
    await start(e)
    assert (await finish(e)).state == "superseded"
    with pytest.raises(NativeCrashQuarantinedError):
        e.policy.guard(e.profile)


@pytest.mark.asyncio
async def test_new_incident_during_probe_prevents_release(environment):
    e = environment

    async def probe(*_args):
        e.policy.remember(e.profile, -signal.SIGSEGV)
        return dict(e.probe.return_value)

    e.probe.side_effect = probe
    await start(e)
    assert (await finish(e)).state == "superseded"
    with pytest.raises(NativeCrashQuarantinedError):
        e.policy.guard(e.profile)


@pytest.mark.asyncio
async def test_duplicate_start_coalesces_and_cancel_keeps_block(environment):
    e = environment
    entered = asyncio.Event()
    reaped = asyncio.Event()

    async def probe(*_args):
        entered.set()
        try:
            await asyncio.Future()
        finally:
            reaped.set()

    e.probe.side_effect = probe
    first = await start(e)
    await entered.wait()
    second = await start(e)
    assert second.attempt_id == first.attempt_id
    await e.runner.cancel(first.attempt_id)
    assert reaped.is_set()
    assert (await finish(e)).state == "cancelled"
    e.restore.assert_not_awaited()
    with pytest.raises(NativeCrashQuarantinedError):
        e.policy.guard(e.profile)


@pytest.mark.asyncio
async def test_stale_owner_fingerprint_is_refused_without_probe(environment):
    e = environment
    with pytest.raises(ValueError, match="changed"):
        await e.runner.start("stale", [b"one", b"two", b"three"], b"clip")
    e.probe.assert_not_awaited()


@pytest.mark.asyncio
async def test_probe_profile_is_frozen_against_in_place_setting_changes(environment):
    e = environment

    async def probe(context, *_args):
        e.context.profile["provider"] = "cpu"
        assert context.profile["provider"] == "intel_gpu"
        return dict(e.probe.return_value)

    e.probe.side_effect = probe
    await start(e)
    assert (await finish(e)).state == "superseded"
    e.restore.assert_not_awaited()


@pytest.mark.asyncio
async def test_incomplete_child_cleanup_disables_further_attempts(environment):
    from app.services.native_profile_probe import ProbeCleanupFailed

    e = environment
    e.probe.side_effect = ProbeCleanupFailed("not reaped")
    await start(e)
    assert (await finish(e)).state == "failed"
    assert (await e.runner.inspect()).profile.eligible is False
    with pytest.raises(ValueError, match="cleanup"):
        await start(e)
    assert e.probe.await_count == 1


@pytest.mark.asyncio
async def test_cancel_request_disconnect_waits_for_child_cleanup(environment):
    e = environment
    entered = asyncio.Event()
    cleaning = asyncio.Event()
    allow_cleanup = asyncio.Event()

    async def probe(*_args):
        entered.set()
        try:
            await asyncio.Future()
        finally:
            cleaning.set()
            await allow_cleanup.wait()

    e.probe.side_effect = probe
    first = await start(e)
    await entered.wait()
    request = asyncio.create_task(e.runner.cancel(first.attempt_id))
    await cleaning.wait()
    request.cancel()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    try:
        assert not request.done()
        assert e.runner.status().state == "running"
    finally:
        allow_cleanup.set()
        await asyncio.gather(request, return_exceptions=True)
        await e.runner.wait()
    assert e.runner.status().state == "cancelled"


@pytest.mark.asyncio
async def test_prepare_never_launches_native_work_and_cancel_prevents_late_upload(environment):
    e = environment
    prepared = await e.runner.prepare(e.policy._key(e.profile))
    assert prepared.state == "uploading"
    e.probe.assert_not_awaited()
    assert (await e.runner.cancel(prepared.attempt_id)).state == "cancelled"
    with pytest.raises(ValueError, match="upload"):
        await e.runner.start_prepared(prepared.attempt_id, [b"one", b"two", b"three"], b"clip")
    e.probe.assert_not_awaited()


@pytest.mark.asyncio
async def test_new_incident_while_uploading_prevents_native_launch(environment):
    e = environment
    prepared = await e.runner.prepare(e.policy._key(e.profile))
    e.policy.remember(e.profile, -signal.SIGSEGV)
    with pytest.raises(ValueError, match="incident"):
        await e.runner.start_prepared(prepared.attempt_id, [b"one", b"two", b"three"], b"clip")
    e.probe.assert_not_awaited()


@pytest.mark.asyncio
async def test_changed_profile_while_uploading_prevents_native_launch(environment):
    e = environment
    prepared = await e.runner.prepare(e.policy._key(e.profile))
    e.context.profile = e.profile | {"provider": "cpu"}
    with pytest.raises(ValueError, match="profile"):
        await e.runner.start_prepared(prepared.attempt_id, [b"one", b"two", b"three"], b"clip")
    e.probe.assert_not_awaited()


@pytest.mark.asyncio
async def test_expired_reservation_never_launches_probe(environment, monkeypatch):
    e = environment
    prepared = await e.runner.prepare(e.policy._key(e.profile), attempt_id="known-request")
    deadline = e.runner._upload_deadline
    monkeypatch.setattr(
        "app.services.native_profile_revalidation.time", SimpleNamespace(monotonic=lambda: deadline + 1)
    )
    with pytest.raises(ValueError, match="upload"):
        await e.runner.start_prepared(prepared.attempt_id, [b"one", b"two", b"three"], b"clip")
    assert e.runner.status().state == "failed"
    e.probe.assert_not_awaited()


@pytest.mark.asyncio
async def test_shutdown_cancels_upload_without_native_work(environment):
    e = environment
    await e.runner.prepare(e.policy._key(e.profile))
    await e.runner.shutdown()
    assert e.runner.status().state == "cancelled"
    e.probe.assert_not_awaited()


@pytest.mark.asyncio
async def test_duplicate_prepare_is_idempotent_but_cannot_replace_another_attempt(environment):
    e = environment
    first = await e.runner.prepare(e.policy._key(e.profile), attempt_id="first")
    assert await e.runner.prepare(e.policy._key(e.profile), attempt_id="first") == first
    with pytest.raises(ValueError, match="active"):
        await e.runner.prepare(e.policy._key(e.profile), attempt_id="second")
    await e.runner.abandon_upload("second")
    assert e.runner.status().state == "uploading"


@pytest.mark.asyncio
async def test_audit_failure_cannot_release_a_profile(environment):
    e = environment
    e.runner._audit = AsyncMock(side_effect=OSError("fixture permission failure"))
    await start(e)
    assert (await finish(e)).state == "failed"
    e.probe.assert_not_awaited()
    with pytest.raises(NativeCrashQuarantinedError):
        e.policy.guard(e.profile)


@pytest.mark.asyncio
async def test_live_pressure_prevents_probe_without_changing_incidents(environment):
    e = environment
    e.context.pressure = lambda: "Bird classification needs the hardware."
    await start(e)
    assert (await finish(e)).state == "failed"
    e.probe.assert_not_awaited()
    e.restore.assert_not_awaited()


@pytest.mark.asyncio
async def test_only_one_upload_stream_can_claim_a_reserved_attempt(environment):
    e = environment
    attempt = await e.runner.prepare(e.policy._key(e.profile))
    e.runner.claim_upload(attempt.attempt_id)
    with pytest.raises(ValueError, match="upload in progress"):
        e.runner.claim_upload(attempt.attempt_id)
    await e.runner.abandon_upload(attempt.attempt_id)
    with pytest.raises(ValueError, match="no longer current"):
        e.runner.claim_upload(attempt.attempt_id)
    e.probe.assert_not_awaited()


@pytest.mark.asyncio
async def test_safe_probe_failure_reaches_owner_status_and_audit_without_releasing_profile(environment):
    import json
    from app.services.native_profile_probe_result import failure_message

    e = environment
    message = failure_message({"reason": "device_failure", "device_code": "CL_OUT_OF_RESOURCES"})
    e.probe.side_effect = ValueError(message)
    await start(e)
    status = await finish(e)
    assert status.state == "failed" and status.message == message
    assert "CL_OUT_OF_RESOURCES" in status.message
    e.restore.assert_not_awaited()
    with pytest.raises(NativeCrashQuarantinedError):
        e.policy.guard()
    audit = json.loads(next((e.root / "audit").glob("*.json")).read_text())
    assert audit["message"] == message and audit["state"] == "failed"


@pytest.mark.asyncio
async def test_unverifiable_incident_evidence_disables_check_and_refuses_upload(environment):
    e = environment
    next((e.root / "incidents").glob("*.json")).write_text("DUMMY-corrupt-incident")
    view = await e.runner.inspect()
    assert view.profile.blocked and not view.profile.eligible
    assert "could not be verified" in view.profile.reason
    with pytest.raises(ValueError, match="could not be verified"):
        await start(e)
    e.probe.assert_not_awaited()


@pytest.mark.asyncio
async def test_owner_inspection_checks_worker_approval_off_the_event_loop(environment, monkeypatch):
    import threading

    e = environment
    loop_thread = threading.get_ident()
    threads = []
    original = e.policy.worker_approval

    def inspect_approval(profile):
        threads.append(threading.get_ident())
        return original(profile)

    monkeypatch.setattr(e.policy, "worker_approval", inspect_approval)
    await e.runner.inspect()
    assert threads and all(thread != loop_thread for thread in threads)
