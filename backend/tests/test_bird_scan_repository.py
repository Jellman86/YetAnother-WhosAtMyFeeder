"""Durable scan admission preserves input and fences stale workers."""

import asyncio
import sqlite3

import pytest
import pytest_asyncio

from app.database import close_db, get_db, init_db
from app.repositories.bird_scan_repository import BirdScanBusyError, BirdScanNotFoundError, BirdScanRepository

INPUT = dict(
    candidate_id="frame-1",
    image_ref="frames/frame-1.jpg",
    content_sha256="a" * 64,
    media_version="inode:mtime:size",
    clip_variant="event",
    frame_index=1,
)


@pytest_asyncio.fixture
async def repo():
    await init_db()
    async with get_db() as db:
        await db.execute("DELETE FROM detections WHERE frigate_event LIKE 'scan-test-%'")
        await db.execute("""INSERT INTO detections(detection_time,detection_index,score,display_name,
            category_name,frigate_event,camera_name) VALUES ('2026-10-08 10:00:00',0,0.9,
            'Robin','Robin','scan-test-one','feeder')""")
        await db.commit()
        yield BirdScanRepository(db)
        await db.execute("DELETE FROM detections WHERE frigate_event LIKE 'scan-test-%'")
        await db.commit()
    await close_db()


@pytest.mark.asyncio
async def test_enqueue_deduplicates_same_scene_and_never_replaces_active_scene(repo):
    first = await repo.enqueue("scan-test-one", **INPUT)
    assert first.status == "queued"
    assert await repo.enqueue(first.event_id, **INPUT) == first
    assert await repo.enqueue(first.event_id, **INPUT, force=True) == first
    for field, changed in (("content_sha256", "b" * 64), ("media_version", "replaced"), ("candidate_id", "other")):
        with pytest.raises(BirdScanBusyError):
            await repo.enqueue(first.event_id, **{**INPUT, field: changed}, force=True)
    assert await repo.get(first.event_id) == first
    assert await repo.pending_count() == 1
    assert await repo.list_pending(limit=1) == [first]


@pytest.mark.asyncio
async def test_completed_scene_requires_force_and_new_scene_gets_new_revision(repo):
    await repo.enqueue("scan-test-one", **INPUT)
    running = await repo.claim_next()
    assert running.status == "running"
    assert running.started_at
    assert {field: getattr(running, field) for field in INPUT} == INPUT
    assert await repo.complete(
        running.event_id,
        running.revision,
        expected_generation=running.generation,
        result_count=2,
        retained_previous=False,
    )
    done = await repo.get(running.event_id)
    assert done.status == "completed" and done.result_count == 2 and done.completed_at
    assert await repo.enqueue(running.event_id, **INPUT) == done
    retried = await repo.enqueue(running.event_id, **INPUT, force=True)
    assert retried.generation == running.generation
    assert retried.revision > running.revision
    assert retried.result_count is None and retried.started_at is None
    running = await repo.claim_next()
    assert await repo.fail(
        running.event_id, running.revision, expected_generation=running.generation, error="media_changed"
    )
    replaced = await repo.enqueue(running.event_id, **{**INPUT, "candidate_id": "frame-2", "frame_index": 2})
    assert replaced.revision > running.revision and replaced.candidate_id == "frame-2"


@pytest.mark.asyncio
async def test_recovery_fences_abandoned_worker_and_preserves_input(repo):
    await repo.enqueue("scan-test-one", **INPUT)
    running = await repo.claim_next()
    assert await repo.claim_next() is None
    assert await repo.recover_running() == 1
    assert await repo.recover_running() == 0
    recovered = await repo.claim_next()
    assert recovered.generation == running.generation
    assert recovered.revision > running.revision
    assert {field: getattr(recovered, field) for field in INPUT} == INPUT
    assert not await repo.complete(
        running.event_id,
        running.revision,
        expected_generation=running.generation,
        result_count=9,
        retained_previous=False,
    )
    assert not await repo.fail(
        running.event_id, running.revision, expected_generation=running.generation, error="scan_failed"
    )
    assert await repo.complete(
        recovered.event_id,
        recovered.revision,
        expected_generation=recovered.generation,
        result_count=0,
        retained_previous=True,
    )
    assert await repo.pending_count() == 0


