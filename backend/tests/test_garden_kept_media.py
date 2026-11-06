"""A confirmed Garden animal keeps its full photograph and clip after Frigate lets them go.

Frigate is mocked at its client. Every test proves one side of the rule: confirmed
media is kept and served, anything else is never kept, and revocation, dismissal and
retention erase what was kept.
"""

from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
from io import BytesIO
import shutil
import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from PIL import Image
import pytest
import pytest_asyncio

from app.config import settings
from app.database import close_db, get_db, init_db
from app.main import app
from app.models.garden import GardenAutomaticCheck, GardenPresenceMass
from app.models.garden_motion import MotionSource
from app.repositories.garden_repository import GardenRepository
from app.services import garden_identification
from app.services import media_cache as cache_module
from app.services.frigate_client import frigate_client
from app.services.garden_capture_service import garden_capture_service
from app.services.garden_media_cache import garden_media_cache, kept_path

EVENT = "1700000000.1-cat"


def photograph(colour: str = "green") -> bytes:
    output = BytesIO()
    Image.new("RGB", (64, 48), colour).save(output, format="JPEG")
    return output.getvalue()


class FakeFrigate:
    """Frigate's client as Garden sees it: an event, its snapshot and its clip, until they expire."""

    def __init__(self) -> None:
        start = time.time() - 3600
        self.event: dict | None = {
            "id": EVENT,
            "camera": "patio",
            "label": "cat",
            "start_time": start,
            "end_time": start + 8,
            "has_clip": True,
        }
        self.snapshot: bytes | None = photograph()
        self.snapshot_error = "snapshot_not_found"
        self.clip: bytes | None = b"\x00\x00\x00\x18ftypmp42" + b"v" * 4096
        self.clip_error = "clip_not_found"
        self.calls: Counter[str] = Counter()

    def gone(self) -> None:
        self.event = self.snapshot = self.clip = None

    async def get_event(self, event_id: str) -> dict | None:
        self.calls["event"] += 1
        return dict(self.event) if self.event else None

    async def get_snapshot_with_error(self, event_id: str, crop: bool = True, **_: object):
        self.calls["snapshot"] += 1
        assert crop is False, "Garden keeps the full frame the record shows"
        return (self.snapshot, None) if self.snapshot else (None, self.snapshot_error)

    async def get_snapshot(self, event_id: str, crop: bool = True, **_: object):
        self.calls["live_snapshot"] += 1
        return self.snapshot

    async def download_clip_to_file(self, event_id: str, dest_path: str, timeout: float = 20.0):
        self.calls["clip"] += 1
        if not self.clip:
            return False, self.clip_error
        with open(dest_path, "wb") as output:
            output.write(self.clip)
        return True, None

    async def get_alignment_snapshot_with_error(self, *_: object, **__: object):
        return None, "unavailable"


@pytest_asyncio.fixture(autouse=True)
async def frigate(monkeypatch):
    monkeypatch.setattr(settings.frigate, "garden_cameras", ["patio"])
    monkeypatch.setattr(settings.frigate, "garden_labels", ["cat", "dog"])
    monkeypatch.setattr(settings.frigate, "clips_enabled", True)
    monkeypatch.setattr(settings.media_cache, "cache_clips", True)
    monkeypatch.setattr(settings.media_cache, "retention_days", 0)
    monkeypatch.setattr(settings.media_cache, "max_size_mb", 0)
    monkeypatch.setattr(settings.media_cache, "per_species_maximum", 0)
    monkeypatch.setattr(settings.maintenance, "retention_days", 0)
    monkeypatch.setattr(settings.auth, "enabled", False)
    monkeypatch.setattr(settings.public_access, "enabled", False)
    monkeypatch.setattr(garden_identification, "bird_work_pending", lambda _status: False)
    monkeypatch.setattr(cache_module.media_cache, "_available", True)
    monkeypatch.setattr(garden_capture_service, "has_history", True)
    fake = FakeFrigate()
    for name in (
        "get_event",
        "get_snapshot_with_error",
        "get_snapshot",
        "download_clip_to_file",
        "get_alignment_snapshot_with_error",
    ):
        monkeypatch.setattr(frigate_client, name, getattr(fake, name))
    shutil.rmtree(cache_module.GARDEN_DIR, ignore_errors=True)
    await init_db()
    async with get_db() as db:
        await db.execute("DELETE FROM garden_kept_media")
        await db.execute("DELETE FROM garden_captures")
        await db.commit()
    yield fake
    await close_db()


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def recent(days: float = 0.0) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days, hours=1)).replace(tzinfo=None).isoformat()


