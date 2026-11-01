"""Garden alerts opt in independently, stay fresh from the naming decision, and recheck privacy."""

import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.config_models import FrigateSettings
from app.database import init_db, close_db, get_db
from app.models.garden import GardenAutomaticCheck, GardenIdentification, GardenPresenceMass
from app.repositories.garden_repository import GardenCapture, GardenRepository
from app.utils.api_datetime import utc_naive_now

NOW = datetime(2026, 10, 25, 12)


def identity(*, automatic: bool = True, name: str = "Domestic cat", review: str = "accepted") -> GardenIdentification:
    return GardenIdentification(
        outcome="suggestion",
        reason="garden",
        review=review,
        automatic=automatic,
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
        identified_at=NOW.isoformat(),
    )


def check(checked_at: datetime) -> GardenAutomaticCheck:
    return GardenAutomaticCheck(
        outcome="animal",
        checked_at=checked_at.isoformat(),
        policy_version=1,
        mass=GardenPresenceMass(bird=0, animal=1, human=0, non_animal=0, other=0),
        image_sha256="c" * 64,
        variant="4.0.3a",
        model_sha256="a" * 64,
        package_sha256="b" * 64,
        devices=["CPU"],
    )


def snapshot(*, observed_ago: float, checked_ago: float | None, automatic: bool = True) -> GardenCapture:
    return GardenCapture(
        id="c" * 32,
        frigate_event="cat",
        camera="patio",
        label="cat",
        observed_at=(NOW - timedelta(seconds=observed_ago)).isoformat(),
        status="confirmed",
        has_snapshot=True,
        reviewed_at=None,
        identification=identity(automatic=automatic),
        automatic_check=check(NOW - timedelta(seconds=checked_ago)) if checked_ago is not None else None,
    )


# --- Settings -----------------------------------------------------------------------------------


def test_garden_alerts_default_off_following_bird_channels_with_photos():
    config = FrigateSettings(frigate_url="http://frigate")
    assert config.garden_notifications_enabled is False
    assert config.garden_notification_channels == []
    assert config.garden_notifications_use_bird_channels is True
    assert config.garden_notifications_include_photo is True
    with pytest.raises(ValueError):
        FrigateSettings(frigate_url="http://frigate", garden_notification_channels=["unknown"])


@pytest.mark.parametrize(
    "saved,follows_birds",
    [
        ({}, True),
        ({"garden_notification_channels": []}, True),
        ({"garden_notification_channels": ["telegram"]}, False),
        ({"garden_notification_channels": ["telegram"], "garden_notifications_use_bird_channels": True}, True),
        ({"garden_notification_channels": [], "garden_notifications_use_bird_channels": False}, False),
    ],
)
def test_saved_configs_without_the_mode_keep_their_explicit_channels(saved, follows_birds):
    config = FrigateSettings(frigate_url="http://frigate", **saved)
    assert config.garden_notifications_use_bird_channels is follows_birds


# --- Eligibility ---------------------------------------------------------------------------------


@pytest.mark.parametrize("decision_age,expected", [(-0.001, False), (0, True), (300, True), (300.001, False)])
def test_freshness_is_measured_from_the_naming_decision_with_an_inclusive_five_minute_bound(decision_age, expected):
    from app.services.garden_notifications import decision_time, eligible

    capture = snapshot(observed_ago=540 + decision_age, checked_ago=decision_age)
    assert (
        eligible(capture, enabled=True, cameras=["patio"], decided_at=decision_time(capture, None), now=NOW) is expected
    )


@pytest.mark.parametrize("naming_lag", [417, 631])
def test_measured_naming_lag_now_qualifies_where_the_old_300_second_sighting_window_dropped_it(naming_lag):
    from app.services.garden_notifications import decision_time, eligible

    capture = snapshot(observed_ago=naming_lag, checked_ago=1)
    # The previous rule measured from the sighting, which this lag always exceeded.
    assert naming_lag > 300
    assert eligible(capture, enabled=True, cameras=["patio"], decided_at=decision_time(capture, None), now=NOW)


@pytest.mark.parametrize(
    "sighting_age,expected", [(-0.001, False), (0, True), (2 * 3600, True), (2 * 3600 + 0.001, False)]
)
def test_an_old_sighting_is_history_however_recently_it_was_named(sighting_age, expected):
    from app.services.garden_notifications import SIGHTING_MAX_AGE, eligible

    assert SIGHTING_MAX_AGE == timedelta(hours=2)
    capture = snapshot(observed_ago=sighting_age, checked_ago=0)
    assert eligible(capture, enabled=True, cameras=["patio"], decided_at=NOW, now=NOW) is expected


