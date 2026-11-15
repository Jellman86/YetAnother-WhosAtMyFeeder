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
async def test_rfdetr_without_passing_evidence_checks_accelerators_automatically(environment, monkeypatch):
    sweep = environment
    monkeypatch.setattr(recovery, "selected_finder", lambda: ("bird_crop_detector_accurate_rfdetr_nano", "def"))
    runner = recovery.BirdFinderRevalidation()
    await runner.run()
    sweep.assert_awaited_once()
    assert sweep.await_args.kwargs["prefer_accelerators"] is True
    assert runner.status()["state"] == "succeeded"


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


@pytest.mark.asyncio
@pytest.mark.parametrize("provider, expected", [("intel_npu", {"cpu", "intel_cpu", "intel_npu"}), ("cpu", None)])
async def test_explicit_finder_device_never_automatically_rechecks_another_accelerator(
    environment, monkeypatch, provider, expected
):
    from app.config import settings

    monkeypatch.setattr(settings.classification, "bird_crop_inference_provider", provider)
    runner = recovery.BirdFinderRevalidation()
    await runner.run()
    if expected is None:
        environment.assert_not_awaited()
    else:
        assert environment.await_args.kwargs["only_providers"] == expected


@pytest.mark.asyncio
async def test_only_a_device_change_during_recheck_discards_the_result(environment, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings.classification, "bird_crop_inference_provider", "auto")

    async def changed(*args, **kwargs):
        settings.classification.bird_crop_inference_provider = "cpu"
        return {"eligible_providers": ["cpu", "intel_npu"], "providers": [], "image_flavor": "intel"}

    environment.side_effect = changed
    runner = recovery.BirdFinderRevalidation()
    await runner.run()
    assert runner.status()["state"] == "superseded"
    assert validation.host_eligible_providers(FINDER, artifact_sha256="abc") == []


@pytest.mark.asyncio
async def test_saved_accelerator_is_rechecked_after_failed_sweep_erased_eligibility(environment, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings.classification, "bird_crop_inference_provider", "intel_npu")
    validation.write_eligibility_entry(FINDER, [], artifact_sha256="abc")
    runner = recovery.BirdFinderRevalidation()
    await runner.run()
    environment.assert_awaited_once()
    assert environment.await_args.kwargs["only_providers"] == {"cpu", "intel_npu"}
    assert runner.status()["state"] == "succeeded"


@pytest.mark.asyncio
async def test_failed_result_survives_empty_eligibility_and_runtime_change(environment, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings.classification, "bird_crop_inference_provider", "cpu")
    failure = {
        "state": "failed",
        "model_id": FINDER,
        "providers": ["intel_npu"],
        "reason": "The accelerator did not match the CPU.",
        "checked_at": "2026-11-12T21:59:27Z",
    }
    recovery._write_ledger_entry("previous-runtime", failure)
    validation.write_eligibility_entry(FINDER, [], artifact_sha256="abc")
    runner = recovery.BirdFinderRevalidation()
    await runner.run()
    assert runner.status()["state"] == "failed"
    assert runner.status()["runtime_current"] is False
    assert runner.status()["reason"] == failure["reason"]
    assert runner.status()["checked_at"] == failure["checked_at"]
    environment.assert_not_awaited()


@pytest.mark.asyncio
async def test_running_check_retains_previous_failed_result(environment, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings.classification, "bird_crop_inference_provider", "intel_npu")
    recovery._write_ledger_entry(
        "previous-runtime",
        {
            "state": "failed",
            "model_id": FINDER,
            "providers": ["intel_npu"],
            "reason": "No match",
            "checked_at": "2026-11-12T21:59:27Z",
        },
    )
    runner = recovery.BirdFinderRevalidation()

    async def inspect(*args, **kwargs):
        status = runner.status()
        assert status["state"] == "running"
        assert status["last_result"]["state"] == "failed"
        assert status["last_result"]["runtime_current"] is False
        return environment.return_value

    environment.side_effect = inspect
    await runner.run()
    assert runner.status()["state"] == "succeeded"


