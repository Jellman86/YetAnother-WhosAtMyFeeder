"""Removing a photo choice removes every framing behind its thumbnail, in one step (#1107)."""

from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.database import get_db
from app.main import app
from app.repositories.detection_repository import Detection, DetectionRepository
from app.routers import proxy
from app.utils.api_datetime import utc_naive_now

FRAME = 3


def candidate(event, name, source_mode, *, frame_index=FRAME, selected=False, crop_box=None, content="a"):
    return {
        "candidate_id": f"{event}__{name}",
        "frame_index": frame_index,
        "clip_variant": "event",
        "source_mode": source_mode,
        "crop_box": crop_box,
        "ranking_score": 0.5,
        "selected": selected,
        "image_ref": f"{event}__{name}__image",
        "thumbnail_ref": f"{event}__{name}__thumb",
        "snapshot_source": f"hq_candidate_{name}",
        "content_sha256": (content + name).ljust(64, "0")[:64],
    }


def frame_candidates(event, *, crop_content="a", **selected):
    return [
        candidate(event, "saved", "model_crop", frame_index=1, selected=selected.get("saved", True)),
        candidate(event, "crop", "model_crop", crop_box=[10, 10, 60, 60], content=crop_content),
        candidate(event, "hint", "frigate_hint_crop", crop_box=[8, 8, 64, 64], selected=selected.get("hint", False)),
        candidate(event, "scene", "full_frame", selected=selected.get("scene", False)),
        candidate(event, "evidence", "model_observation", crop_box=[10, 10, 60, 60]),
        candidate(event, "earlier", "retained_photo", frame_index=0),
    ]


@pytest_asyncio.fixture
async def capture(history_pool, monkeypatch):
    monkeypatch.setattr(settings.auth, "enabled", False)
    monkeypatch.setattr(settings.public_access, "enabled", False)
    event = "photo-removal-" + uuid4().hex[:12]
    async with get_db() as db:
        repo = DetectionRepository(db)
        await repo.create(
            Detection(
                detection_time=utc_naive_now(),
                detection_index=0,
                score=0.9,
                display_name="House Finch",
                category_name="House Finch",
                frigate_event=event,
                camera_name="test",
            )
        )
        await repo.replace_snapshot_candidates(event, frame_candidates(event))
    status = proxy.SnapshotStatusResponse(
        event_id=event,
        cached=True,
        source="hq_candidate_saved",
        high_quality_event_snapshots_enabled=True,
        high_quality_bird_crop_enabled=True,
        already_hq_bird_crop=True,
        can_generate_hq_bird_crop=True,
    )
    monkeypatch.setattr(proxy, "_build_snapshot_status", AsyncMock(return_value=status))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield event, client, status
    async with get_db() as db:
        await db.execute("DELETE FROM detections WHERE frigate_event=?", (event,))
        await db.commit()


def ident(event, name):
    return f"{event}__{name}"


async def patch(client, event, name, **body):
    return await client.patch(f"/api/frigate/{event}/snapshot/candidates/{ident(event, name)}", json=body)


async def dismissals(event):
    async with get_db() as db:
        async with db.execute(
            "SELECT candidate_id, content_identity FROM snapshot_candidate_dismissals WHERE frigate_event=? ORDER BY 1",
            (event,),
        ) as cursor:
            return [tuple(row) for row in await cursor.fetchall()]


def hidden(response):
    return {row["candidate_id"] for row in response.json()["candidates"] if row["photo_hidden"]}


@pytest.mark.asyncio
async def test_removing_a_folded_choice_hides_every_framing_and_reports_only_what_it_removed(capture):
    event, client, _ = capture
    earlier = await patch(client, event, "hint", dismissed=True)
    assert earlier.status_code == 200, earlier.text
    assert earlier.json()["changed_dismissals"] == [
        {"candidate_id": ident(event, "hint"), "content_identity": frame_candidates(event)[2]["content_sha256"]}
    ]

    removed = await patch(
        client, event, "crop", dismissed=True, companion_candidate_ids=[ident(event, "hint"), ident(event, "scene")]
    )

    assert removed.status_code == 200, removed.text
    assert hidden(removed) == {ident(event, "crop"), ident(event, "hint"), ident(event, "scene")}
    by_name = {row["candidate_id"]: row["content_sha256"] for row in frame_candidates(event)}
    assert removed.json()["changed_dismissals"] == [
        {"candidate_id": ident(event, "crop"), "content_identity": by_name[ident(event, "crop")]},
        {"candidate_id": ident(event, "scene"), "content_identity": by_name[ident(event, "scene")]},
    ]


@pytest.mark.asyncio
async def test_undo_restores_what_the_removal_hid_and_keeps_an_earlier_removal(capture):
    event, client, _ = capture
    await patch(client, event, "hint", dismissed=True)
    removed = await patch(
        client, event, "crop", dismissed=True, companion_candidate_ids=[ident(event, "hint"), ident(event, "scene")]
    )
    targets = removed.json()["changed_dismissals"]

    restored = await patch(
        client,
        event,
        "crop",
        dismissed=False,
        companion_candidate_ids=[target["candidate_id"] for target in targets[1:]],
        expected_content_identities={target["candidate_id"]: target["content_identity"] for target in targets},
    )

    assert restored.status_code == 200, restored.text
    assert hidden(restored) == {ident(event, "hint")}
    assert restored.json()["changed_dismissals"] == targets


