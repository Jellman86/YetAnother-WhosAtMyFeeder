from app.utils.photo_retention import merge_photo_choices
import pytest


def _photo(index, *, source="model_crop", selected=False):
    return {
        "candidate_id": f"photo-{index}",
        "frame_index": index,
        "clip_variant": "event",
        "source_mode": source,
        "created_at": f"2026-10-01 00:{index:02d}:00",
        "selected": selected,
        "image_ref": f"photo-{index}-image",
        "thumbnail_ref": f"photo-{index}-thumb",
    }


def test_regeneration_bounds_earlier_choices_and_preserves_original_owner_and_reviewed_frames():
    original = {**_photo(0, source="retained_photo"), "snapshot_source": "frigate_snapshot_unverified"}
    old = [original, *[_photo(i) for i in range(1, 30)], *[_photo(i, source="full_frame") for i in range(30, 35)]]
    fresh = [_photo(i) for i in range(40, 59)]
    rows = merge_photo_choices(old, fresh, reviewed_frames={("event", 30)}, manual_candidate_id="photo-1")
    ids = {row["candidate_id"] for row in rows}
    assert {row["candidate_id"] for row in fresh} <= ids
    assert {"photo-0", "photo-1", "photo-30"} <= ids
    assert {f"photo-{i}" for i in range(22, 30)} <= ids
    assert "photo-2" not in ids
    assert len(rows) == len(fresh) + 11


def test_earlier_crop_keeps_its_exact_full_frame_without_retaining_every_old_scene():
    old = []
    for i in range(20):
        old.extend([_photo(i), {**_photo(i, source="full_frame"), "candidate_id": f"scene-{i}"}])
    rows = merge_photo_choices(old, [_photo(21)], reviewed_frames=set(), manual_candidate_id=None)
    ids = {row["candidate_id"] for row in rows}
    assert len(rows) == 19
    assert all(f"scene-{i}" in ids for i in range(12, 20))
    assert "scene-0" in ids  # The oldest available photo and its comparison survive.


def test_new_retained_photo_participates_in_the_bound_without_changing_selected_photo():
    old = [_photo(i, source="retained_photo") for i in range(20)]
    fresh = [_photo(21, source="retained_photo"), _photo(22, selected=True)]
    rows = merge_photo_choices(old, fresh, reviewed_frames=set(), manual_candidate_id=None)
    assert len(rows) == 10  # Original comparison, eight earlier photos, current selected photo.
    assert [row["candidate_id"] for row in rows if row["selected"]] == ["photo-22"]
    assert any(row["candidate_id"] == "photo-0" for row in rows)


def test_regeneration_updates_existing_keys_without_duplicate_rows():
    old = [_photo(0, selected=True)]
    fresh = [{**_photo(0), "image_ref": "new-bytes", "selected": True}]
    rows = merge_photo_choices(old, fresh, reviewed_frames=set(), manual_candidate_id=None)
    assert rows == fresh


@pytest.mark.asyncio
async def test_candidate_replacement_preserves_creation_time_and_content_identity():
    from app.database import get_db
    from app.repositories.detection_repository import Detection, DetectionRepository
    from app.utils.api_datetime import utc_naive_now

    async with get_db() as db:
        repo = DetectionRepository(db)
        await repo.create(
            Detection(
                detection_time=utc_naive_now(),
                detection_index=1,
                score=0.9,
                display_name="Dunnock",
                category_name="Prunella modularis",
                frigate_event="retention-timestamps",
                camera_name="test",
            )
        )
        row = {**_photo(1), "content_sha256": "a" * 64}
        await repo.replace_snapshot_candidates("retention-timestamps", [row])
        stored = (await repo.list_snapshot_candidates("retention-timestamps"))[0]
        assert stored["content_sha256"] == "a" * 64
        assert stored["created_at"] == row["created_at"]
        await repo.replace_snapshot_candidates("retention-timestamps", [{**stored, "selected": True}])
        repeated = (await repo.list_snapshot_candidates("retention-timestamps"))[0]
        assert repeated["created_at"] == row["created_at"]
        assert repeated["content_sha256"] == "a" * 64


def test_repeated_versions_of_one_frame_do_not_keep_unbounded_companion_images():
    old = []
    for i in range(30):
        old.extend(
            [
                {**_photo(i), "frame_index": 0},
                {**_photo(i, source="full_frame"), "candidate_id": f"scene-{i}", "frame_index": 0},
            ]
        )
    rows = merge_photo_choices(old, [_photo(40)], reviewed_frames={("event", 0)}, manual_candidate_id=None)
    assert len(rows) <= 20
    assert "scene-29" in {row["candidate_id"] for row in rows}


def test_selected_full_frame_is_an_earlier_photo_choice():
    row = _photo(0, source="full_frame", selected=True)
    rows = merge_photo_choices([row], [_photo(1)], reviewed_frames=set(), manual_candidate_id=None)
    assert "photo-0" in {item["candidate_id"] for item in rows}