async def frigate_capture(status: str = "pending", event_id: str = EVENT, days: float = 0.0) -> str:
    async with get_db() as db:
        repo = GardenRepository(db)
        await repo.capture(event_id, "patio", "cat", recent(days), True)
        await db.execute("UPDATE garden_captures SET status=? WHERE frigate_event=?", (status, event_id))
        await db.commit()
        async with db.execute("SELECT id FROM garden_captures WHERE frigate_event=?", (event_id,)) as cursor:
            return (await cursor.fetchone())[0]


async def motion_capture(image: bytes) -> str:
    start = time.time() - 120
    source = MotionSource(
        camera="patio",
        clip_start=start,
        clip_end=start + 10,
        frame_index=1,
        frame_offset=1.0,
        clip_sha256="a" * 64,
        image_sha256=hashlib.sha256(image).hexdigest(),
        detector_sha256="b" * 64,
        detector_score=0.9,
        box_xywh=(0.1, 0.2, 0.3, 0.4),
    )
    async with get_db() as db:
        repo = GardenRepository(db)
        capture_id = await repo.capture_motion(source, image)
        await repo.review(capture_id, "confirmed")
    return capture_id


async def record(capture_id: str):
    async with get_db() as db:
        return await GardenRepository(db).kept_media_record(capture_id)


def kept_files() -> set[str]:
    folder = cache_module.GARDEN_DIR
    return {path.name for path in folder.iterdir()} if folder.exists() else set()


@pytest.mark.asyncio
async def test_confirming_a_frigate_capture_keeps_its_photo_and_clip_after_frigate_drops_them(frigate):
    capture_id = await frigate_capture()
    original_photo, original_clip = frigate.snapshot, frigate.clip
    async with client() as http:
        assert (await http.post(f"/api/garden/{capture_id}/confirm")).status_code == 200
        kept = await record(capture_id)
        assert kept.photo_state == kept.clip_state == "kept"
        assert kept.photo_sha256 == hashlib.sha256(original_photo).hexdigest()
        assert kept.clip_sha256 == hashlib.sha256(original_clip).hexdigest()
        assert kept_files() == {f"{capture_id}.jpg", f"{capture_id}.mp4"}

        frigate.gone()
        photo = await http.get(f"/api/garden/{capture_id}/snapshot")
        assert photo.status_code == 200 and photo.content == original_photo
        assert (await http.head(f"/api/frigate/{EVENT}/clip.mp4")).status_code == 200
        clip = await http.get(f"/api/frigate/{EVENT}/clip.mp4")
        assert clip.status_code == 200 and clip.content == original_clip
        item = (await http.get("/api/garden/timeline?status=confirmed")).json()["items"][0]
    assert item["snapshot_url"] == f"/api/garden/{capture_id}/snapshot"
    assert item["clip_event"] == EVENT
    assert item["photo_kept"] is item["clip_kept"] is True


