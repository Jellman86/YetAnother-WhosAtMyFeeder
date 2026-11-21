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
    monkeypatch.setattr(recovery, "present_accelerators", lambda: {"intel_npu", "intel_gpu", "cuda"})
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
        hardware_guard_held=True,
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


def _jpeg(path, size, mtime):
    from PIL import Image

    Image.new("RGB", size, (90, 120, 60)).save(path, "JPEG", quality=60)
    os.utime(path, (mtime, mtime))


def test_the_check_panel_takes_full_camera_frames_and_never_bird_crops(tmp_path):
    # Mirrors a host that keeps model crops and cropped HQ snapshots beside its full frames.
    files = {
        "v1.jpg": ((640, 480), 100),
        "v1_thumb.jpg": ((640, 480), 101),
        "v1__model_crop__f10__c3__aaaaaaaaaa__image.jpg": ((640, 640), 102),
        "v1__model_crop__f10__c3__aaaaaaaaab__thumb_thumb.jpg": ((160, 160), 102),
        "v1__retained_snapshot__bbbbbbbbbbbb__image.jpg": ((800, 600), 103),
        "v1__frigate_hint_crop__f10__cccccccccc__image.jpg": ((800, 600), 104),
        "v1__full_frame__f10__dddddddddd__image.jpg": ((1280, 720), 105),
        "v1__full_frame__f20__eeeeeeeeee__image.jpg": ((1280, 720), 106),
        "v1__full_frame__f30__ffffffffff__image.jpg": ((1280, 720), 107),
        "v2.jpg": ((160, 160), 110),
        "v2__full_frame__f5__1111111111__image.jpg": ((1280, 720), 111),
        "v3__full_frame__f5__2222222222__image.jpg": ((300, 200), 120),
        "v4__full_frame__f5__3333333333__image.jpg": ((1280, 720), 130),
    }
    for name, (size, mtime) in files.items():
        _jpeg(tmp_path / name, size, mtime)
    (tmp_path / "notes.txt").write_text("x")

    chosen = [os.path.basename(path) for path in recovery.select_check_frames(tmp_path, limit=12)]

    # One frame per visit first, newest visit first; then a second from the same visit.
    # v1's model crop at f10 puts that full frame ahead of its newer ones.
    assert chosen == [
        "v4__full_frame__f5__3333333333__image.jpg",
        "v2__full_frame__f5__1111111111__image.jpg",
        "v1__full_frame__f10__dddddddddd__image.jpg",
        "v1__full_frame__f30__ffffffffff__image.jpg",
    ]
    assert [os.path.basename(path) for path in recovery.select_check_frames(tmp_path, limit=3)] == chosen[:3]


def test_frames_where_a_bird_was_cropped_come_before_other_frames_of_the_visit(tmp_path):
    # A model crop at f510 means production found a bird in that exact frame.
    for name, size, mtime in [
        ("v1__full_frame__f900__aaaaaaaaaa__image.jpg", (1280, 720), 109),
        ("v1__full_frame__f510__bbbbbbbbbb__image.jpg", (1280, 720), 101),
        ("v1__model_crop__f510__c3__cccccccccc__image.jpg", (160, 160), 102),
        ("v1__full_frame__f0__dddddddddd__image.jpg", (1280, 720), 105),
        ("v2__full_frame__f1__eeeeeeeeee__image.jpg", (1280, 720), 90),
        ("v3__full_frame__f1__ffffffffff__image.jpg", (1280, 720), 80),
    ]:
        _jpeg(tmp_path / name, size, mtime)
    chosen = [os.path.basename(path) for path in recovery.select_check_frames(tmp_path, limit=12)]
    assert chosen[0] == "v1__full_frame__f510__bbbbbbbbbb__image.jpg"
    assert chosen[3] == "v1__full_frame__f900__aaaaaaaaaa__image.jpg"