def test_owner_names_use_the_acceptance_time_and_automatic_names_use_their_check():
    from app.services.garden_notifications import decision_time, eligible

    owner = snapshot(observed_ago=3000, checked_ago=None, automatic=False)
    assert decision_time(owner, None) is None
    assert not eligible(owner, enabled=True, cameras=["patio"], decided_at=None, now=NOW)
    accepted = NOW - timedelta(seconds=10)
    assert eligible(owner, enabled=True, cameras=["patio"], decided_at=decision_time(owner, accepted), now=NOW)
    automatic = snapshot(observed_ago=600, checked_ago=900)
    # An automatic name is as old as its check, whatever time a caller passes.
    assert decision_time(automatic, NOW).isoformat() == (NOW - timedelta(seconds=900)).isoformat() + "+00:00"
    assert not eligible(automatic, enabled=True, cameras=["patio"], decided_at=decision_time(automatic, NOW), now=NOW)


@pytest.mark.parametrize("change", ["disabled", "camera", "unconfirmed", "unreviewed", "unnamed", "corrected"])
def test_only_enabled_confirmed_accepted_uncorrected_names_on_garden_cameras_qualify(change):
    from dataclasses import replace

    from app.models.garden import GardenOwnerIdentification
    from app.services.garden_notifications import eligible

    capture = snapshot(observed_ago=60, checked_ago=0)
    enabled, cameras = True, ["patio"]
    if change == "disabled":
        enabled = False
    if change == "camera":
        cameras = ["front"]
    if change == "unconfirmed":
        capture = replace(capture, status="pending")
    if change == "unreviewed":
        capture = replace(capture, identification=identity(review="unreviewed"))
    if change == "unnamed":
        capture = replace(capture, identification=identity(name=""))
    if change == "corrected":
        capture = replace(
            capture,
            owner_identification=GardenOwnerIdentification(
                species_id=7, name="Red fox", scientific_name="Vulpes vulpes", changed_at=NOW.isoformat()
            ),
        )
    assert not eligible(capture, enabled=enabled, cameras=cameras, decided_at=NOW, now=NOW)


# --- Channel resolution --------------------------------------------------------------------------

ALL_ON = {"discord": True, "telegram": True, "pushover": True, "email": True}


@pytest.mark.parametrize(
    "bird_enabled,configured,expected",
    [
        ({"telegram": True}, ALL_ON, ["telegram"]),
        ({"telegram": True, "discord": True}, {"telegram": True, "discord": False}, ["telegram"]),
        ({}, ALL_ON, []),
        (ALL_ON, ALL_ON, ["discord", "telegram", "pushover", "email"]),
    ],
)
def test_following_bird_channels_uses_those_switched_on_and_configured(bird_enabled, configured, expected):
    from app.services.garden_notifications import delivery_channels

    result = delivery_channels(
        use_bird_channels=True, selected=["pushover"], bird_enabled=bird_enabled, configured=configured
    )
    assert result == expected


def test_explicit_channels_ignore_bird_switches_and_keep_unconfigured_choices_to_report_them():
    from app.services.garden_notifications import delivery_channels

    result = delivery_channels(
        use_bird_channels=False,
        selected=["email", "telegram", "email"],
        bird_enabled={"discord": True},
        configured={"telegram": True},
    )
    assert result == ["email", "telegram"]
    assert delivery_channels(use_bird_channels=False, selected=[], bird_enabled=ALL_ON, configured=ALL_ON) == []


# --- Delivery against the real repository -------------------------------------------------------


@pytest_asyncio.fixture
async def history(monkeypatch):
    monkeypatch.setattr(settings.system, "beta_garden_animals", True)
    monkeypatch.setattr(settings.frigate, "garden_notifications_enabled", True)
    monkeypatch.setattr(settings.frigate, "garden_notifications_use_bird_channels", False)
    monkeypatch.setattr(settings.frigate, "garden_notification_channels", ["telegram"])
    monkeypatch.setattr(settings.frigate, "garden_notifications_include_photo", True)
    monkeypatch.setattr(settings.frigate, "garden_cameras", ["patio"])
    await init_db()
    async with get_db() as db:
        await db.execute("DELETE FROM garden_captures")
        await db.commit()
    yield
    await close_db()


