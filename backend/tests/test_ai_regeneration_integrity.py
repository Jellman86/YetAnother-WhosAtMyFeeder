"""Forced analysis is an atomic replacement, with optimistic conversation protection."""

import asyncio
from contextlib import asynccontextmanager, closing
from datetime import datetime, timezone
import os
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiosqlite
import httpx
import pytest
import pytest_asyncio
from app.config import settings
from app.main import app
from app.routers import ai
from app.services.ai_service import AIAnalysisError
from app.repositories.detection_repository import DetectionRepository


@pytest_asyncio.fixture
async def regeneration(tmp_path, monkeypatch):
    path = tmp_path / "history.db"
    with closing(sqlite3.connect(os.environ["DB_PATH"])) as source, closing(sqlite3.connect(path)) as target:
        source.backup(target)
        target.execute("PRAGMA foreign_keys=ON")
        target.execute("DELETE FROM detections")
        target.execute(
            "INSERT INTO detections (detection_time,detection_index,score,display_name,category_name,frigate_event,camera_name,ai_analysis,ai_analysis_timestamp) VALUES (?,1,.9,'Robin','Robin','regen-fixture','camera','Original analysis','2026-09-01 10:00:00')",
            (datetime.now(timezone.utc).isoformat(),),
        )
        target.execute(
            "INSERT INTO ai_conversation_turns (frigate_event,role,content) VALUES ('regen-fixture','user','Original question')"
        )
        target.execute(
            "INSERT INTO ai_conversation_turns (frigate_event,role,content) VALUES ('regen-fixture','assistant','Original answer')"
        )
        target.commit()
    controls = SimpleNamespace(fail_delete=False, cancel_update=False)

    @asynccontextmanager
    async def database():
        async with aiosqlite.connect(path) as db:
            await db.execute("PRAGMA foreign_keys=ON")
            if controls.cancel_update:
                execute = db.execute

                def cancelled_write(sql, parameters=()):
                    if sql.startswith("UPDATE detections SET ai_analysis"):

                        async def cancel_after_update():
                            await execute(sql, parameters)
                            raise asyncio.CancelledError()

                        return cancel_after_update()
                    return execute(sql, parameters)

                db.execute = cancelled_write
            if controls.fail_delete:
                await db.set_authorizer(
                    lambda op, table, *_: (
                        sqlite3.SQLITE_DENY
                        if op == sqlite3.SQLITE_DELETE and table == "ai_conversation_turns"
                        else sqlite3.SQLITE_OK
                    )
                )
            yield db

    monkeypatch.setattr(ai, "get_db", database)
    monkeypatch.setattr(settings.auth, "enabled", False)
    monkeypatch.setattr(settings.public_access, "enabled", False)
    snapshot = AsyncMock(return_value=b"fixture-image")
    provider = AsyncMock(return_value="Replacement analysis")
    monkeypatch.setattr(ai.frigate_client, "get_snapshot", snapshot)
    monkeypatch.setattr(ai.ai_service, "analyze_detection", provider)

    async def state():
        async with database() as db:
            row = await (
                await db.execute(
                    "SELECT ai_analysis,ai_analysis_timestamp FROM detections WHERE frigate_event='regen-fixture'"
                )
            ).fetchone()
            turns = await (
                await db.execute(
                    "SELECT role,content FROM ai_conversation_turns WHERE frigate_event='regen-fixture' ORDER BY id"
                )
            ).fetchall()
            return row, turns

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as client:
        yield SimpleNamespace(
            client=client,
            provider=provider,
            snapshot=snapshot,
            database=database,
            controls=controls,
            state=state,
            route="/api/events/regen-fixture/analyze?force=true&use_clip=false",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["image", "rate_limit", "empty"])
async def test_failed_regeneration_preserves_analysis_and_full_conversation(regeneration, failure):
    r = regeneration
    before = await r.state()
    if failure == "image":
        r.snapshot.return_value = None
    elif failure == "rate_limit":
        r.provider.return_value = AIAnalysisError("Rate limited", http_status_hint=429, retryable=True)
    else:
        r.provider.return_value = None
    response = await r.client.post(r.route)
    assert response.status_code == (429 if failure == "rate_limit" else 502)
    assert await r.state() == before


@pytest.mark.asyncio
async def test_successful_regeneration_replaces_analysis_and_clears_conversation_together(regeneration):
    r = regeneration
    response = await r.client.post(r.route)
    assert response.status_code == 200
    row, turns = await r.state()
    assert row[0] == "Replacement analysis"
    assert row[1] != "2026-09-01 10:00:00"
    assert turns == []


@pytest.mark.asyncio
async def test_chat_accepted_during_provider_work_prevents_stale_regeneration(regeneration, monkeypatch):
    r = regeneration
    entered, release = asyncio.Event(), asyncio.Event()

    async def pending(**kwargs):
        entered.set()
        await release.wait()
        return "Stale replacement"

    r.provider.side_effect = pending
    monkeypatch.setattr(ai.ai_service, "chat_detection", AsyncMock(return_value="New reply"))
    request = asyncio.create_task(r.client.post(r.route))
    await asyncio.wait_for(entered.wait(), 1)
    try:
        assert (
            await r.client.post("/api/events/regen-fixture/conversation", json={"message": "New question"})
        ).status_code == 200
    finally:
        release.set()
    response = await request
    assert response.status_code == 409
    row, turns = await r.state()
    assert row[0] == "Original analysis"
    assert [text for _, text in turns] == ["Original question", "Original answer", "New question", "New reply"]


