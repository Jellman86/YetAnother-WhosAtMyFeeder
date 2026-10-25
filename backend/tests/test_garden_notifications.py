"""Garden alerts opt in independently, claim known visits durably, and recheck privacy."""

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from app.config import settings
from app.config_models import FrigateSettings
from app.database import init_db, close_db, get_db
from app.models.garden import GardenIdentification
from app.repositories.garden_repository import GardenRepository
from app.utils.api_datetime import utc_naive_now


def test_garden_alerts_default_off_with_no_inherited_bird_channels():
    config = FrigateSettings(frigate_url="http://frigate")
    assert config.garden_notifications_enabled is False
    assert config.garden_notification_channels == []
    with pytest.raises(ValueError):
        FrigateSettings(frigate_url="http://frigate", garden_notification_channels=["unknown"])


@pytest_asyncio.fixture
async def history(monkeypatch):
    monkeypatch.setattr(settings.system, "beta_garden_animals", True)
    monkeypatch.setattr(settings.frigate, "garden_notifications_enabled", True)
    monkeypatch.setattr(settings.frigate, "garden_notification_channels", ["telegram"])
    monkeypatch.setattr(settings.frigate, "garden_cameras", ["patio"])
    await init_db()
    async with get_db() as db:
        await db.execute("DELETE FROM garden_captures")
        await db.commit()
    yield
    await close_db()


async def named(event="cat", seconds=0, name="Domestic cat"):
    now = utc_naive_now() - timedelta(seconds=seconds)
    async with get_db() as db:
        repo = GardenRepository(db)
        await repo.capture(event, "patio", "cat", now.isoformat(), True)
        item = next(item for item in await repo.list("pending", 128, 0) if item.frigate_event == event)
        await repo.review(item.id, "confirmed")
        identity = GardenIdentification(
            outcome="suggestion",
            reason="garden",
            review="accepted",
            automatic=True,
            species_id=101,
            name=name,
            score=0.95,
            country="GBR",
            variant="4.0.3a",
            provider="cpu",
            devices=["CPU"],
            model_sha256="a" * 64,
            package_sha256="b" * 64,
            image_sha256="c" * 64,
            output_index=0,
            input_kind="tracked_crop",
            frame_size=(640, 480),
            identified_at=now.isoformat(),
        )
        assert await repo.save_identification(await repo.get(item.id), identity)
        return item.id


@pytest.mark.asyncio
async def test_selected_garden_channel_ignores_bird_modes_filters_and_restart_replays(history, monkeypatch):
    from app.services.garden_notifications import GardenNotificationService

    monkeypatch.setattr(settings.notifications, "mode", "silent")
    monkeypatch.setattr(settings.notifications.filters, "audio_confirmed_only", True)
    sender = AsyncMock(return_value=True)
    service = GardenNotificationService(sender=sender)
    first = await named("first", 50)
    await service.deliver(first)
    await service.deliver(first)
    second = await named("second", 0)
    await GardenNotificationService(sender=sender).deliver(second)
    assert sender.await_count == 1
    assert sender.call_args.args[0] == "telegram"
    assert (await service.status_counts())["sent"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["disabled", "beta", "camera", "person", "dismissed", "old", "unnamed"])
async def test_queued_delivery_rechecks_opt_in_named_state_freshness_and_privacy(history, monkeypatch, change):
    from app.services.garden_notifications import GardenNotificationService

    capture_id = await named(seconds=600 if change == "old" else 0)
    if change == "disabled":
        monkeypatch.setattr(settings.frigate, "garden_notifications_enabled", False)
    if change == "beta":
        monkeypatch.setattr(settings.system, "beta_garden_animals", False)
    if change == "camera":
        monkeypatch.setattr(settings.frigate, "garden_cameras", [])
    async with get_db() as db:
        repo = GardenRepository(db)
        if change == "person":
            await repo.block_capture(capture_id)
        if change == "dismissed":
            await repo.review(capture_id, "dismissed")
        if change == "unnamed":
            await db.execute("DELETE FROM garden_identifications WHERE capture_id=?", (capture_id,))
            await db.commit()
    sender = AsyncMock(return_value=True)
    await GardenNotificationService(sender=sender).deliver(capture_id)
    sender.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_attempt_is_not_replayed_and_new_visit_is_independent(history):
    from app.services.garden_notifications import GardenNotificationService

    sender = AsyncMock(return_value=False)
    service = GardenNotificationService(sender=sender)
    older = await named("older", 200)
    await service.deliver(older)
    await GardenNotificationService(sender=sender).deliver(older)
    newer = await named("newer", 0)
    await service.deliver(newer)
    assert sender.await_count == 2
    assert (await service.status_counts())["failed"] == 2