async def named(event="cat", seconds=0, name="Domestic cat", checked_seconds=0):
    """An automatically named capture seen `seconds` ago and named `checked_seconds` ago."""
    now = utc_naive_now()
    async with get_db() as db:
        repo = GardenRepository(db)
        await repo.capture(event, "patio", "cat", (now - timedelta(seconds=seconds)).isoformat(), True)
        item = next(item for item in await repo.list("pending", 128, 0) if item.frigate_event == event)
        result = check(now - timedelta(seconds=checked_seconds))
        assert await repo.save_automatic_naming(item, result, identity(name=name))
        return item.id


async def owner_named(event="owner", seconds=0):
    """A capture the owner confirmed and whose species suggestion they accepted."""
    now = utc_naive_now()
    async with get_db() as db:
        repo = GardenRepository(db)
        await repo.capture(event, "patio", "cat", (now - timedelta(seconds=seconds)).isoformat(), True)
        item = next(item for item in await repo.list("pending", 128, 0) if item.frigate_event == event)
        await repo.review(item.id, "confirmed")
        suggestion = identity(automatic=False, review="unreviewed")
        assert await repo.save_identification(await repo.get(item.id), suggestion)
        assert await repo.review_identification(item.id, "accepted")
        return item.id


def service_with(sender, photo=b"jpeg"):
    from app.services.garden_notifications import GardenNotificationService

    return GardenNotificationService(sender=sender, photo_loader=AsyncMock(return_value=photo))


@pytest.mark.asyncio
async def test_selected_garden_channel_ignores_bird_modes_filters_and_restart_replays(history, monkeypatch):
    monkeypatch.setattr(settings.notifications, "mode", "silent")
    monkeypatch.setattr(settings.notifications, "notification_cooldown_minutes", 60)
    monkeypatch.setattr(settings.notifications.filters, "audio_confirmed_only", True)
    sender = AsyncMock(return_value=True)
    service = service_with(sender)
    first = await named("first", 50)
    await service.deliver(first)
    await service.deliver(first)
    second = await named("second", 0)
    await service_with(sender).deliver(second)
    assert sender.await_count == 1
    assert sender.call_args.args[0] == "telegram"
    assert sender.call_args.args[2] == b"jpeg"
    assert (await service.status_counts())["sent"] == 1


@pytest.mark.asyncio
async def test_following_bird_channels_sends_on_the_enabled_configured_bird_channel(history, monkeypatch):
    monkeypatch.setattr(settings.frigate, "garden_notifications_use_bird_channels", True)
    monkeypatch.setattr(settings.frigate, "garden_notification_channels", [])
    monkeypatch.setattr(settings.notifications.telegram, "enabled", True)
    monkeypatch.setattr(settings.notifications.telegram, "bot_token", "private-test-token")
    monkeypatch.setattr(settings.notifications.telegram, "chat_id", "owner-chat")
    for channel in ["discord", "pushover", "email"]:
        monkeypatch.setattr(getattr(settings.notifications, channel), "enabled", False)
    sender = AsyncMock(return_value=True)
    await service_with(sender).deliver(await named())
    assert [call.args[0] for call in sender.await_args_list] == ["telegram"]


@pytest.mark.asyncio
async def test_alert_is_text_only_when_photos_are_off_or_unavailable(history, monkeypatch):
    sender = AsyncMock(return_value=True)
    await service_with(sender, photo=None).deliver(await named("missing"))
    assert sender.call_args.args[2] is None
    monkeypatch.setattr(settings.frigate, "garden_notifications_include_photo", False)
    loader = AsyncMock(return_value=b"jpeg")
    from app.services.garden_notifications import GardenNotificationService

    await GardenNotificationService(sender=sender, photo_loader=loader).deliver(await named("off"))
    loader.assert_not_awaited()
    assert sender.call_args.args[2] is None