@pytest.mark.asyncio
async def test_finder_recheck_retains_current_providers_it_did_not_probe(environment, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings.classification, "bird_crop_inference_provider", "intel_npu")
    validation.write_eligibility_entry(FINDER, ["cpu", "intel_gpu"], image_flavor="intel", artifact_sha256="abc")
    environment.return_value = {
        "eligible_providers": ["cpu"],
        "providers": [{"provider": "cpu", "ok": True}, {"provider": "intel_npu", "ok": False}],
        "best": {"provider": "cpu"},
        "image_flavor": "intel",
    }
    runner = recovery.BirdFinderRevalidation()
    await runner.run()
    assert set(validation.host_eligible_providers(FINDER, artifact_sha256="abc")) == {"cpu", "intel_gpu"}
    await runner.run()
    environment.assert_awaited_once()


@pytest.mark.asyncio
async def test_finder_recheck_does_not_claim_success_when_evidence_cannot_be_saved(environment, monkeypatch):
    monkeypatch.setattr(validation, "write_eligibility_entry", lambda *args, **kwargs: None)
    runner = recovery.BirdFinderRevalidation()
    await runner.run()
    assert runner.status()["state"] == "failed"


@pytest.mark.asyncio
async def test_finder_revalidation_logs_one_outcome_with_box_counts_and_worst_iou(environment, monkeypatch):
    from unittest.mock import Mock

    line = Mock()
    monkeypatch.setattr(recovery.log, "info", line)
    environment.return_value = {
        "eligible_providers": ["cpu"],
        "image_flavor": "intel",
        "best": {"provider": "cpu"},
        "providers": [
            {"provider": "cpu", "ok": True},
            {
                "provider": "intel_npu",
                "ok": False,
                "baseline_boxes": 2,
                "provider_boxes": 1,
                "matched_boxes": 1,
                "worst_box_iou": 0.0,
            },
        ],
    }
    runner = recovery.BirdFinderRevalidation()
    await runner.run()
    line.assert_called_once()
    assert line.call_args.args == ("bird_finder_revalidation_result",)
    assert line.call_args.kwargs["outcome"] == "failed"
    diff = line.call_args.kwargs["box_diff"][1]
    assert diff["baseline_boxes"] == 2
    assert diff["provider_boxes"] == 1
    assert diff["worst_box_iou"] == 0.0


@pytest.mark.asyncio
async def test_rfdetr_saved_npu_recovery_includes_gpu_even_without_old_eligibility(environment, monkeypatch):
    from app.config import settings

    finder = "bird_crop_detector_accurate_rfdetr_nano"
    monkeypatch.setattr(recovery, "selected_finder", lambda: (finder, "abc"))
    monkeypatch.setattr(settings.classification, "bird_crop_inference_provider", "intel_npu")
    environment.return_value = {
        "eligible_providers": ["cpu", "intel_gpu"],
        "image_flavor": "intel",
        "providers": [
            {"provider": "cpu", "ok": True},
            {"provider": "intel_npu", "ok": False},
            {"provider": "intel_gpu", "ok": True},
        ],
        "best": {"provider": "intel_gpu"},
    }
    runner = recovery.BirdFinderRevalidation()
    await runner.run()
    environment.assert_awaited_once_with(
        finder,
        image_paths=["/photos/a.jpg", "/photos/b.jpg"],
        only_providers={"cpu", "intel_npu", "intel_gpu"},
        prefer_accelerators=True,
    )
    assert runner.status()["state"] == "succeeded"
    assert "NPU did not pass" in runner.status()["reason"]
    assert "verified GPU" in runner.status()["reason"]
    await runner.run()
    environment.assert_awaited_once()


@pytest.mark.parametrize(
    "state, reason, expected",
    [
        (
            "failed",
            "The accelerators did not match the CPU on saved bird photos, so the finder stays on the CPU.",
            "mismatch",
        ),
        (
            "failed",
            "The automatic finder check could not finish. Check devices for this finder to retry.",
            "unfinished",
        ),
        ("waiting", "No saved bird photos to compare devices on yet.", "no_photos"),
        ("running", "The inference runtime changed.", "driver_changed"),
        ("interrupted", "The check was interrupted.", "interrupted"),
        ("succeeded", "The finder passed.", "passed"),
    ],
)
def test_legacy_finder_results_have_stable_reason_codes(state, reason, expected):
    status = recovery.BirdFinderCheckStatus(state=state, reason=reason).model_dump()
    assert status["reason_code"] == expected
    assert status["reason"] == reason