@pytest.mark.asyncio
async def test_hq_repeated_regeneration_bounds_files_and_preserves_manual_photo(monkeypatch):
    from app.database import get_db
    from app.repositories.detection_repository import Detection, DetectionRepository
    from app.services import high_quality_snapshot_service as hq
    from app.services.video_snapshot_service import _jpeg
    from app.utils.api_datetime import utc_naive_now
    from PIL import Image

    event = "bounded-hq-regeneration"
    async with get_db() as db:
        await DetectionRepository(db).create(
            Detection(
                detection_time=utc_naive_now(),
                detection_index=1,
                score=0.9,
                display_name="Dunnock",
                category_name="Prunella modularis",
                frigate_event=event,
                camera_name="test",
            )
        )
    cache = hq.media_cache
    original = _jpeg(Image.new("RGB", (32, 32), "red"))
    await cache.cache_snapshot(event, original, source="frigate_snapshot")
    service = hq.HighQualitySnapshotService()
    prior = None
    obsolete_ref = None
    for i in range(25):
        row = {
            **_photo(i),
            "candidate_id": f"{event}-choice-{i}",
            "selected": True,
            "image_ref": f"{event}-photo-{i}",
            "thumbnail_ref": f"{event}-thumb-{i}",
            "image_bytes": _jpeg(Image.new("RGB", (32, 32), (i * 7, 40, 90))),
        }
        await service._persist_snapshot_candidates(event, [row])
        if i == 0:
            async with get_db() as db:
                prior = next(
                    item for item in await DetectionRepository(db).list_snapshot_candidates(event) if item["selected"]
                )
            prior["image_bytes"] = row["image_bytes"]
            await cache.set_manual_snapshot_selection(event, True)
        if i == 1:
            async with get_db() as db:
                obsolete_ref = next(
                    item["image_ref"]
                    for item in await DetectionRepository(db).list_snapshot_candidates(event)
                    if item["candidate_id"] == row["candidate_id"]
                )
    async with get_db() as db:
        rows = await DetectionRepository(db).list_snapshot_candidates(event)
    assert len(rows) <= 11
    assert next(row for row in rows if row["selected"])["candidate_id"] == prior["candidate_id"]
    assert await cache.get_snapshot(prior["image_ref"]) == prior["image_bytes"]
    assert await cache.get_snapshot(event) == original
    retained = next(row for row in rows if row["source_mode"] == "retained_photo")
    assert await cache.get_snapshot(retained["image_ref"]) == original
    assert await cache.get_snapshot(obsolete_ref) is None
    assert all([await cache.get_snapshot(row["image_ref"]) for row in rows])


@pytest.mark.asyncio
async def test_hq_failed_candidate_commit_does_not_prune_old_files(monkeypatch):
    from app.database import get_db
    from app.repositories.detection_repository import Detection, DetectionRepository
    from app.services import high_quality_snapshot_service as hq
    from app.utils.api_datetime import utc_naive_now

    event = "failed-retention-commit"
    old = [_photo(i, source="retained_photo") for i in range(20)]
    async with get_db() as db:
        repo = DetectionRepository(db)
        await repo.create(
            Detection(
                detection_time=utc_naive_now(),
                detection_index=1,
                score=0.9,
                display_name="Dunnock",
                category_name="Prunella modularis",
                frigate_event=event,
                camera_name="test",
            )
        )
        await repo.replace_snapshot_candidates(event, old)
    for row in old:
        await hq.media_cache.cache_snapshot(row["image_ref"], b"previous", source="snapshot_candidate")

    async def fail(*args, **kwargs):
        raise RuntimeError("database commit failed")

    monkeypatch.setattr(DetectionRepository, "replace_snapshot_candidates", fail)
    with pytest.raises(RuntimeError, match="database commit failed"):
        await hq.HighQualitySnapshotService()._persist_snapshot_candidates(event, [_photo(30)])
    async with get_db() as db:
        stored = await DetectionRepository(db).list_snapshot_candidates(event)
    assert len(stored) == 20
    assert all([await hq.media_cache.get_snapshot(row["image_ref"]) == b"previous" for row in old])