@pytest.mark.asyncio
async def test_a_confirmed_motion_photo_outlives_its_three_day_expiry_without_a_clip(frigate):
    image = photograph("brown")
    capture_id = await motion_capture(image)
    await garden_media_cache.collect(capture_id)
    kept = await record(capture_id)
    assert (kept.photo_state, kept.photo_source, kept.clip_state) == ("kept", "motion_photo", None)
    assert frigate.calls["clip"] == 0
    async with get_db() as db:
        repo = GardenRepository(db)
        await db.execute("UPDATE garden_motion_sources SET expires_at='2000-01-01' WHERE capture_id=?", (capture_id,))
        await db.commit()
        await repo.expire_motion_photos()
        assert await repo.motion_photo(capture_id) is None
        assert (await repo.get(capture_id)).has_snapshot
    assert await garden_capture_service.snapshot(capture_id) == image


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["pending", "dismissed"])
async def test_unconfirmed_captures_are_never_kept(frigate, status):
    capture_id = await frigate_capture(status)
    await garden_media_cache.collect(capture_id)
    await garden_media_cache.collect_one()
    assert await record(capture_id) is None
    assert kept_files() == set()
    assert frigate.calls["snapshot"] == frigate.calls["clip"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["dismiss", "restore", "dismiss-captures"])
async def test_leaving_confirmed_deletes_the_kept_photo_and_clip(frigate, action):
    capture_id = await frigate_capture("confirmed")
    await garden_media_cache.collect(capture_id)
    assert kept_files()
    async with client() as http:
        if action == "dismiss-captures":
            token = (await http.get("/api/garden/timeline?status=confirmed")).json()["items"][0]["review_token"]
            body = {"captures": [{"id": capture_id, "review_token": token}]}
            response = await http.post("/api/garden/dismiss-captures", json=body)
        else:
            response = await http.post(f"/api/garden/{capture_id}/{action}")
        assert response.status_code == 200, response.text
        assert await record(capture_id) is None
        assert kept_files() == set()
        frigate.gone()
        assert (await http.get(f"/api/garden/{capture_id}/snapshot")).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("revocation", ["false_positive", "overlapping_person"])
async def test_a_privacy_revocation_erases_kept_media(frigate, revocation):
    capture_id = await frigate_capture("confirmed")
    await garden_media_cache.collect(capture_id)
    assert kept_files()
    if revocation == "false_positive":
        after = {"id": EVENT, "camera": "patio", "label": "cat", "false_positive": True}
    else:
        window = frigate.event
        after = {
            "id": "1700000999.1-person",
            "camera": "patio",
            "label": "person",
            "start_time": window["start_time"] + 2,
            "end_time": window["start_time"] + 4,
        }
    await garden_capture_service.process({"type": "update", "after": after})
    async with get_db() as db:
        assert await GardenRepository(db).get(capture_id) is None
    assert await record(capture_id) is None
    assert kept_files() == set()


@pytest.mark.asyncio
async def test_a_later_frigate_veto_seen_while_keeping_keeps_nothing(frigate):
    capture_id = await frigate_capture("confirmed")
    frigate.event["label"] = "person"
    await garden_media_cache.collect(capture_id)
    async with get_db() as db:
        assert await GardenRepository(db).get(capture_id) is None
    assert frigate.calls["snapshot"] == 0
    assert kept_files() == set()


@pytest.mark.asyncio
async def test_history_retention_and_media_retention_delete_kept_media(frigate, monkeypatch):
    old = await frigate_capture("confirmed", "1700000000.2-old", days=8)
    fresh = await frigate_capture("confirmed")
    for capture_id in (old, fresh):
        await garden_media_cache.collect(capture_id)
    monkeypatch.setattr(settings.media_cache, "retention_days", 7)
    await garden_media_cache.apply_retention()
    assert (await record(old)).photo_state == "evicted"
    assert kept_files() == {f"{fresh}.jpg", f"{fresh}.mp4"}
    async with get_db() as db:
        repo = GardenRepository(db)
        assert (await repo.get(old)).status == "confirmed"
        await repo.delete_older_than(datetime.now(timezone.utc))
    await garden_media_cache.sweep()
    assert kept_files() == set()


