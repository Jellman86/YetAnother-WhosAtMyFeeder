"""Exercise manual scan composition with real counting and fake native boundaries."""

import asyncio
import io
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from PIL import Image
import pytest

from app.services import bird_scan_service as scans


@pytest.mark.asyncio
async def test_manual_scan_keeps_unclassified_boxes_beyond_crop_limit(monkeypatch):
    image = Image.new("RGB", (400, 200), "green")
    output = io.BytesIO()
    image.save(output, format="JPEG")
    boxes = [{"box": (10 + i * 80, 20, 50 + i * 80, 80), "confidence": 0.9} for i in range(4)]
    crop = Image.new("RGB", (80, 80), "green")
    generator = Mock(
        return_value=[
            {
                "crop_image": crop,
                "box": (0, 0, 80, 100),
                "detector_box": boxes[0]["box"],
                "confidence": 0.9,
                "observation_boxes": boxes,
            }
        ]
    )
    monkeypatch.setattr(scans.bird_crop_service, "generate_classification_candidate_crops", generator)
    monkeypatch.setattr(scans.settings.media_cache, "bird_scan_mode", "standard")
    monkeypatch.setattr(
        scans.high_quality_snapshot_service,
        "_score_snapshot_candidate",
        AsyncMock(side_effect=lambda item: {**item, "classifier_label": "House Finch", "classifier_score": 0.95}),
    )
    monkeypatch.setattr(
        scans.high_quality_snapshot_service, "_recheck_weak_count_candidates", AsyncMock(return_value=[])
    )
    detector = Mock(side_effect=AssertionError("cached detector boxes must be reused"))
    monkeypatch.setattr(scans.bird_crop_service, "detect_observation_boxes", detector)
    job = SimpleNamespace(
        event_id="exact-event", revision=1, candidate_id="exact-scene", clip_variant="recording", frame_index=41
    )

    result = await scans.BirdScanService()._analyze_scene(job, output.getvalue())

    assert result.full_frame_candidate_id == "exact-scene"
    assert (result.clip_variant, result.frame_index) == ("recording", 41)
    assert len(result.birds) == 4
    assert result.birds[0].species == "House Finch"
    assert all(bird.species == "Unknown Bird" for bird in result.birds[1:])
    assert all(bird.candidate_id.startswith("exact-scene__observed__") for bird in result.birds)
    assert generator.call_args.kwargs["max_crops"] == 3
    detector.assert_not_called()
    crop.close()
    image.close()


@pytest.mark.asyncio
async def test_cancellation_waits_for_native_reader_before_releasing_image():
    entered, release = threading.Event(), threading.Event()
    image = Image.new("RGB", (1, 1), "green")

    def reader():
        entered.set()
        assert release.wait(2)
        return image.getpixel((0, 0))

    async def owner():
        try:
            await scans._native_call(reader)
        finally:
            image.close()

    task = asyncio.create_task(owner())
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        assert image.getpixel((0, 0)) == (0, 128, 0)
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    with pytest.raises(ValueError):
        image.getpixel((0, 0))