@pytest.mark.asyncio
async def test_concurrent_captures_claim_one_channel_attempt_for_the_known_visit(history):
    import asyncio
    from app.services.garden_notifications import GardenNotificationService

    first, second = await named("first", 30), await named("second", 0)
    sender = AsyncMock(return_value=True)
    service = GardenNotificationService(sender=sender)
    await asyncio.gather(service.deliver(first), service.deliver(second))
    assert sender.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("channel", ["discord", "telegram", "pushover"])
async def test_text_transports_use_explicit_credentials_without_bird_enable_flags_or_images(
    history, monkeypatch, channel
):
    import json
    import httpx
    from app.services.garden_notification_transport import send_garden_notification
    from app.services.notification_service import notification_service

    monkeypatch.setattr(settings.notifications.discord, "enabled", False)
    monkeypatch.setattr(
        settings.notifications.discord, "webhook_url", "https://discord.test/webhook/private-token?thread_id=123"
    )
    monkeypatch.setattr(settings.notifications.telegram, "enabled", False)
    monkeypatch.setattr(settings.notifications.telegram, "bot_token", "private-test-token")
    monkeypatch.setattr(settings.notifications.telegram, "chat_id", "owner-chat")
    monkeypatch.setattr(settings.notifications.pushover, "enabled", False)
    monkeypatch.setattr(settings.notifications.pushover, "api_token", "private-test-token")
    monkeypatch.setattr(settings.notifications.pushover, "user_key", "owner-key")
    monkeypatch.setattr(settings.notifications, "instance_url", "https://owner.test/feeder")
    monkeypatch.setattr(settings.notifications, "link_target", "frigate")
    capture_id = await named(name="Cat <b>& text")
    async with get_db() as db:
        capture = await GardenRepository(db).get(capture_id)
    requests = []

    async def receive(request):
        requests.append(request)
        return httpx.Response(200, json={"ok": True, "status": 1, "id": "message-1"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(receive)) as client:
        monkeypatch.setattr(notification_service, "client", client)
        assert await send_garden_notification(channel, capture)
    request = requests[0]
    body = request.content.decode()
    assert "snapshot" not in body and "attachment" not in body and "sendPhoto" not in str(request.url)
    assert "owner.test" in body and "frigate" not in body
    assert "Named automatically" in body or "Named+automatically" in body
    if channel == "telegram":
        payload = json.loads(body)
        assert "&lt;b&gt;&amp;" in payload["text"]
        assert payload["link_preview_options"]["is_disabled"] is True
    if channel == "discord":
        assert request.url.params["wait"] == "true"
        assert request.url.params["thread_id"] == "123"
        assert json.loads(body)["allowed_mentions"] == {"parse": []}


@pytest.mark.asyncio
@pytest.mark.parametrize("oauth", [False, True])
async def test_email_is_text_only_escaped_and_does_not_use_the_bird_template(history, monkeypatch, oauth):
    from app.services.garden_notification_transport import send_garden_notification
    from app.services.smtp_service import smtp_service

    cfg = settings.notifications.email
    for key, value in {
        "enabled": False,
        "use_oauth": oauth,
        "oauth_provider": "gmail",
        "to_email": "owner@example.test",
        "from_email": "sender@example.test",
        "smtp_host": "smtp.example.test",
        "include_snapshot": True,
    }.items():
        monkeypatch.setattr(cfg, key, value)
    sender = AsyncMock(return_value=True)
    monkeypatch.setattr(smtp_service, "send_email_oauth" if oauth else "send_email_password", sender)
    capture_id = await named(name="Cat <b>& text")
    async with get_db() as db:
        capture = await GardenRepository(db).get(capture_id)
    assert await send_garden_notification("email", capture)
    data = sender.call_args.kwargs
    assert data["image_data"] is None
    assert "Cat &lt;b&gt;&amp; text" in data["html_body"]
    assert "Garden animal" in data["subject"]
    assert "bird" not in data["html_body"].lower()


def test_notification_migration_is_reversible_and_keeps_capture_history(tmp_path, monkeypatch):
    import sqlite3
    from pathlib import Path
    from alembic import command
    from alembic.config import Config

    backend = Path(__file__).resolve().parents[1]
    database = tmp_path / "garden-migration.db"
    monkeypatch.setenv("DB_PATH", str(database))
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "migrations"))
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    with sqlite3.connect(database) as db:
        db.execute(
            "INSERT INTO garden_captures(id,event_key,camera,label,observed_at,status,has_snapshot) VALUES(?,?,?,?,?,?,?)",
            ("a" * 32, "b" * 64, "patio", "cat", "2026-10-25T00:00:00", "confirmed", 1),
        )
        db.execute(
            "INSERT INTO garden_notification_attempts(capture_id,channel,attempted_at,state) VALUES(?,?,?,?)",
            ("a" * 32, "telegram", "2026-10-25T00:00:00", "sent"),
        )
        original = db.execute("SELECT * FROM garden_captures").fetchall()
    command.downgrade(config, "b72d91a4e630")
    command.downgrade(config, "b72d91a4e630")
    command.upgrade(config, "head")
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT * FROM garden_captures").fetchall() == original
        assert db.execute("SELECT COUNT(*) FROM garden_notification_attempts").fetchone()[0] == 0
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