@pytest.mark.asyncio
async def test_undo_never_clears_a_removal_of_the_replacement_pixels(capture):
    event, client, _ = capture
    removed = await patch(client, event, "crop", dismissed=True, companion_candidate_ids=[ident(event, "scene")])
    targets = removed.json()["changed_dismissals"]
    async with get_db() as db:
        await DetectionRepository(db).replace_snapshot_candidates(event, frame_candidates(event, crop_content="b"))
    again = await patch(client, event, "crop", dismissed=True)
    assert again.status_code == 200, again.text

    restored = await patch(
        client,
        event,
        "crop",
        dismissed=False,
        companion_candidate_ids=[ident(event, "scene")],
        expected_content_identities={target["candidate_id"]: target["content_identity"] for target in targets},
    )

    assert restored.status_code == 200, restored.text
    assert hidden(restored) == {ident(event, "crop")}
    assert restored.json()["changed_dismissals"] == [targets[1]]


@pytest.mark.asyncio
async def test_restoring_a_framing_that_is_already_back_succeeds(capture):
    event, client, _ = capture
    await patch(client, event, "crop", dismissed=True)

    restored = await patch(client, event, "crop", dismissed=False, companion_candidate_ids=[ident(event, "scene")])

    assert restored.status_code == 200, restored.text
    assert hidden(restored) == set()
    assert [target["candidate_id"] for target in restored.json()["changed_dismissals"]] == [ident(event, "crop")]


@pytest.mark.asyncio
@pytest.mark.parametrize("member", ["hint", "scene"])
async def test_a_choice_holding_the_saved_photograph_is_not_removed_at_all(capture, member):
    event, client, _ = capture
    async with get_db() as db:
        await DetectionRepository(db).replace_snapshot_candidates(
            event, frame_candidates(event, saved=False, **{member: True})
        )

    refused = await patch(
        client, event, "crop", dismissed=True, companion_candidate_ids=[ident(event, "hint"), ident(event, "scene")]
    )

    assert refused.status_code == 409
    assert await dismissals(event) == []


@pytest.mark.asyncio
async def test_a_choice_holding_the_current_photograph_is_not_removed_even_when_no_row_is_marked(capture):
    event, client, status = capture
    async with get_db() as db:
        await DetectionRepository(db).replace_snapshot_candidates(event, frame_candidates(event, saved=False))
    status.source = "hq_candidate_scene"

    refused = await patch(client, event, "crop", dismissed=True, companion_candidate_ids=[ident(event, "scene")])

    assert refused.status_code == 409
    assert await dismissals(event) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "body", "status_code"),
    [
        ("crop", {"companion_candidate_ids": ["{crop}"]}, 400),
        ("crop", {"companion_candidate_ids": ["{hint}", "{hint}"]}, 400),
        ("crop", {"companion_candidate_ids": [""]}, 422),
        ("crop", {"companion_candidate_ids": ["{saved}"]}, 400),
        ("crop", {"companion_candidate_ids": ["{evidence}"]}, 400),
        ("evidence", {}, 400),
        ("earlier", {"companion_candidate_ids": ["{crop}"]}, 400),
        ("crop", {"companion_candidate_ids": ["as-recorded"]}, 400),
        ("crop", {"companion_candidate_ids": [f"extra-{index}" for index in range(17)]}, 422),
        ("crop", {"companion_candidate_ids": ["another-capture__crop"]}, 404),
        ("crop", {"expected_content_identities": {"{crop}": "a"}}, 400),
    ],
)
async def test_a_removal_that_is_not_one_frames_photographs_changes_nothing(capture, name, body, status_code):
    event, client, _ = capture
    names = {key: ident(event, key) for key in ("crop", "hint", "saved", "evidence")}
    if "companion_candidate_ids" in body:
        body = {**body, "companion_candidate_ids": [value.format(**names) for value in body["companion_candidate_ids"]]}
    if "expected_content_identities" in body:
        body = {
            **body,
            "expected_content_identities": {
                key.format(**names): value for key, value in body["expected_content_identities"].items()
            },
        }

    refused = await patch(client, event, name, dismissed=True, **body)

    assert refused.status_code == status_code, refused.text
    assert await dismissals(event) == []


@pytest.mark.asyncio
async def test_the_camera_snapshot_is_removed_on_its_own(capture):
    event, client, _ = capture
    path = f"/api/frigate/{event}/snapshot/candidates/as-recorded"

    refused = await client.patch(path, json={"dismissed": True, "companion_candidate_ids": [ident(event, "crop")]})
    removed = await client.patch(path, json={"dismissed": True})
    restored = await client.patch(path, json={"dismissed": False})

    assert refused.status_code == 400
    assert removed.status_code == 200, removed.text
    assert removed.json()["changed_dismissals"] == [{"candidate_id": "as-recorded", "content_identity": "as-recorded"}]
    assert restored.json()["changed_dismissals"] == removed.json()["changed_dismissals"]
    assert await dismissals(event) == []


@pytest.mark.asyncio
async def test_restore_targets_must_belong_to_the_choice_being_restored(capture):
    event, client, _ = capture
    await patch(client, event, "crop", dismissed=True)

    refused = await patch(
        client, event, "crop", dismissed=False, expected_content_identities={ident(event, "scene"): "anything"}
    )

    assert refused.status_code == 400
    assert [row[0] for row in await dismissals(event)] == [ident(event, "crop")]