def _meta(path, source, *, bound=True):
    import hashlib
    import json

    metadata = {"event_id": path.stem, "source": source}
    if bound:
        metadata["image_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (path.parent / f"{path.name}.meta.json").write_text(json.dumps(metadata))


def test_an_original_event_snapshot_counts_only_when_its_provenance_is_uncropped(tmp_path):
    for index in range(3):
        _jpeg(tmp_path / f"full{index}.jpg", (2688, 1512), 100 + index)
        _meta(tmp_path / f"full{index}.jpg", "frigate_snapshot")
    assert len(recovery.select_check_frames(tmp_path, limit=12)) == 3


@pytest.mark.parametrize("source", ["high_quality_bird_crop", "hq_candidate_model_crop", None])
def test_large_bird_crops_that_replaced_the_event_snapshot_never_qualify(tmp_path, source):
    # HQ processing replaces <event>.jpg with the chosen crop; a 600 px crop passes any size rule.
    for index in range(3):
        path = tmp_path / f"crop{index}.jpg"
        _jpeg(path, (600, 600), 100 + index)
        if source is not None:
            _meta(path, source)
    assert recovery.select_check_frames(tmp_path, limit=12) == []


def test_provenance_for_an_earlier_image_never_vouches_for_its_replacement(tmp_path):
    # HQ processing replaces the image before its sidecar: old full-frame
    # provenance must not admit the new bird crop that now sits beside it.
    for index in range(3):
        path = tmp_path / f"visit{index}.jpg"
        _jpeg(path, (1280, 720), 100 + index)
        _meta(path, "frigate_snapshot")
        _jpeg(path, (600, 600), 100 + index)
    assert recovery.select_check_frames(tmp_path, limit=12) == []


def test_an_event_snapshot_replaced_during_the_check_is_judged_on_the_bytes_it_decoded(tmp_path, monkeypatch):
    for index in range(3):
        path = tmp_path / f"visit{index}.jpg"
        _jpeg(path, (1280, 720), 100 + index)
        _meta(path, "frigate_snapshot")
    real_read = recovery._read_regular_file

    def replace_after_header(path, limit):
        # Swap in a crop between the provenance read and the full image read.
        if path.endswith(".jpg") and limit > recovery.MAX_HEADER_BYTES:
            _jpeg(tmp_path / os.path.basename(path), (800, 800), 100)
        return real_read(path, limit)

    monkeypatch.setattr(recovery, "_read_regular_file", replace_after_header)
    assert recovery.select_check_frames(tmp_path, limit=12) == []


def test_older_snapshots_without_a_recorded_identity_are_not_event_frames(tmp_path):
    for index in range(3):
        path = tmp_path / f"visit{index}.jpg"
        _jpeg(path, (1280, 720), 100 + index)
        _meta(path, "frigate_snapshot", bound=False)
    assert recovery.select_check_frames(tmp_path, limit=12) == []


def test_visits_with_one_saved_frame_still_add_their_proven_event_snapshot(tmp_path):
    for visit in ("v1", "v2"):
        _jpeg(tmp_path / f"{visit}__full_frame__f1__{'a' * 10}__image.jpg", (1280, 720), 100)
        snapshot = tmp_path / f"{visit}.jpg"
        _jpeg(snapshot, (1280, 720), 101)
        _meta(snapshot, "frigate_snapshot")
    assert len(recovery.select_check_frames(tmp_path, limit=12)) == 4


def test_a_cached_panel_expires_even_when_the_directory_time_does_not_change(tmp_path, monkeypatch):
    from app.services import media_cache

    monkeypatch.setattr(media_cache, "SNAPSHOTS_DIR", tmp_path)
    now = [1000.0]
    monkeypatch.setattr(recovery, "_monotonic", lambda: now[0])
    for index in range(3):
        _jpeg(tmp_path / f"v{index}__full_frame__f1__{index:010x}__image.jpg", (1280, 720), 100 + index)
    assert len(recovery.recent_bird_photos()) == 3
    # A coarse-timestamp filesystem: a new file lands without moving the directory mtime.
    listed = os.stat(tmp_path)
    _jpeg(tmp_path / "v9__full_frame__f1__9999999999__image.jpg", (1280, 720), 200)
    os.utime(tmp_path, ns=(listed.st_atime_ns, listed.st_mtime_ns))
    assert len(recovery.recent_bird_photos()) == 3
    now[0] += recovery.SELECTION_CACHE_MAX_AGE_SECONDS
    assert len(recovery.recent_bird_photos()) == 4


def test_final_full_frames_are_full_frames_too(tmp_path):
    for index in range(3):
        _jpeg(tmp_path / f"v{index}__full_frame__final__{index:010x}__image.jpg", (1280, 720), 100 + index)
    _jpeg(tmp_path / "v2__model_crop__final__c3__aaaaaaaaaa__image.jpg", (160, 160), 99)
    _jpeg(tmp_path / "v2__full_frame__f7__bbbbbbbbbb__image.jpg", (1280, 720), 103)
    chosen = [os.path.basename(path) for path in recovery.select_check_frames(tmp_path, limit=12)]
    assert len(chosen) == 4
    # v2 had a bird cropped from its final frame, so that frame leads its visit.
    assert chosen.index("v2__full_frame__final__0000000002__image.jpg") < chosen.index(
        "v2__full_frame__f7__bbbbbbbbbb__image.jpg"
    )


def test_many_newer_small_snapshots_cannot_use_up_the_budget_before_older_full_frames(tmp_path):
    for index in range(recovery.MAX_FRAME_HEADER_READS + 10):
        path = tmp_path / f"new{index:04d}.jpg"
        _jpeg(path, (160, 160), 10_000 + index)
        _meta(path, "frigate_snapshot")
    for index in range(3):
        _jpeg(tmp_path / f"old{index}__full_frame__f1__{index:010x}__image.jpg", (1280, 720), 100 + index)
    assert len(recovery.select_check_frames(tmp_path, limit=12)) == 3


def test_selection_never_follows_symlinks(tmp_path):
    real = tmp_path / "elsewhere"
    real.mkdir()
    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    for index in range(3):
        target = real / f"{index}.jpg"
        _jpeg(target, (1280, 720), 100)
        (snapshots / f"v{index}__full_frame__f1__{index:010x}__image.jpg").symlink_to(target)
    assert recovery.select_check_frames(snapshots, limit=12) == []


def test_a_fifo_named_like_a_frame_cannot_block_selection(tmp_path):
    import threading

    for index in range(3):
        os.mkfifo(tmp_path / f"v{index}__full_frame__f1__{index:010x}__image.jpg")
    result = []
    worker = threading.Thread(target=lambda: result.append(recovery.select_check_frames(tmp_path, limit=12)))
    worker.daemon = True
    worker.start()
    worker.join(timeout=10)
    assert not worker.is_alive()
    assert result == [[]]


def test_a_header_padded_past_the_read_budget_is_rejected_without_reading_it_all(tmp_path, monkeypatch):
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (1280, 720), (90, 120, 60)).save(buffer, "JPEG", quality=60)
    data = buffer.getvalue()
    padding = b"".join(b"\xff\xe5" + (65533).to_bytes(2, "big") + b"\0" * 65531 for _ in range(40))
    for index in range(3):
        (tmp_path / f"v{index}__full_frame__f1__{index:010x}__image.jpg").write_bytes(data[:2] + padding + data[2:])
    reads = []
    real_read = os.read
    monkeypatch.setattr(recovery.os, "read", lambda fd, size: reads.append(size) or real_read(fd, size))
    assert recovery.select_check_frames(tmp_path, limit=12) == []
    assert max(reads) <= recovery.MAX_HEADER_BYTES