@pytest.mark.asyncio
async def test_a_failing_photo_read_still_sends_the_text_alert(history):
    from app.services.garden_notifications import GardenNotificationService

    sender = AsyncMock(return_value=True)
    loader = AsyncMock(side_effect=OSError("frigate unreachable"))
    await GardenNotificationService(sender=sender, photo_loader=loader).deliver(await named())
    assert sender.call_args.args[2] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change", ["disabled", "beta", "camera", "person", "dismissed", "old", "stale", "unnamed", "follow_none"]
)
async def test_queued_delivery_rechecks_opt_in_named_state_freshness_and_privacy(history, monkeypatch, change):
    capture_id = await named(
        seconds=2 * 3600 + 60 if change == "old" else 540, checked_seconds=301 if change == "stale" else 0
    )
    if change == "disabled":
        monkeypatch.setattr(settings.frigate, "garden_notifications_enabled", False)
    if change == "beta":
        monkeypatch.setattr(settings.system, "beta_garden_animals", False)
    if change == "camera":
        monkeypatch.setattr(settings.frigate, "garden_cameras", [])
    if change == "follow_none":
        monkeypatch.setattr(settings.frigate, "garden_notifications_use_bird_channels", True)
        for channel in ["discord", "telegram", "pushover", "email"]:
            monkeypatch.setattr(getattr(settings.notifications, channel), "enabled", False)
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
    await service_with(sender).deliver(capture_id)
    sender.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_privacy_change_while_the_photo_loads_skips_the_send(history):
    from app.services.garden_notifications import GardenNotificationService

    capture_id = await named()

    async def load_then_block(capture):
        async with get_db() as db:
            await GardenRepository(db).block_capture(capture.id)
        return b"jpeg"

    sender = AsyncMock(return_value=True)
    service = GardenNotificationService(sender=sender, photo_loader=load_then_block)
    await service.deliver(capture_id)
    sender.assert_not_awaited()
    assert (await service.status_counts())["skipped"] == 1


@pytest.mark.asyncio
async def test_owner_acceptance_sends_only_while_the_acceptance_is_fresh(history):
    sender = AsyncMock(return_value=True)
    capture_id = await owner_named("fresh", seconds=3000)
    await service_with(sender).deliver(capture_id)
    sender.assert_not_awaited()
    await service_with(sender).deliver(capture_id, accepted_at=utc_naive_now() - timedelta(seconds=301))
    sender.assert_not_awaited()
    await service_with(sender).deliver(capture_id, accepted_at=utc_naive_now())
    sender.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_attempt_is_not_replayed_and_new_visit_is_independent(history):
    sender = AsyncMock(return_value=False)
    service = service_with(sender)
    older = await named("older", 200)
    await service.deliver(older)
    await service_with(sender).deliver(older)
    newer = await named("newer", 0)
    await service.deliver(newer)
    assert sender.await_count == 2
    assert (await service.status_counts())["failed"] == 2


@pytest.mark.asyncio
async def test_concurrent_captures_claim_one_channel_attempt_for_the_known_visit(history):
    import asyncio

    first, second = await named("first", 30), await named("second", 0)
    sender = AsyncMock(return_value=True)
    service = service_with(sender)
    await asyncio.gather(service.deliver(first), service.deliver(second))
    assert sender.await_count == 1


@pytest.mark.asyncio
async def test_schedule_queues_only_while_some_channel_would_receive_it(history, monkeypatch):
    from app.services import garden_notifications as module

    enqueue = AsyncMock()
    monkeypatch.setattr(module.notification_dispatcher, "enqueue", enqueue)
    service = service_with(AsyncMock(return_value=True))
    await service.schedule("a" * 32)
    assert enqueue.await_count == 1
    monkeypatch.setattr(settings.frigate, "garden_notification_channels", [])
    await service.schedule("a" * 32)
    assert enqueue.await_count == 1


# --- Messages and transports ---------------------------------------------------------------------


@pytest_asyncio.fixture
async def channels(history, monkeypatch):
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
    monkeypatch.setattr(settings.notifications, "notification_language", "en")


async def saved(capture_id):
    async with get_db() as db:
        return await GardenRepository(db).get(capture_id)


