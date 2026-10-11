import asyncio
import json
import os

import numpy as np
import pytest
from PIL import Image

from app.services.video_scene_cache import VideoSceneCache


requires_safe_artifact_open = pytest.mark.skipif(
    not getattr(os, "O_NOFOLLOW", None), reason="Platform has no safe no-follow artifact open"
)


async def wait_for_worker_event(event, worker):
    waiter = asyncio.create_task(event.wait())
    try:
        done, _ = await asyncio.wait({waiter, worker}, timeout=3, return_when=asyncio.FIRST_COMPLETED)
        if worker in done:
            await worker
        assert event.is_set(), "Worker did not reach the expected boundary within three seconds"
    finally:
        waiter.cancel()
        await asyncio.gather(waiter, return_exceptions=True)


def evidence(frame=2, size=(80, 60), score=0.9):
    return {
        "frame_index": frame,
        "frame_width": size[0],
        "frame_height": size[1],
        "frame_offset_seconds": frame / 2,
        "score": score,
    }


@pytest.mark.parametrize("operation", ["write", "load"])
def test_artifact_cache_without_safe_no_follow_open_leaves_files_untouched(tmp_path, monkeypatch, operation):
    import os

    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"clip identity")
    directory = tmp_path / "scenes"
    directory.mkdir()
    cache = VideoSceneCache()
    cache.retain(evidence(), Image.new("RGB", (80, 60)))
    monkeypatch.delattr(os, "O_NOFOLLOW", raising=False)

    def unexpected_open(*args, **kwargs):
        pytest.fail("An unsupported safe artifact open must not read or write files")

    monkeypatch.setattr(os, "open", unexpected_open)
    if operation == "write":
        assert not cache.write(directory, clip, "event", evidence())
    else:
        assert not cache.load(directory, clip, "event")
    assert list(directory.iterdir()) == []
    assert cache.retained_scene(evidence()) is not None


@requires_safe_artifact_open
def test_winning_scene_survives_artifact_without_changing_pixels(tmp_path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"clip identity")
    directory = tmp_path / "scenes"
    directory.mkdir()
    pixels = np.random.default_rng(42).integers(0, 256, (60, 80, 3), dtype=np.uint8)
    image = Image.fromarray(pixels)
    retained = VideoSceneCache()
    retained.retain(evidence(), image)
    assert retained.write(directory, clip, "event", evidence())
    loaded = VideoSceneCache()
    assert loaded.load(directory, clip, "event")
    assert np.array_equal(np.asarray(loaded.scene_for(clip, "event", evidence())), pixels)
    assert loaded.scene_for(clip, "recording", evidence()) is None
    assert loaded.scene_for(clip, "event", evidence(frame=3)) is None
    assert loaded.scene_for(clip, "event", evidence(size=(81, 60))) is None
    # Retained pixels cannot be altered by a later caller changing the source image.
    image.paste("red", (0, 0, 80, 60))
    assert np.array_equal(np.asarray(retained.retained_scene(evidence())), pixels)
    clip.write_bytes(b"different clip")
    assert loaded.scene_for(clip, "event", evidence()) is None


def test_retention_is_bounded_and_eviction_keeps_evidence_fallback(tmp_path):
    cache = VideoSceneCache(max_scenes=2, max_bytes=80 * 60 * 4 * 2)
    for frame in range(20):
        cache.retain(evidence(frame=frame, score=0.5 + frame / 100), Image.new("RGB", (80, 60)))
    assert cache.retained_count == 2
    assert cache.retained_bytes == 80 * 60 * 4 * 2
    assert cache.retained_scene(evidence(frame=0)) is None
    assert cache.retained_scene(evidence(frame=19)) is not None
    cache.retain(evidence(frame=99, size=(800, 600), score=1), Image.new("RGB", (800, 600)))
    assert cache.retained_count == 2
    assert cache.retained_bytes == 80 * 60 * 4 * 2


@requires_safe_artifact_open
@pytest.mark.parametrize("change", ["pixels", "manifest", "variant", "symlink", "missing"])
def test_invalid_or_unavailable_artifact_falls_back_to_decode(tmp_path, change):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"clip identity")
    directory = tmp_path / "scenes"
    directory.mkdir()
    cache = VideoSceneCache()
    cache.retain(evidence(), Image.new("RGB", (80, 60), "green"))
    assert cache.write(directory, clip, "event", evidence())
    if change == "pixels":
        (directory / "scene.bmp").write_bytes(b"corrupt")
    elif change == "manifest":
        (directory / "scene.json").write_text(json.dumps({"frame_width": 999999}))
    elif change == "symlink":
        (directory / "scene.bmp").unlink()
        (directory / "scene.bmp").symlink_to(clip)
    elif change == "missing":
        (directory / "scene.bmp").unlink()
    loaded = VideoSceneCache()
    assert not loaded.load(directory, clip, "recording" if change == "variant" else "event")
    assert loaded.retained_count == 0


def test_cancelled_owner_directory_cannot_be_recreated_by_late_worker(tmp_path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"clip identity")
    cache = VideoSceneCache()
    cache.retain(evidence(), Image.new("RGB", (80, 60)))
    directory = tmp_path / "cancelled"
    assert not cache.write(directory, clip, "event", evidence())
    assert not directory.exists()