@pytest.mark.asyncio
async def test_saved_status_is_owner_only_and_contains_no_credentials(history, monkeypatch):
    import httpx
    from app.main import app

    monkeypatch.setattr(settings.auth, "enabled", False)
    monkeypatch.setattr(settings.public_access, "enabled", False)
    monkeypatch.setattr(settings.notifications.telegram, "bot_token", "private-status-token")
    monkeypatch.setattr(settings.notifications.telegram, "chat_id", "private-chat")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/garden/notifications")
        assert response.status_code == 200, response.text
        assert response.json()["configured"]["telegram"] is True
        assert "private-status-token" not in response.text and "private-chat" not in response.text
        monkeypatch.setattr(settings.auth, "enabled", True)
        monkeypatch.setattr(settings.public_access, "enabled", True)
        assert (await client.get("/api/garden/notifications")).status_code in {401, 403}


@pytest.mark.parametrize("age,expected", [(-0.001, False), (0, True), (300, True), (300.001, False)])
def test_delivery_freshness_has_inclusive_five_minute_boundary(age, expected):
    from datetime import datetime

    from app.repositories.garden_repository import GardenCapture
    from app.services.garden_notifications import eligible

    now = datetime(2026, 10, 25, 12)
    identity = GardenIdentification(
        outcome="suggestion",
        reason="garden",
        review="accepted",
        name="Domestic cat",
        species_id=101,
        country="GBR",
        variant="4.0.3a",
        provider="cpu",
        devices=["CPU"],
        model_sha256="a" * 64,
        package_sha256="b" * 64,
        image_sha256="c" * 64,
        output_index=0,
        input_kind="tracked_crop",
        frame_size=(640, 480),
        identified_at=now.isoformat(),
    )
    capture = GardenCapture(
        id="cat",
        frigate_event="cat",
        camera="patio",
        label="cat",
        observed_at=(now - timedelta(seconds=age)).isoformat(),
        status="confirmed",
        has_snapshot=True,
        reviewed_at=None,
        identification=identity,
    )
    assert eligible(capture, enabled=True, cameras=["patio"], now=now) is expected


@pytest.mark.asyncio
@pytest.mark.parametrize("action,attempts", [("accept", 1), ("dismiss", 0)])
async def test_only_accepting_a_species_schedules_an_owner_review_alert(monkeypatch, action, attempts):
    from app.routers import garden

    saved = object()
    schedule = AsyncMock()
    monkeypatch.setattr(garden.garden_identification_service, "review", AsyncMock())
    monkeypatch.setattr(garden.garden_identification_service, "invalidate_photo_checks", lambda: None)
    monkeypatch.setattr(garden.garden_capture_service, "get", AsyncMock(return_value=saved))
    monkeypatch.setattr(garden, "_response", AsyncMock(return_value=saved))
    monkeypatch.setattr(garden.garden_notification_service, "schedule", schedule)
    assert await garden.review_identification("cat", action) is saved
    assert schedule.await_count == attempts