async def send_through_mock(monkeypatch, channel, capture, photo):
    from app.services import garden_notification_transport as transport

    requests = []

    async def receive(request):
        requests.append(request)
        return httpx.Response(200, json={"ok": True, "status": 1, "id": "message-1"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(receive)) as client:
        monkeypatch.setattr(transport, "http_client", client)
        assert await transport.send_garden_notification(channel, capture, photo)
    assert len(requests) == 1
    return requests[0]


def test_message_states_the_sighting_time_and_deep_links_to_the_capture(monkeypatch):
    from app.services.garden_notification_transport import message

    monkeypatch.setattr(settings.notifications, "instance_url", "https://owner.test/feeder/")
    monkeypatch.setattr(settings.notifications, "notification_language", "en")
    capture = snapshot(observed_ago=540, checked_ago=0)
    title, body, url = message(capture)
    assert title == "Garden animal: Domestic cat"
    assert body == "Seen on patio at 2026-10-25 11:51 UTC\nNamed automatically"
    assert url == (
        "https://owner.test/feeder/events?visitors=garden&review=confirmed&camera=patio&garden_capture=" + "c" * 32
    )
    monkeypatch.setattr(settings.notifications, "instance_url", None)
    monkeypatch.setattr(settings.notifications.email, "dashboard_url", None)
    assert message(capture)[2] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("channel", ["discord", "telegram", "pushover"])
async def test_text_transports_escape_names_and_use_explicit_credentials_without_bird_flags(
    channels, monkeypatch, channel
):
    capture = await saved(await named(name="Cat <b>& *text*"))
    request = await send_through_mock(monkeypatch, channel, capture, None)
    body = request.content.decode()
    assert "attachment" not in body and "sendPhoto" not in str(request.url)
    assert "owner.test" in body and "frigate" not in body
    assert "garden_capture" in body
    assert "Named automatically" in body or "Named+automatically" in body
    if channel == "telegram":
        payload = json.loads(body)
        assert "&lt;b&gt;&amp;" in payload["text"]
        assert payload["link_preview_options"]["is_disabled"] is True
        assert payload["reply_markup"]["inline_keyboard"][0][0]["text"] == "View capture"
    if channel == "discord":
        assert request.url.params["wait"] == "true"
        assert request.url.params["thread_id"] == "123"
        payload = json.loads(body)
        assert payload["allowed_mentions"] == {"parse": []}
        assert "\\*text\\*" in payload["embeds"][0]["title"]
        assert payload["embeds"][0]["timestamp"].endswith("+00:00")


@pytest.mark.asyncio
@pytest.mark.parametrize("channel", ["discord", "telegram", "pushover"])
async def test_photo_transports_attach_the_capture_photo_with_escaped_text(channels, monkeypatch, channel):
    capture = await saved(await named(name="Cat <b>& *text*"))
    photo = b"\xff\xd8\xff garden-jpeg"
    request = await send_through_mock(monkeypatch, channel, capture, photo)
    body = request.content
    assert request.headers["content-type"].startswith("multipart/form-data")
    assert photo in body
    assert b"private-token" not in body and b"/api/garden/" not in body
    text = body.decode("utf-8", errors="replace")
    if channel == "telegram":
        assert str(request.url).endswith("/sendPhoto")
        assert 'name="photo"' in text
        assert "&lt;b&gt;&amp;" in text
        assert "garden_capture" in text
    if channel == "discord":
        assert request.url.params["wait"] == "true"
        assert 'name="files[0]"' in text
        assert "attachment://garden.jpg" in text
        assert '"allowed_mentions": {"parse": []}' in text
        assert "\\\\*text\\\\*" in text
    if channel == "pushover":
        assert 'name="attachment"' in text
        assert "garden_capture" in text


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["refused", "timeout"])
async def test_a_failed_telegram_alert_is_not_sent_and_logs_no_credential(channels, monkeypatch, failure):
    from structlog.testing import capture_logs

    from app.services import garden_notification_transport as transport

    capture = await saved(await named())
    requests = []

    async def receive(request):
        requests.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout(f"Timeout accessing {request.url}", request=request)
        return httpx.Response(403, json={"ok": False})

    async with httpx.AsyncClient(transport=httpx.MockTransport(receive)) as client:
        monkeypatch.setattr(transport, "http_client", client)
        with capture_logs() as logs:
            assert await transport.send_garden_notification("telegram", capture, None) is False
    assert len(requests) == 1
    warning = next(row for row in logs if row["event"] == "garden_channel_delivery_failed")
    assert warning["error_type"] == ("ReadTimeout" if failure == "timeout" else "HTTPStatusError")
    assert "private-test-token" not in json.dumps(logs)