@pytest.mark.asyncio
async def test_a_snapshot_that_differs_from_the_decision_evidence_is_not_kept(frigate):
    capture_id = await frigate_capture("confirmed")
    check = GardenAutomaticCheck(
        outcome="uncertain",
        checked_at=recent(),
        image_sha256="a" * 64,
        variant="4.0.3a",
        model_sha256="b" * 64,
        package_sha256="c" * 64,
        mass=GardenPresenceMass(bird=0.0, animal=1.0, human=0.0, non_animal=0.0, other=0.0),
        devices=["CPU"],
    )
    async with get_db() as db:
        await db.execute(
            "INSERT INTO garden_automatic_checks(capture_id,result_json) VALUES (?,?)",
            (capture_id, check.model_dump_json()),
        )
        await db.commit()
    await garden_media_cache.collect(capture_id)
    assert (await record(capture_id)).photo_state == "changed"
    assert f"{capture_id}.jpg" not in kept_files()


@pytest.mark.asyncio
async def test_a_source_frigate_says_is_gone_is_settled_but_a_failed_request_retries_later(frigate):
    gone = await frigate_capture("confirmed", "1700000000.3-gone", days=8)
    frigate.gone()
    await garden_media_cache.collect_one()
    settled = await record(gone)
    assert (settled.photo_state, settled.clip_state, settled.retry_after) == ("missing", "missing", None)
    calls = frigate.calls.copy()
    await garden_media_cache.collect_one()
    assert frigate.calls == calls

    flaky = await frigate_capture("confirmed", "1700000000.4-flaky")
    frigate.event = {**FakeFrigate().event, "id": "1700000000.4-flaky"}
    frigate.snapshot_error, frigate.clip_error = "snapshot_timeout", "clip_timeout"
    await garden_media_cache.collect_one()
    waiting = await record(flaky)
    assert waiting.photo_state == waiting.clip_state == "retry"
    assert waiting.retry_after > datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    calls = frigate.calls.copy()
    await garden_media_cache.collect_one()
    assert frigate.calls == calls


@pytest.mark.asyncio
async def test_backfill_keeps_each_confirmed_capture_once_and_never_fabricates(frigate):
    available = await frigate_capture("confirmed", "1700000000.5-available")
    expired = await frigate_capture("confirmed", "1700000000.6-expired", days=8)
    pending = await frigate_capture("pending", "1700000000.7-pending")

    async def snapshot(event_id: str, crop: bool = True, **_: object):
        frigate.calls[event_id] += 1
        return (photograph(), None) if event_id.endswith("available") else (None, "snapshot_not_found")

    frigate.get_snapshot_with_error = snapshot
    with patch.object(frigate_client, "get_snapshot_with_error", snapshot):
        for _ in range(5):
            await garden_media_cache.collect_one()
    assert frigate.calls["1700000000.5-available"] == frigate.calls["1700000000.6-expired"] == 1
    assert frigate.calls["1700000000.7-pending"] == 0
    assert (await record(available)).photo_state == "kept"
    assert (await record(expired)).photo_state == "missing"
    assert await record(pending) is None
    assert {name for name in kept_files() if name.endswith(".jpg")} == {f"{available}.jpg"}


@pytest.mark.asyncio
async def test_a_kept_photo_that_no_longer_matches_its_checksum_is_never_served(frigate):
    capture_id = await frigate_capture("confirmed")
    await garden_media_cache.collect(capture_id)
    kept_path(capture_id, "photo").write_bytes(photograph("red"))
    frigate.gone()
    async with client() as http:
        assert (await http.get(f"/api/garden/{capture_id}/snapshot")).status_code == 404