def test_content_hash_migration_is_reversible_and_keeps_existing_candidate_rows(tmp_path):
    import os
    from pathlib import Path
    import sqlite3
    import subprocess
    import sys

    path = tmp_path / "migration.db"
    env = {**os.environ, "DB_PATH": str(path)}
    backend = Path(__file__).parents[1]

    def migrate(target, direction="upgrade"):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", direction, target],
            cwd=backend,
            env=env,
            capture_output=True,
            timeout=60,
        )
        assert result.returncode == 0, result.stdout.decode() + result.stderr.decode()

    migrate("e98a7230bd14")
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO detections (detection_time,detection_index,score,display_name,category_name,frigate_event,camera_name) VALUES ('2026-10-01',1,.9,'Dunnock','Prunella modularis','legacy','test')"
        )
        db.execute(
            "INSERT INTO snapshot_candidates (frigate_event,candidate_id,frame_index,source_mode,clip_variant,ranking_score,selected) VALUES ('legacy','photo',1,'full_frame','event',.9,1)"
        )
    migrate("head")
    migrate("head")
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT candidate_id,content_sha256 FROM snapshot_candidates").fetchall() == [("photo", None)]
    migrate("e98a7230bd14", "downgrade")
    migrate("head")
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT candidate_id,content_sha256 FROM snapshot_candidates").fetchall() == [("photo", None)]


def test_previous_displayed_photo_survives_a_large_tied_generation():
    old = [{**_photo(i), "created_at": "2026-10-01 00:00:00"} for i in range(16)]
    old[1]["selected"] = True
    rows = merge_photo_choices(old, [_photo(30)], reviewed_frames=set(), manual_candidate_id=None)
    assert "photo-1" in {row["candidate_id"] for row in rows}


@pytest.mark.asyncio
@pytest.mark.parametrize("reuse_displayed_key", [False, True])
async def test_two_unapplied_hq_generations_keep_the_actual_displayed_photo(reuse_displayed_key):
    import hashlib
    from app.database import get_db
    from app.repositories.detection_repository import Detection, DetectionRepository
    from app.services import high_quality_snapshot_service as hq
    from app.utils.api_datetime import utc_naive_now

    event = f"unapplied-hq-{reuse_displayed_key}"
    photo = b"displayed-crop-bytes"
    old = [
        {**_photo(0, source="retained_photo"), "snapshot_source": "frigate_snapshot"},
        {**_photo(1, selected=True), "content_sha256": hashlib.sha256(photo).hexdigest()},
    ]
    async with get_db() as db:
        repo = DetectionRepository(db)
        await repo.create(
            Detection(
                detection_time=utc_naive_now(),
                detection_index=1,
                score=0.9,
                display_name="Dunnock",
                category_name="Prunella modularis",
                frigate_event=event,
                camera_name="test",
            )
        )
        await repo.replace_snapshot_candidates(event, old)
    await hq.media_cache.cache_snapshot(event, photo, source="video_evidence_crop")
    await hq.media_cache.cache_snapshot(old[1]["image_ref"], photo, source="snapshot_candidate")
    for generation in range(2):
        candidates = [
            {
                **_photo(i + 20 + generation * 20),
                "selected": i == 0,
                "image_bytes": b"new-choice" + bytes([i, generation]),
            }
            for i in range(16)
        ]
        if reuse_displayed_key:
            candidates.append({**_photo(1), "image_bytes": b"changed-reused-key"})
        await hq.HighQualitySnapshotService()._persist_snapshot_candidates(event, candidates)
        async with get_db() as db:
            stored = await DetectionRepository(db).list_snapshot_candidates(event)
        matching = [row for row in stored if row.get("content_sha256") == hashlib.sha256(photo).hexdigest()]
        assert matching
        assert any([await hq.media_cache.get_snapshot(row["image_ref"]) == photo for row in matching])
        assert await hq.media_cache.get_snapshot(event) == photo


@pytest.mark.asyncio
async def test_failed_hq_save_never_overwrites_a_referenced_candidate_file(monkeypatch):
    from app.database import get_db
    from app.repositories.detection_repository import Detection, DetectionRepository
    from app.services import high_quality_snapshot_service as hq
    from app.utils.api_datetime import utc_naive_now

    event = "immutable-hq-candidate"
    key = f"{event}__model_crop__f1__aaaaaaaaaa"
    ref = key + "__image"
    row = {**_photo(1), "candidate_id": key, "image_ref": ref, "selected": True}
    async with get_db() as db:
        repo = DetectionRepository(db)
        await repo.create(
            Detection(
                detection_time=utc_naive_now(),
                detection_index=1,
                score=0.9,
                display_name="Dunnock",
                category_name="Prunella modularis",
                frigate_event=event,
                camera_name="test",
            )
        )
        await repo.replace_snapshot_candidates(event, [row])
    await hq.media_cache.cache_snapshot(ref, b"old-reference", source="snapshot_candidate")

    async def fail(*args, **kwargs):
        raise RuntimeError("commit failed")

    monkeypatch.setattr(DetectionRepository, "replace_snapshot_candidates", fail)
    with pytest.raises(RuntimeError, match="commit failed"):
        await hq.HighQualitySnapshotService()._persist_snapshot_candidates(
            event, [{**row, "image_bytes": b"new-reference"}]
        )
    assert await hq.media_cache.get_snapshot(ref) == b"old-reference"