@pytest.mark.parametrize(
    "code, state, due",
    [
        ("mismatch", "failed", False),
        ("passed", "succeeded", False),
        ("unfinished", "failed", True),
        ("interrupted", "running", True),
        ("superseded", "superseded", True),
    ],
)
def test_only_conclusive_results_consume_a_runtime_attempt(code, state, due):
    from datetime import datetime, timezone

    entry = {"state": state, "reason_code": code, "checked_at": "2026-11-15T00:00:00+00:00", "attempt_count": 1}
    assert recovery.retry_due(entry, photo_signature="same", now=datetime(2026, 11, 15, 2, tzinfo=timezone.utc)) is due


def test_inconclusive_retry_backoff_is_capped_and_photo_changes_are_distinct():
    from datetime import datetime, timezone

    now = datetime(2026, 11, 15, 2, tzinfo=timezone.utc)
    entry = {"state": "failed", "reason_code": "unfinished", "checked_at": now.isoformat(), "attempt_count": 1}
    assert not recovery.retry_due(entry, photo_signature="same", now=now)
    entry.update(checked_at="2026-11-14T00:00:00Z", attempt_count=3)
    assert not recovery.retry_due(entry, photo_signature="same", now=now)
    entry.update(reason_code="no_positive_baseline", photo_signature="old")
    assert recovery.retry_due(entry, photo_signature="new", now=now)
    assert not recovery.retry_due(entry, photo_signature="old", now=now)


@pytest.mark.asyncio
async def test_unavailable_cpu_baseline_keeps_previous_evidence_and_is_inconclusive(environment, monkeypatch):
    monkeypatch.setattr(
        validation,
        "current_provider_runtime_signature",
        lambda provider: "old-cpu" if provider == "cpu" else f"new-{provider}",
    )
    before = (validation._eval_root() / validation.ELIGIBILITY_FILENAME).read_bytes()
    environment.return_value = {
        "baseline_status": "unavailable",
        "eligible_providers": [],
        "providers": [{"provider": "cpu", "ok": False, "finite": False}],
        "image_flavor": "intel",
    }
    runner = recovery.BirdFinderRevalidation()
    await runner.run()
    assert runner.status()["reason_code"] == "unfinished"
    assert (validation._eval_root() / validation.ELIGIBILITY_FILENAME).read_bytes() == before
    assert "cpu" in validation.host_eligible_providers(FINDER, artifact_sha256="abc")


@pytest.mark.asyncio
async def test_no_positive_baseline_retries_only_after_photos_change(environment, monkeypatch):
    environment.return_value = {
        "baseline_status": "no_positive",
        "eligible_providers": ["cpu"],
        "providers": [
            {"provider": "cpu", "ok": True},
            {"provider": "intel_npu", "ok": False, "baseline_has_birds": False},
        ],
        "image_flavor": "intel",
    }
    runner = recovery.BirdFinderRevalidation()
    await runner.run()
    assert runner.status()["reason_code"] == "no_positive_baseline"
    assert "did not match" not in runner.status()["reason"]
    await runner.run()
    assert environment.await_count == 1
    monkeypatch.setattr(recovery, "recent_bird_photos", lambda: ["/photos/new.jpg"])
    await runner.run()
    assert environment.await_count == 2


@pytest.mark.asyncio
async def test_owner_crop_sweep_prevents_concurrent_automatic_probe(environment):
    async with validation.crop_validation_lock(FINDER):
        await recovery.BirdFinderRevalidation().run()
    environment.assert_not_awaited()


def test_preparation_does_not_publish_status_from_its_worker_thread(environment):
    recovery._write_ledger_entry(
        "old",
        {
            "state": "failed",
            "model_id": FINDER,
            "providers": ["intel_npu"],
            "reason": "The accelerator did not match the CPU.",
            "checked_at": "2026-11-12T00:00:00Z",
        },
    )
    runner = recovery.BirdFinderRevalidation()
    before = runner.status()
    runner._prepare(FINDER, "abc", photos=["/photos/a.jpg"])
    assert runner.status() == before