@pytest.mark.asyncio
async def test_overlapping_regeneration_has_one_winner(regeneration):
    r = regeneration
    entered, release = asyncio.Event(), asyncio.Event()

    async def provider(**kwargs):
        if not entered.is_set():
            entered.set()
            await release.wait()
            return "Stale replacement"
        return "Winning replacement"

    r.provider.side_effect = provider
    first = asyncio.create_task(r.client.post(r.route))
    await asyncio.wait_for(entered.wait(), 1)
    try:
        assert (await r.client.post(r.route)).status_code == 200
    finally:
        release.set()
    assert (await first).status_code == 409
    row, turns = await r.state()
    assert row[0] == "Winning replacement"
    assert turns == []


@pytest.mark.asyncio
async def test_cancelled_provider_preserves_conversation(regeneration):
    r = regeneration
    before = await r.state()
    entered = asyncio.Event()

    async def pending(**kwargs):
        entered.set()
        await asyncio.Event().wait()

    r.provider.side_effect = pending
    request = asyncio.create_task(r.client.post(r.route))
    await asyncio.wait_for(entered.wait(), 1)
    request.cancel()
    with pytest.raises(asyncio.CancelledError):
        await request
    assert await r.state() == before


@pytest.mark.asyncio
async def test_failed_conversation_cleanup_rolls_back_analysis_replacement(regeneration):
    r = regeneration
    before = await r.state()
    r.controls.fail_delete = True
    response = await r.client.post(r.route)
    assert response.status_code == 500
    assert await r.state() == before
    r.provider.assert_awaited_once()


@pytest.mark.asyncio
async def test_late_chat_reply_cannot_repopulate_a_regenerated_conversation(regeneration, monkeypatch):
    r = regeneration
    entered, release = asyncio.Event(), asyncio.Event()

    async def pending(prompt):
        entered.set()
        await release.wait()
        return "Reply to the old analysis"

    monkeypatch.setattr(ai.ai_service, "chat_detection", AsyncMock(side_effect=pending))
    chat = asyncio.create_task(
        r.client.post("/api/events/regen-fixture/conversation", json={"message": "Pending question"})
    )
    await asyncio.wait_for(entered.wait(), 1)
    try:
        assert (await r.client.post(r.route)).status_code == 200
    finally:
        release.set()
    assert (await chat).status_code == 409
    row, turns = await r.state()
    assert row[0] == "Replacement analysis"
    assert turns == []


@pytest.mark.asyncio
async def test_cancellation_after_database_update_rolls_back_both_changes(regeneration):
    r = regeneration
    before = await r.state()
    r.controls.cancel_update = True
    async with r.database() as db:
        repo = DetectionRepository(db)
        revision = await repo.get_ai_analysis_revision("regen-fixture")
        assert revision is not None
        with pytest.raises(asyncio.CancelledError):
            await repo.update_ai_analysis(
                "regen-fixture", "Cancelled analysis", expected_revision=revision, reset_conversation=True
            )
        await db.execute("BEGIN IMMEDIATE")
        await db.rollback()
    assert await r.state() == before


@pytest.mark.asyncio
async def test_first_analysis_preserves_existing_conversation(regeneration):
    r = regeneration
    async with r.database() as db:
        await db.execute("UPDATE detections SET ai_analysis=NULL,ai_analysis_timestamp=NULL")
        await db.commit()
    _, before_turns = await r.state()
    response = await r.client.post(r.route.replace("force=true", "force=false"))
    assert response.status_code == 200
    row, turns = await r.state()
    assert row[0] == "Replacement analysis"
    assert turns == before_turns


@pytest.mark.parametrize("language", ["en", "es", "fr", "de", "ja", "zh", "ru", "pt", "it"])
def test_conflict_message_is_available_in_every_backend_locale(language):
    path = Path(__file__).resolve().parents[1] / "locales" / f"{language}.json"
    value = json.loads(path.read_text())["errors"]["ai"]["context_changed"]
    assert isinstance(value, str) and value.strip()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    ["display_name='Cardinal'", "temperature=30", "weather_condition='Rain'", "detection_time='2026-09-02 10:00:00'"],
)
@pytest.mark.parametrize("conversation", [False, True])
async def test_prompt_context_edits_reject_late_provider_result(regeneration, monkeypatch, change, conversation):
    r = regeneration
    before = await r.state()
    entered, release = asyncio.Event(), asyncio.Event()

    async def pending(*args, **kwargs):
        entered.set()
        await release.wait()
        return "Stale provider result"

    if conversation:
        monkeypatch.setattr(ai.ai_service, "chat_detection", pending)
        request = asyncio.create_task(
            r.client.post("/api/events/regen-fixture/conversation", json={"message": "New question"})
        )
    else:
        r.provider.side_effect = pending
        request = asyncio.create_task(r.client.post(r.route))
    await asyncio.wait_for(entered.wait(), 2)
    try:
        async with r.database() as db:
            await db.execute(f"UPDATE detections SET {change} WHERE frigate_event='regen-fixture'")
            await db.commit()
    finally:
        release.set()
    response = await request
    assert response.status_code == 409
    row, turns = await r.state()
    assert row == before[0]
    assert turns[:2] == before[1]
    assert all(content != "Stale provider result" for _, content in turns)


@pytest.mark.asyncio
async def test_unrelated_favorite_edit_does_not_invalidate_prompt(regeneration):
    r = regeneration
    entered, release = asyncio.Event(), asyncio.Event()

    async def pending(**kwargs):
        entered.set()
        await release.wait()
        return "Current context result"

    r.provider.side_effect = pending
    request = asyncio.create_task(r.client.post(r.route))
    await asyncio.wait_for(entered.wait(), 2)
    try:
        async with r.database() as db:
            await DetectionRepository(db).favorite_detection("regen-fixture")
    finally:
        release.set()
    assert (await request).status_code == 200