@pytest.mark.asyncio
@pytest.mark.parametrize("oauth", [False, True])
@pytest.mark.parametrize("photo", [None, b"\xff\xd8\xff garden-jpeg"])
async def test_email_is_escaped_and_embeds_the_photo_inline_when_given(history, monkeypatch, oauth, photo):
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
        "include_snapshot": False,
    }.items():
        monkeypatch.setattr(cfg, key, value)
    sender = AsyncMock(return_value=True)
    monkeypatch.setattr(smtp_service, "send_email_oauth" if oauth else "send_email_password", sender)
    capture = await saved(await named(name="Cat <b>& text"))
    assert await send_garden_notification("email", capture, photo)
    data = sender.call_args.kwargs
    assert data["image_data"] == photo
    assert "Cat &lt;b&gt;&amp; text" in data["html_body"]
    assert ("cid:bird_snapshot" in data["html_body"]) is bool(photo)
    assert "Garden animal" in data["subject"]
    assert "bird" not in data["html_body"].replace("cid:bird_snapshot", "").lower()


@pytest.mark.asyncio
async def test_photo_prefers_the_saved_crop_then_the_snapshot_and_refuses_oversized_images(history, monkeypatch):
    from fastapi import HTTPException

    from app.repositories.garden_repository import GardenPhotoUnavailable
    from app.services import garden_notification_transport as transport
    from app.services.garden_capture_service import garden_capture_service

    capture = await saved(await named())
    crop = AsyncMock(return_value=b"crop")
    shot = AsyncMock(return_value=b"snapshot")
    monkeypatch.setattr(GardenRepository, "crop_photo", crop)
    monkeypatch.setattr(garden_capture_service, "snapshot", shot)
    assert await transport.garden_photo(capture) == b"crop"
    shot.assert_not_awaited()
    crop.return_value = None
    assert await transport.garden_photo(capture) == b"snapshot"
    crop.side_effect = GardenPhotoUnavailable("changed")
    assert await transport.garden_photo(capture) == b"snapshot"
    shot.side_effect = HTTPException(404, "gone")
    assert await transport.garden_photo(capture) is None
    shot.side_effect = None
    shot.return_value = b"x" * (transport.PHOTO_LIMIT_BYTES + 1)
    assert await transport.garden_photo(capture) is None


# --- Storage and API -----------------------------------------------------------------------------


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
async def test_saved_status_is_owner_only_reports_the_resolved_channels_and_contains_no_credentials(
    history, monkeypatch
):
    from app.main import app

    monkeypatch.setattr(settings.auth, "enabled", False)
    monkeypatch.setattr(settings.public_access, "enabled", False)
    monkeypatch.setattr(settings.frigate, "garden_notifications_use_bird_channels", True)
    monkeypatch.setattr(settings.notifications.telegram, "enabled", True)
    monkeypatch.setattr(settings.notifications.telegram, "bot_token", "private-status-token")
    monkeypatch.setattr(settings.notifications.telegram, "chat_id", "private-chat")
    for channel in ["discord", "pushover", "email"]:
        monkeypatch.setattr(getattr(settings.notifications, channel), "enabled", False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/garden/notifications")
        assert response.status_code == 200, response.text
        status = response.json()
        assert status["configured"]["telegram"] is True
        assert status["use_bird_channels"] is True
        assert status["delivery_channels"] == ["telegram"]
        assert status["include_photo"] is True
        assert "private-status-token" not in response.text and "private-chat" not in response.text
        monkeypatch.setattr(settings.auth, "enabled", True)
        monkeypatch.setattr(settings.public_access, "enabled", True)
        assert (await client.get("/api/garden/notifications")).status_code in {401, 403}


@pytest.mark.asyncio
@pytest.mark.parametrize("action,attempts", [("accept", 1), ("dismiss", 0)])
async def test_only_accepting_a_species_schedules_an_owner_review_alert_with_its_acceptance_time(
    monkeypatch, action, attempts
):
    from app.routers import garden

    saved_capture = object()
    schedule = AsyncMock()
    monkeypatch.setattr(garden.garden_identification_service, "review", AsyncMock())
    monkeypatch.setattr(garden.garden_identification_service, "invalidate_photo_checks", lambda: None)
    monkeypatch.setattr(garden.garden_capture_service, "get", AsyncMock(return_value=saved_capture))
    monkeypatch.setattr(garden, "_response", AsyncMock(return_value=saved_capture))
    monkeypatch.setattr(garden.garden_notification_service, "schedule", schedule)
    before = utc_naive_now()
    assert await garden.review_identification("cat", action) is saved_capture
    assert schedule.await_count == attempts
    if attempts:
        accepted_at = schedule.call_args.kwargs["accepted_at"]
        assert before <= accepted_at <= utc_naive_now()