def test_clip_changed_during_analysis_cannot_claim_retained_pixels(tmp_path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"original clip")
    directory = tmp_path / "scenes"
    directory.mkdir()
    cache = VideoSceneCache(clip_path=clip, clip_variant="event")
    cache.retain(evidence(), Image.new("RGB", (80, 60)))
    clip.write_bytes(b"replacement clip")
    assert not cache.write(directory, clip, "event", evidence())


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
@pytest.mark.parametrize("missing_flag", [False, True])
async def test_async_boundary_owns_artifact_path_and_returns_only_results(tmp_path, monkeypatch, cancel, missing_flag):
    import asyncio
    from pathlib import Path
    from unittest.mock import AsyncMock

    from app.services.classifier_service import ClassifierService

    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"clip identity")
    service = ClassifierService.__new__(ClassifierService)
    output = VideoSceneCache()
    if missing_flag:
        monkeypatch.delattr(os, "O_NOFOLLOW", raising=False)
    can_share_artifact = bool(getattr(os, "O_NOFOLLOW", None))
    started = asyncio.Event()
    directories = []
    rows = [{"label": "Robin", "score": 0.9, "_video_snapshot_evidence": evidence()}]

    async def classify(**kwargs):
        directory = Path(kwargs["input_context"]["_video_scene_directory"])
        directories.append(directory)
        assert directory.exists() and directory != tmp_path
        worker_cache = VideoSceneCache()
        worker_cache.retain(evidence(), Image.new("RGB", (80, 60), "green"))
        assert worker_cache.write(directory, clip, "event", evidence()) is can_share_artifact
        started.set()
        if cancel:
            await asyncio.Event().wait()
        return rows

    service._classify_video_async_impl = AsyncMock(side_effect=classify)
    task = asyncio.create_task(
        service.classify_video_async(
            str(clip), input_context={"_video_scene_directory": str(tmp_path)}, scene_cache=output
        )
    )
    try:
        await wait_for_worker_event(started, task)
        if cancel:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 3)
            assert output.retained_count == 0
        else:
            assert await asyncio.wait_for(task, 3) == rows
            assert (output.scene_for(clip, "event", evidence()) is not None) is can_share_artifact
            assert "_video_scene_directory" not in json.dumps(rows)
        assert not directories[0].exists()
    finally:
        task.cancel()
        await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), 3)


@pytest.mark.asyncio
async def test_supplied_context_cannot_choose_artifact_directory_without_cache(tmp_path):
    from unittest.mock import AsyncMock

    from app.services.classifier_service import ClassifierService

    service = ClassifierService.__new__(ClassifierService)
    service._classify_video_async_impl = AsyncMock(return_value=[])
    await service.classify_video_async("unused", input_context={"_video_scene_directory": str(tmp_path)})
    assert "_video_scene_directory" not in service._classify_video_async_impl.await_args.kwargs["input_context"]


@requires_safe_artifact_open
@pytest.mark.asyncio
async def test_cancellation_prevents_late_manifest_creation_during_cleanup(tmp_path, monkeypatch):
    import asyncio
    import os
    from pathlib import Path
    import threading
    from unittest.mock import AsyncMock

    from app.services.classifier_service import ClassifierService

    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"clip identity")
    service = ClassifierService.__new__(ClassifierService)
    loop = asyncio.get_running_loop()
    at_manifest = asyncio.Event()
    release, finished = threading.Event(), threading.Event()
    directories = []
    original_open, original_unlink = os.open, os.unlink

    def gated_open(path, *args, **kwargs):
        if str(path).endswith("scene.json"):
            loop.call_soon_threadsafe(at_manifest.set)
            assert release.wait(3)
        return original_open(path, *args, **kwargs)

    def unlink_then_release(path, *args, **kwargs):
        result = original_unlink(path, *args, **kwargs)
        if str(path).endswith("scene.bmp"):
            release.set()
            assert finished.wait(3)
        return result

    def late_writer(directory):
        cache = VideoSceneCache()
        cache.retain(evidence(), Image.new("RGB", (80, 60)))
        try:
            return cache.write(directory, clip, "event", evidence())
        finally:
            finished.set()

    async def classify(**kwargs):
        directory = Path(kwargs["input_context"]["_video_scene_directory"])
        directories.append(directory)
        await asyncio.to_thread(late_writer, directory)
        return []

    monkeypatch.setattr(os, "open", gated_open)
    monkeypatch.setattr(os, "unlink", unlink_then_release)
    service._classify_video_async_impl = AsyncMock(side_effect=classify)
    task = asyncio.create_task(service.classify_video_async(str(clip), scene_cache=VideoSceneCache()))
    try:
        await wait_for_worker_event(at_manifest, task)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 3)
        assert not directories[0].exists()
        assert not directories[0].with_name(directories[0].name + "-discard").exists()
    finally:
        release.set()
        task.cancel()
        await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), 3)


@pytest.mark.asyncio
async def test_worker_boundary_wait_surfaces_failure_before_event():
    async def broken_worker():
        raise RuntimeError("worker failed before signaling")

    worker = asyncio.create_task(broken_worker())
    with pytest.raises(RuntimeError, match="worker failed before signaling"):
        await wait_for_worker_event(asyncio.Event(), worker)
    assert worker.done()
