import asyncio
import os
from unittest.mock import AsyncMock

import pytest

from app.services import bird_finder_revalidation as recovery
from app.services import model_validation as validation

FINDER = "bird_crop_detector_accurate_yolox_tiny"


@pytest.fixture
def environment(tmp_path, monkeypatch):
    monkeypatch.setenv("YAWAMF_EVAL_RUNS_DIR", str(tmp_path / "eval"))
    monkeypatch.setenv("YAWAMF_IMAGE_FLAVOR", "intel")
    monkeypatch.setattr(recovery, "selected_finder", lambda: (FINDER, "abc"))
    monkeypatch.setattr(recovery, "recent_bird_photos", lambda: ["/photos/a.jpg", "/photos/b.jpg"])
    monkeypatch.setattr(validation, "current_provider_runtime_signature", lambda provider: f"old-{provider}")
    validation.write_eligibility_entry(
        FINDER, ["cpu", "intel_cpu", "intel_gpu", "intel_npu"], image_flavor="intel", artifact_sha256="abc"
    )
    monkeypatch.setattr(validation, "current_provider_runtime_signature", lambda provider: f"new-{provider}")
    sweep = AsyncMock(
        return_value={
            "eligible_providers": ["cpu", "intel_cpu", "intel_gpu", "intel_npu"],
            "providers": [
                {"provider": "intel_npu", "ok": True, "latency_ms": 15.0},
                {"provider": "intel_gpu", "ok": True, "latency_ms": 19.0},
                {"provider": "intel_cpu", "ok": True, "latency_ms": 26.0},
                {"provider": "cpu", "ok": True, "latency_ms": 80.0},
            ],
            "best": {"provider": "intel_npu", "latency_ms": 15.0},
            "image_flavor": "intel",
        }
    )
    monkeypatch.setattr(recovery, "sweep_crop_model_devices", sweep)
    return sweep


@pytest.mark.asyncio
async def test_stale_finder_accelerators_are_rechecked_once_on_saved_photos(environment):
    sweep = environment
    runner = recovery.BirdFinderRevalidation()
    await runner.run()

    sweep.assert_awaited_once_with(
        FINDER,
        image_paths=["/photos/a.jpg", "/photos/b.jpg"],
        only_providers={"cpu", "intel_cpu", "intel_gpu", "intel_npu"},
    )
    assert runner.status()["state"] == "succeeded"
    assert validation.host_provider_preference_order(FINDER, artifact_sha256="abc")[0] == "intel_npu"
    assert validation.activation_provider_recommendation(FINDER, artifact_sha256="abc") == "intel_npu"

    await recovery.BirdFinderRevalidation().run()
    assert sweep.await_count == 1


@pytest.mark.asyncio
async def test_finder_that_never_passed_an_accelerator_is_not_checked_automatically(environment, monkeypatch):
    sweep = environment
    monkeypatch.setattr(recovery, "selected_finder", lambda: ("bird_crop_detector_accurate_rfdetr_nano", "def"))
    runner = recovery.BirdFinderRevalidation()
    await runner.run()
    sweep.assert_not_awaited()
    assert runner.status()["state"] == "idle"


@pytest.mark.asyncio
async def test_current_finder_evidence_is_left_alone(environment, monkeypatch):
    sweep = environment
    monkeypatch.setattr(validation, "current_provider_runtime_signature", lambda provider: f"old-{provider}")
    await recovery.BirdFinderRevalidation().run()
    sweep.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_saved_photos_waits_without_spending_the_attempt(environment, monkeypatch):
    sweep = environment
    monkeypatch.setattr(recovery, "recent_bird_photos", lambda: [])
    runner = recovery.BirdFinderRevalidation()
    await runner.run()
    sweep.assert_not_awaited()
    assert runner.status()["state"] == "waiting"

    monkeypatch.setattr(recovery, "recent_bird_photos", lambda: ["/photos/a.jpg"])
    await recovery.BirdFinderRevalidation().run()
    sweep.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_finder_recheck_keeps_cpu_and_does_not_loop(environment):
    sweep = environment
    sweep.return_value = {
        "eligible_providers": ["cpu", "intel_cpu"],
        "providers": [{"provider": "intel_gpu", "ok": False}, {"provider": "cpu", "ok": True, "latency_ms": 80.0}],
        "best": {"provider": "intel_cpu", "latency_ms": 26.0},
        "image_flavor": "intel",
    }
    runner = recovery.BirdFinderRevalidation()
    await runner.run()
    assert runner.status()["state"] == "failed"
    assert set(validation.host_eligible_providers(FINDER, artifact_sha256="abc")) == {"cpu", "intel_cpu"}

    await recovery.BirdFinderRevalidation().run()
    assert sweep.await_count == 1


@pytest.mark.asyncio
async def test_finder_change_during_recheck_publishes_nothing(environment, monkeypatch):
    sweep = environment

    async def changed(*args, **kwargs):
        monkeypatch.setattr(recovery, "selected_finder", lambda: ("bird_crop_detector_accurate_rfdetr_nano", "def"))
        return {"eligible_providers": ["cpu", "intel_npu"], "providers": [], "image_flavor": "intel"}

    sweep.side_effect = changed
    runner = recovery.BirdFinderRevalidation()
    await runner.run()
    assert runner.status()["state"] == "superseded"
    assert validation.host_eligible_providers(FINDER, artifact_sha256="abc") == []


@pytest.mark.asyncio
async def test_interrupted_finder_recheck_is_recorded_without_retry(environment):
    sweep = environment
    sweep.side_effect = asyncio.CancelledError
    runner = recovery.BirdFinderRevalidation()
    with pytest.raises(asyncio.CancelledError):
        await runner.run()
    assert runner.status()["state"] == "interrupted"
    await recovery.BirdFinderRevalidation().run()
    assert sweep.await_count == 1


def test_recent_bird_photos_takes_newest_full_snapshots_only(tmp_path):
    for index, name in enumerate(["old.jpg", "new.jpg", "new_thumb.jpg", "notes.txt", "middle.jpg"]):
        path = tmp_path / name
        path.write_bytes(b"x")
        os.utime(path, (1_000 + index, 1_000 + index))
    (tmp_path / "new.jpg").touch()
    os.utime(tmp_path / "new.jpg", (5_000, 5_000))

    assert recovery.newest_snapshots(tmp_path, limit=2) == [str(tmp_path / "new.jpg"), str(tmp_path / "middle.jpg")]
    assert recovery.newest_snapshots(tmp_path / "missing", limit=2) == []


def test_finder_status_reports_the_automatic_check(monkeypatch):
    from app.services.bird_crop_service import BirdCropService

    monkeypatch.setattr(
        recovery.bird_finder_revalidation,
        "_status",
        recovery.BirdFinderCheckStatus(state="waiting", model_id=FINDER, providers=["intel_npu"]),
    )
    status = BirdCropService().get_status()
    assert status["device_check"]["state"] == "waiting"
    assert status["device_check"]["providers"] == ["intel_npu"]