@pytest.mark.asyncio
async def test_guests_read_kept_media_only_under_the_unchanged_public_rules(frigate, monkeypatch):
    capture_id = await frigate_capture("confirmed")
    outside_window = await frigate_capture("confirmed", "1700000000.2-old", days=30)
    for kept in (capture_id, outside_window):
        await garden_media_cache.collect(kept)
    frigate.gone()
    monkeypatch.setattr(settings.auth, "enabled", True)
    monkeypatch.setattr(settings.public_access, "enabled", True)
    monkeypatch.setattr(settings.public_access, "show_snapshots", True)
    monkeypatch.setattr(settings.public_access, "show_clips", True)
    monkeypatch.setattr(settings.public_access, "media_days_mode", "custom")
    monkeypatch.setattr(settings.public_access, "media_historical_days", 7)
    monkeypatch.setattr(settings.public_access, "historical_days_mode", "custom")
    monkeypatch.setattr(settings.public_access, "show_historical_days", 7)
    async with client() as http:
        assert (await http.get(f"/api/garden/{capture_id}/snapshot")).status_code == 200
        assert (await http.get(f"/api/frigate/{EVENT}/clip.mp4")).status_code == 200
        # Kept media does not widen the public media window.
        assert (await http.get(f"/api/garden/{outside_window}/snapshot")).status_code == 404
        assert (await http.get("/api/frigate/1700000000.2-old/clip.mp4")).status_code == 404
        monkeypatch.setattr(settings.public_access, "show_snapshots", False)
        monkeypatch.setattr(settings.public_access, "show_clips", False)
        assert (await http.get(f"/api/garden/{capture_id}/snapshot")).status_code == 404
        assert (await http.get(f"/api/frigate/{EVENT}/clip.mp4")).status_code == 404
        item = (await http.get("/api/garden/timeline")).json()["items"][0]
    assert item["snapshot_url"] is item["clip_event"] is None
    assert item["photo_kept"] is item["clip_kept"] is False


@pytest.mark.asyncio
async def test_an_unreviewed_garden_clip_is_neither_served_from_nor_written_to_the_bird_cache(frigate):
    await frigate_capture("pending")
    stale = cache_module.CLIPS_DIR / f"{EVENT}.mp4"
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_bytes(b"v" * 4096)
    frigate_says_gone = MagicMock()
    frigate_says_gone.get = AsyncMock(return_value=httpx.Response(404, request=httpx.Request("GET", "http://f")))
    try:
        with patch("app.routers.proxy.get_http_client", return_value=frigate_says_gone):
            async with client() as http:
                assert (await http.head(f"/api/frigate/{EVENT}/clip.mp4")).status_code == 404
    finally:
        stale.unlink(missing_ok=True)
    assert await garden_media_cache.event_clip(EVENT) == (True, None)


@pytest.mark.asyncio
async def test_kept_media_shares_the_media_budget_and_the_oldest_goes_first(frigate, monkeypatch):
    from app.services.media_storage_service import media_storage_service

    frigate.clip = b"\x00\x00\x00\x18ftypmp42" + b"v" * 700_000
    older = await frigate_capture("confirmed", "1700000000.8-older", days=2)
    newer = await frigate_capture("confirmed", "1700000000.9-newer", days=1)
    for capture_id in (older, newer):
        await garden_media_cache.collect(capture_id)
    monkeypatch.setattr(settings.media_cache, "max_size_mb", 1)
    with patch.object(media_storage_service, "_inventory", return_value=({}, {})):
        result = await media_storage_service.enforce_limits()
    assert result["visits_evicted"] == 1
    assert (await record(older)).photo_state == "evicted"
    assert kept_files() == {f"{newer}.jpg", f"{newer}.mp4"}
    calls = frigate.calls.copy()
    await garden_media_cache.collect_one()
    assert frigate.calls == calls, "an evicted copy is not recreated in a loop"


@pytest.mark.asyncio
async def test_storage_figures_include_kept_garden_media(frigate):
    capture_id = await frigate_capture("confirmed")
    await garden_media_cache.collect(capture_id)
    stats = cache_module.media_cache._get_cache_stats_sync()
    size = len(frigate.snapshot) + len(frigate.clip)
    assert stats["garden_count"] == 2
    assert stats["garden_size_bytes"] == size
    assert stats["total_size_bytes"] >= size