@pytest.mark.asyncio
async def test_independent_connections_cannot_claim_the_same_job(repo):
    await repo.enqueue("scan-test-one", **INPUT)
    async with get_db() as second_db:
        results = await asyncio.gather(repo.claim_next(), BirdScanRepository(second_db).claim_next())
    assert sum(result is not None for result in results) == 1


@pytest.mark.asyncio
async def test_completion_can_share_transaction_and_roll_back(repo):
    await repo.enqueue("scan-test-one", **INPUT)
    job = await repo.claim_next()
    await repo.db.execute("BEGIN IMMEDIATE")
    assert await repo.complete(
        job.event_id,
        job.revision,
        expected_generation=job.generation,
        result_count=2,
        retained_previous=False,
        commit=False,
    )
    assert repo.db.in_transaction
    await repo.db.rollback()
    assert (await repo.get(job.event_id)).status == "running"
    assert await repo.complete(
        job.event_id,
        job.revision,
        expected_generation=job.generation,
        result_count=2,
        retained_previous=False,
        commit=False,
    )
    await repo.db.execute("UPDATE detections SET score=0.8 WHERE frigate_event=?", (job.event_id,))
    await repo.db.commit()
    assert (await repo.get(job.event_id)).status == "completed"


@pytest.mark.asyncio
async def test_deleted_detection_cannot_be_enqueued_or_completed(repo):
    await repo.enqueue("scan-test-one", **INPUT)
    job = await repo.claim_next()
    await repo.db.execute("DELETE FROM detections WHERE frigate_event=?", (job.event_id,))
    await repo.db.commit()
    assert await repo.get(job.event_id) is None
    assert not await repo.complete(
        job.event_id, job.revision, expected_generation=job.generation, result_count=2, retained_previous=False
    )
    with pytest.raises(BirdScanNotFoundError):
        await repo.enqueue(job.event_id, **INPUT)


@pytest.mark.asyncio
async def test_automatic_completion_cannot_replace_active_or_newer_revision(repo):
    assert await repo.record_automatic_completed(
        "scan-test-one",
        **INPUT,
        expected_revision=None,
        expected_generation=None,
        result_count=1,
        retained_previous=False,
    )
    first = await repo.get("scan-test-one")
    assert first.status == "completed"
    assert not await repo.record_automatic_completed(
        first.event_id,
        **INPUT,
        expected_revision=None,
        expected_generation=None,
        result_count=2,
        retained_previous=False,
    )
    await repo.enqueue(first.event_id, **INPUT, force=True)
    assert not await repo.record_automatic_completed(
        first.event_id,
        **INPUT,
        expected_revision=first.revision,
        expected_generation=first.generation,
        result_count=2,
        retained_previous=False,
    )
    manual = await repo.claim_next()
    assert await repo.complete(
        manual.event_id, manual.revision, expected_generation=manual.generation, result_count=3, retained_previous=False
    )
    assert not await repo.record_automatic_completed(
        first.event_id,
        **INPUT,
        expected_revision=first.revision,
        expected_generation=first.generation,
        result_count=2,
        retained_previous=False,
    )
    assert (await repo.get(first.event_id)).result_count == 3
    assert await repo.record_automatic_completed(
        first.event_id,
        **{**INPUT, "candidate_id": "frame-2"},
        expected_revision=(await repo.get(first.event_id)).revision,
        expected_generation=first.generation,
        result_count=0,
        retained_previous=True,
        commit=False,
    )
    await repo.db.rollback()
    assert (await repo.get(first.event_id)).result_count == 3


@pytest.mark.asyncio
async def test_invalid_count_is_rejected_and_raw_error_text_is_never_stored(repo):
    await repo.enqueue("scan-test-one", **INPUT)
    job = await repo.claim_next()
    with pytest.raises(ValueError):
        await repo.complete(
            job.event_id, job.revision, expected_generation=job.generation, result_count=-1, retained_previous=False
        )
    assert await repo.fail(
        job.event_id, job.revision, expected_generation=job.generation, error="https://token-secret.example"
    )
    assert (await repo.get(job.event_id)).error == "scan_failed"
    with pytest.raises(sqlite3.IntegrityError):
        await repo.db.execute("UPDATE bird_scan_jobs SET status='bogus'")
    await repo.db.rollback()