def test_truncated_frames_do_not_count_toward_a_panel(tmp_path):
    for index in range(3):
        path = tmp_path / f"v{index}__full_frame__f1__{index:010x}__image.jpg"
        _jpeg(path, (1280, 720), 100 + index)
        path.write_bytes(path.read_bytes()[: path.stat().st_size // 2])
    assert recovery.select_check_frames(tmp_path, limit=12) == []


def test_an_unchanged_snapshot_directory_is_not_listed_again(tmp_path, monkeypatch):
    from app.services import media_cache

    monkeypatch.setattr(media_cache, "SNAPSHOTS_DIR", tmp_path)
    calls = []
    real = recovery.select_check_frames
    monkeypatch.setattr(recovery, "select_check_frames", lambda *a, **k: calls.append(1) or real(*a, **k))
    for index in range(3):
        _jpeg(tmp_path / f"v{index}__full_frame__f1__{index:010x}__image.jpg", (1280, 720), 100 + index)
    first = recovery.recent_bird_photos()
    assert recovery.recent_bird_photos() == first
    assert len(calls) == 1
    _jpeg(tmp_path / "v9__full_frame__f1__9999999999__image.jpg", (1280, 720), 200)
    assert len(recovery.recent_bird_photos()) == 4
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_a_settled_check_never_lists_the_snapshot_directory(environment, monkeypatch):
    monkeypatch.setattr(validation, "current_provider_runtime_signature", lambda provider: f"old-{provider}")
    listed = []
    monkeypatch.setattr(recovery, "recent_bird_photos", lambda: listed.append(1) or ["/photos/a.jpg"])
    monkeypatch.setattr(recovery, "saved_bird_photos_present", lambda: listed.append(1) or True)
    for _ in range(3):
        await recovery.BirdFinderRevalidation().run()
    environment.assert_not_awaited()
    assert listed == []


def test_too_few_full_frames_is_no_panel_at_all(tmp_path):
    _jpeg(tmp_path / "v1__full_frame__f5__1111111111__image.jpg", (1280, 720), 100)
    _jpeg(tmp_path / "v2__full_frame__f5__2222222222__image.jpg", (1280, 720), 101)
    _jpeg(tmp_path / "v3__model_crop__f5__c1__3333333333__image.jpg", (160, 160), 102)
    assert recovery.select_check_frames(tmp_path, limit=12) == []
    assert recovery.select_check_frames(tmp_path / "missing", limit=12) == []


@pytest.mark.asyncio
async def test_saved_crops_without_full_frames_wait_with_their_own_reason(environment, monkeypatch):
    monkeypatch.setattr(recovery, "recent_bird_photos", lambda: [])
    monkeypatch.setattr(recovery, "saved_bird_photos_present", lambda: True)
    runner = recovery.BirdFinderRevalidation()
    await runner.run()
    environment.assert_not_awaited()
    status = runner.status()
    assert status["state"] == "waiting"
    assert status["reason_code"] == "no_full_frames"
    assert "full camera frames" in status["reason"]
    assert status["attempt_count"] == 0


@pytest.mark.asyncio
async def test_an_empty_baseline_from_the_old_crop_panel_does_not_hold_back_the_full_frame_check(environment):
    # The ledger a deployed host already has: no_positive_baseline on the crop panel, four hours to wait.
    from datetime import datetime, timezone

    providers = ["cpu", "intel_cpu", "intel_gpu", "intel_npu"]
    legacy_key = validation._identity_digest(
        {
            "model": FINDER,
            "artifact": "abc",
            "preference": "auto",
            "comparison_policy": 3,
            "runtime": {
                provider: validation.current_provider_runtime_signature(provider)
                for provider in sorted({"cpu", "intel_gpu", "intel_npu"})
            },
        }
    )
    recovery._write_ledger_entry(
        legacy_key,
        {
            "state": "failed",
            "reason_code": "no_positive_baseline",
            "model_id": FINDER,
            "artifact_sha256": "abc",
            "attempt_count": 1,
            "empty_baseline_count": 1,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "photo_signature": recovery.photo_set_signature(["/photos/a.jpg", "/photos/b.jpg"]),
            "requested_providers": providers[2:],
        },
    )
    await recovery.BirdFinderRevalidation().run()
    environment.assert_awaited_once()


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
        hardware_guard_held=True,
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


def test_a_photo_set_change_does_not_rerun_an_empty_baseline_check_within_hours():
    # A busy feeder saves a new snapshot most minutes; each one changes the set.
    from datetime import datetime, timezone

    entry = {
        "state": "failed",
        "reason_code": "no_positive_baseline",
        "photo_signature": "old",
        "checked_at": "2026-11-15T00:00:00Z",
    }
    assert not recovery.retry_due(entry, photo_signature="new", now=datetime(2026, 11, 15, 1, tzinfo=timezone.utc))
    assert recovery.retry_due(entry, photo_signature="new", now=datetime(2026, 11, 15, 4, tzinfo=timezone.utc))


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
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    runner = recovery.BirdFinderRevalidation(clock=lambda: now)
    await runner.run()
    assert runner.status()["reason_code"] == "no_positive_baseline"
    assert "did not match" not in runner.status()["reason"]
    now += timedelta(hours=5)
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


RFDETR = "bird_crop_detector_accurate_rfdetr_nano"
CPU_ONLY_SWEEP = {
    "baseline_status": "usable",
    "eligible_providers": ["cpu"],
    "providers": [{"provider": "cpu", "ok": True, "baseline": True, "baseline_has_birds": True}],
    "best": {"provider": "cpu"},
    "image_flavor": "intel",
}


async def _five_minute_ticks(runner_clock, runner, ticks=200):
    from datetime import timedelta

    for _ in range(ticks):
        await runner.run()
        runner_clock[0] += timedelta(minutes=5)


@pytest.mark.asyncio
async def test_an_intel_image_without_npu_or_gpu_devices_never_sweeps_rfdetr_on_the_cpu(environment, monkeypatch):
    from datetime import datetime, timezone

    monkeypatch.setattr(recovery, "selected_finder", lambda: (RFDETR, "def"))
    monkeypatch.setattr(recovery, "present_accelerators", lambda: set())
    environment.return_value = CPU_ONLY_SWEEP
    clock = [datetime(2026, 11, 15, tzinfo=timezone.utc)]
    runner = recovery.BirdFinderRevalidation(clock=lambda: clock[0])
    await _five_minute_ticks(clock, runner)
    environment.assert_not_awaited()
    assert runner.status()["state"] != "failed"


@pytest.mark.asyncio
async def test_a_check_that_could_probe_no_accelerator_is_final_and_not_retried(environment, monkeypatch):
    from datetime import datetime, timezone

    monkeypatch.setattr(recovery, "selected_finder", lambda: (RFDETR, "def"))
    environment.return_value = CPU_ONLY_SWEEP
    clock = [datetime(2026, 11, 15, tzinfo=timezone.utc)]
    runner = recovery.BirdFinderRevalidation(clock=lambda: clock[0])
    await _five_minute_ticks(clock, runner)
    assert environment.await_count == 1
    status = runner.status()
    assert status["reason_code"] == "no_accelerator"
    assert "retry" not in status["reason"].lower()
    assert status["next_retry_at"] is None


@pytest.mark.parametrize("count, hours", [(1, 4), (2, 8), (3, 16), (4, 24), (9, 24)])
def test_empty_baseline_rechecks_back_off_to_once_a_day(count, hours):
    from datetime import datetime, timedelta, timezone

    checked = datetime(2026, 11, 15, tzinfo=timezone.utc)
    entry = {
        "state": "failed",
        "reason_code": "no_positive_baseline",
        "photo_signature": "old",
        "empty_baseline_count": count,
        "checked_at": checked.isoformat(),
    }
    almost = checked + timedelta(hours=hours) - timedelta(minutes=5)
    assert not recovery.retry_due(entry, photo_signature="new", now=almost)
    assert recovery.retry_due(entry, photo_signature="new", now=checked + timedelta(hours=hours))


@pytest.mark.asyncio
async def test_rfdetr_automatic_checks_never_probe_openvino_cpu(environment, monkeypatch):
    monkeypatch.setattr(validation, "current_provider_runtime_signature", lambda provider: f"old-{provider}")
    validation.write_eligibility_entry(
        RFDETR, ["cpu", "intel_cpu", "intel_npu"], image_flavor="intel", artifact_sha256="def"
    )
    monkeypatch.setattr(validation, "current_provider_runtime_signature", lambda provider: f"new-{provider}")
    monkeypatch.setattr(recovery, "selected_finder", lambda: (RFDETR, "def"))
    await recovery.BirdFinderRevalidation().run()
    environment.assert_awaited_once()
    assert "intel_cpu" not in environment.await_args.kwargs["only_providers"]


def test_a_future_dated_check_from_a_clock_that_ran_ahead_is_due():
    from datetime import datetime, timezone

    now = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)
    ahead = {
        "state": "failed",
        "reason_code": "unfinished",
        "attempt_count": 1,
        "checked_at": "2026-11-16T12:00:00Z",
        "next_retry_at": "2026-11-16T13:00:00Z",
    }
    assert recovery.retry_due(ahead, photo_signature="same", now=now)
    empty = ahead | {"reason_code": "no_positive_baseline", "photo_signature": "old"}
    assert recovery.retry_due(empty, photo_signature="new", now=now)
    assert not recovery.retry_due(ahead | {"state": "failed", "reason_code": "mismatch"}, photo_signature="s", now=now)


def test_status_shows_the_latest_check_by_time_not_by_text(environment, monkeypatch):
    monkeypatch.setattr(recovery, "present_accelerators", lambda: set())
    recovery._write_ledger_entry(
        "a",
        {"state": "failed", "reason_code": "mismatch", "model_id": FINDER, "checked_at": "2026-11-15T10:00:00+01:00"},
    )
    recovery._write_ledger_entry(
        "b", {"state": "succeeded", "reason_code": "passed", "model_id": FINDER, "checked_at": "2026-11-15T09:30:00Z"}
    )
    prepared = recovery.BirdFinderRevalidation()._prepare(FINDER, "abc", photos=[])
    assert prepared.status.reason_code == "passed"


@pytest.mark.asyncio
async def test_an_unreadable_ledger_pauses_checks_and_says_what_to_do(environment):
    path = recovery._ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    runner = recovery.BirdFinderRevalidation()
    await runner.run()
    environment.assert_not_awaited()
    status = runner.status()
    assert status["reason_code"] == "ledger_unreadable"
    assert "retry will follow" not in status["reason"]
    assert "Check devices" in status["reason"]
    await runner.record_owner_check(FINDER, "abc", {"providers": [], "eligible_providers": ["cpu"]})
    assert recovery._read_ledger()


@pytest.mark.asyncio
async def test_the_hardware_guard_is_held_before_the_first_ledger_write(environment, monkeypatch):
    held = []
    write = recovery._write_ledger_entry
    guard = validation.crop_validation_lock(FINDER)

    def observe(key, status, **kwargs):
        held.append(guard.locked())
        write(key, status, **kwargs)

    monkeypatch.setattr(recovery, "_write_ledger_entry", observe)
    await recovery.BirdFinderRevalidation().run()
    assert held and all(held)
    assert not guard.locked()


@pytest.mark.asyncio
async def test_a_failed_owner_check_is_not_repeated_by_the_automatic_check(environment):
    from datetime import datetime, timezone

    now = [datetime(2026, 11, 15, tzinfo=timezone.utc)]
    runner = recovery.BirdFinderRevalidation(clock=lambda: now[0])
    mismatch = {
        "baseline_status": "usable",
        "eligible_providers": ["cpu", "intel_cpu"],
        "providers": [
            {"provider": "cpu", "ok": True},
            {"provider": "intel_npu", "ok": False, "comparison_mismatch": True},
            {"provider": "intel_gpu", "ok": False, "comparison_mismatch": True},
        ],
    }
    await runner.record_owner_check(FINDER, "abc", mismatch)
    await runner.run()
    environment.assert_not_awaited()
    assert runner.status()["reason_code"] == "mismatch"


@pytest.mark.asyncio
async def test_an_unfinished_owner_check_delays_the_automatic_one_by_the_first_backoff(environment):
    from datetime import datetime, timedelta, timezone

    now = [datetime(2026, 11, 15, tzinfo=timezone.utc)]
    runner = recovery.BirdFinderRevalidation(clock=lambda: now[0])
    await runner.record_owner_check(FINDER, "abc", None)
    now[0] += timedelta(minutes=5)
    await runner.run()
    environment.assert_not_awaited()
    now[0] += timedelta(hours=1)
    await runner.run()
    environment.assert_awaited_once()


def test_the_finder_trusts_only_confirmed_uncropped_sources():
    from app.services import classification_input_provenance as provenance

    assert "frigate_snapshot_unverified" not in recovery.FINDER_FRAME_SOURCES
    assert "frigate_thumbnail" not in recovery.FINDER_FRAME_SOURCES
    # Never wider than what classification already calls an uncropped frame.
    assert recovery.FINDER_FRAME_SOURCES <= provenance._FULL_FRAME_SNAPSHOT_SOURCES