@pytest.mark.asyncio
async def test_preference_changes_get_a_fresh_attempt_after_superseded(environment, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings.classification, "bird_crop_inference_provider", "intel_npu")

    async def changed(*args, **kwargs):
        settings.classification.bird_crop_inference_provider = "intel_gpu"
        return {"eligible_providers": ["cpu"], "providers": []}

    environment.side_effect = changed
    runner = recovery.BirdFinderRevalidation()
    await runner.run()
    assert runner.status()["state"] == "superseded"
    environment.side_effect = None
    await runner.run()
    assert environment.await_count == 2


@pytest.mark.asyncio
async def test_unfinished_checks_retry_after_backoff_across_restarts_and_stop_at_three(environment):
    from datetime import datetime, timedelta, timezone

    now = datetime(2026, 11, 15, tzinfo=timezone.utc)
    environment.side_effect = RuntimeError("probe failed")
    runner = recovery.BirdFinderRevalidation(clock=lambda: now)
    await runner.run()
    assert runner.status()["attempt_count"] == 1
    assert runner.status()["next_retry_at"] == (now + timedelta(hours=1)).isoformat()
    now += timedelta(minutes=59)
    await recovery.BirdFinderRevalidation(clock=lambda: now).run()
    assert environment.await_count == 1
    now += timedelta(minutes=2)
    runner = recovery.BirdFinderRevalidation(clock=lambda: now)
    await runner.run()
    assert runner.status()["attempt_count"] == 2
    now += timedelta(hours=3)
    await recovery.BirdFinderRevalidation(clock=lambda: now).run()
    assert environment.await_count == 2
    now += timedelta(hours=2)
    runner = recovery.BirdFinderRevalidation(clock=lambda: now)
    await runner.run()
    assert runner.status()["attempt_count"] == 3
    assert runner.status()["next_retry_at"] is None
    assert "Check devices" in runner.status()["reason"]
    assert "retry will follow" not in runner.status()["reason"]
    now += timedelta(days=1)
    await recovery.BirdFinderRevalidation(clock=lambda: now).run()
    assert environment.await_count == 3


@pytest.mark.asyncio
async def test_corrupt_ledger_warning_is_rate_limited(environment, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from unittest.mock import Mock

    now = datetime(2026, 11, 15, tzinfo=timezone.utc)
    recovery._ledger_path().write_text("not json")
    warning = Mock()
    monkeypatch.setattr(recovery.log, "warning", warning)
    runner = recovery.BirdFinderRevalidation(clock=lambda: now)
    await runner.run()
    await runner.run()
    assert warning.call_count == 1
    now += timedelta(hours=1)
    await runner.run()
    assert warning.call_count == 2


def test_retry_uses_the_reported_deadline_after_a_slow_probe():
    from datetime import datetime, timezone

    entry = {
        "state": "failed",
        "reason_code": "unfinished",
        "attempt_count": 1,
        "checked_at": "2026-11-15T00:00:00Z",
        "next_retry_at": "2026-11-15T01:05:00Z",
    }
    assert not recovery.retry_due(entry, photo_signature="same", now=datetime(2026, 11, 15, 1, 2, tzinfo=timezone.utc))


@pytest.mark.asyncio
async def test_no_positive_panel_preserves_a_current_gpu_without_calling_the_new_check_successful(
    environment, monkeypatch
):
    monkeypatch.setattr(
        validation, "current_provider_runtime_signature", lambda p: f"new-{p}" if p == "intel_npu" else f"old-{p}"
    )
    environment.return_value = {
        "baseline_status": "no_positive",
        "eligible_providers": ["cpu"],
        "providers": [
            {"provider": "cpu", "ok": True},
            {"provider": "intel_npu", "ok": False, "baseline_has_birds": False},
        ],
    }
    runner = recovery.BirdFinderRevalidation()
    await runner.run()
    assert runner.status()["reason_code"] == "no_positive_baseline"
    assert "intel_gpu" in validation.host_eligible_providers(FINDER, artifact_sha256="abc")
    assert "stays on the CPU" not in runner.status()["reason"]