@pytest.mark.asyncio
async def test_concurrent_enqueue_admits_only_one_immutable_scene(repo):
    async with get_db() as second_db:
        results = await asyncio.gather(
            repo.enqueue("scan-test-one", **INPUT),
            BirdScanRepository(second_db).enqueue("scan-test-one", **{**INPUT, "image_ref": "other.jpg"}),
            return_exceptions=True,
        )
    assert sum(isinstance(result, BirdScanBusyError) for result in results) == 1
    winner = next(result for result in results if not isinstance(result, Exception))
    assert await repo.get("scan-test-one") == winner
    assert await repo.pending_count() == 1


@pytest.mark.asyncio
async def test_automatic_scan_started_during_manual_work_cannot_overwrite_finished_manual_result(repo):
    await repo.enqueue("scan-test-one", **INPUT)
    manual = await repo.claim_next()
    assert await repo.complete(
        manual.event_id, manual.revision, expected_generation=manual.generation, result_count=4, retained_previous=False
    )
    assert not await repo.record_automatic_completed(
        manual.event_id,
        **INPUT,
        expected_revision=manual.revision,
        expected_generation=manual.generation,
        result_count=1,
        retained_previous=False,
    )
    assert (await repo.get(manual.event_id)).result_count == 4


@pytest.mark.asyncio
async def test_automatic_completion_cannot_resurrect_deleted_detection(repo):
    await repo.db.execute("DELETE FROM detections WHERE frigate_event='scan-test-one'")
    await repo.db.commit()
    assert not await repo.record_automatic_completed(
        "scan-test-one",
        **INPUT,
        expected_revision=None,
        expected_generation=None,
        result_count=1,
        retained_previous=False,
    )
    assert await repo.get("scan-test-one") is None


@pytest.mark.asyncio
async def test_deleted_and_recreated_event_cannot_accept_old_worker_with_equal_revision(repo):
    await repo.enqueue("scan-test-one", **INPUT)
    old = await repo.claim_next()
    await repo.db.execute("DELETE FROM detections WHERE frigate_event=?", (old.event_id,))
    await repo.db.execute("""INSERT INTO detections(detection_time,detection_index,score,display_name,
        category_name,frigate_event,camera_name) VALUES ('2026-10-08 10:00:00',0,0.9,
        'Robin','Robin','scan-test-one','feeder')""")
    await repo.db.commit()
    queued = await repo.enqueue(old.event_id, **INPUT)
    new = await repo.claim_next()
    assert new.revision == old.revision
    assert new.generation != old.generation
    assert new.generation == queued.generation
    assert not await repo.complete(
        old.event_id, old.revision, expected_generation=old.generation, result_count=9, retained_previous=False
    )
    assert not await repo.fail(old.event_id, old.revision, expected_generation=old.generation, error="media_changed")
    assert await repo.complete(
        new.event_id, new.revision, expected_generation=new.generation, result_count=2, retained_previous=False
    )
    done = await repo.get(new.event_id)
    assert not await repo.record_automatic_completed(
        new.event_id,
        **INPUT,
        expected_revision=done.revision,
        expected_generation=old.generation,
        result_count=9,
        retained_previous=False,
    )
    assert (await repo.get(new.event_id)).result_count == 2


@pytest.mark.asyncio
async def test_automatic_publication_requires_complete_expected_identity(repo):
    with pytest.raises(ValueError, match="generation and revision"):
        await repo.record_automatic_completed(
            "scan-test-one",
            **INPUT,
            expected_revision=None,
            expected_generation="existing",
            result_count=0,
            retained_previous=False,
        )
    with pytest.raises(ValueError, match="generation and revision"):
        await repo.record_automatic_completed(
            "scan-test-one",
            **INPUT,
            expected_revision=1,
            expected_generation=None,
            result_count=0,
            retained_previous=False,
        )
    assert await repo.get("scan-test-one") is None
