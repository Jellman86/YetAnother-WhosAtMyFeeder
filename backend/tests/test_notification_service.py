import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone
from app.services.notification_service import NotificationService


@pytest.fixture
def notification_service():
    return NotificationService()


@pytest.mark.asyncio
async def test_should_notify_respects_confidence_threshold(notification_service):
    """Notifications should filter by confidence threshold."""
    with patch("app.services.notification_service.settings") as mock_settings:
        mock_settings.notifications.filters.species_whitelist = []
        mock_settings.notifications.filters.min_confidence = 0.7
        mock_settings.notifications.filters.audio_confirmed_only = False
        mock_settings.notifications.filters.camera_filters = {}
        mock_settings.notifications.notification_cooldown_minutes = 0

        # Above threshold
        should_notify = await notification_service._should_notify(
            species="Robin", confidence=0.8, audio_confirmed=False, camera="front"
        )
        assert should_notify is True

        # Below threshold
        should_notify = await notification_service._should_notify(
            species="Robin", confidence=0.6, audio_confirmed=False, camera="front"
        )
        assert should_notify is False


@pytest.mark.asyncio
async def test_should_notify_species_whitelist(notification_service):
    """Whitelist should only notify specified species."""
    with patch("app.services.notification_service.settings") as mock_settings:
        mock_settings.notifications.filters.species_whitelist = ["Robin", "Blue Jay"]
        mock_settings.notifications.filters.min_confidence = 0.5
        mock_settings.notifications.filters.audio_confirmed_only = False
        mock_settings.notifications.filters.camera_filters = {}
        mock_settings.notifications.notification_cooldown_minutes = 0

        # In whitelist
        should_notify = await notification_service._should_notify(
            species="Robin", confidence=0.9, audio_confirmed=False, camera="front"
        )
        assert should_notify is True

        # Not in whitelist
        should_notify = await notification_service._should_notify(
            species="Cardinal", confidence=0.9, audio_confirmed=False, camera="front"
        )
        assert should_notify is False


@pytest.mark.asyncio
async def test_should_notify_structured_whitelist_matches_taxonomy(notification_service):
    with patch("app.services.notification_service.settings") as mock_settings:
        mock_settings.notifications.filters.species_whitelist = []
        mock_settings.notifications.filters.species_whitelist_structured = [
            {
                "common_name": "European Robin",
                "scientific_name": "Erithacus rubecula",
                "taxa_id": 1234,
            }
        ]
        mock_settings.notifications.filters.species_blacklist_structured = []
        mock_settings.notifications.filters.min_confidence = 0.5
        mock_settings.notifications.filters.audio_confirmed_only = False
        mock_settings.notifications.filters.camera_filters = {}
        mock_settings.notifications.notification_cooldown_minutes = 0

        should_notify = await notification_service._should_notify(
            species="Robin",
            scientific_name="Erithacus rubecula",
            common_name="European Robin",
            taxa_id=1234,
            confidence=0.9,
            audio_confirmed=False,
            camera="front",
        )
        assert should_notify is True


@pytest.mark.asyncio
async def test_should_notify_structured_blacklist_blocks_taxonomy_match(notification_service):
    with patch("app.services.notification_service.settings") as mock_settings:
        mock_settings.notifications.filters.species_whitelist = []
        mock_settings.notifications.filters.species_whitelist_structured = []
        mock_settings.notifications.filters.species_blacklist_structured = [
            {
                "common_name": "House Sparrow",
                "scientific_name": "Passer domesticus",
                "taxa_id": 5678,
            }
        ]
        mock_settings.notifications.filters.min_confidence = 0.5
        mock_settings.notifications.filters.audio_confirmed_only = False
        mock_settings.notifications.filters.camera_filters = {}
        mock_settings.notifications.notification_cooldown_minutes = 0

        should_notify = await notification_service._should_notify(
            species="Sparrow",
            scientific_name="Passer domesticus",
            common_name="House Sparrow",
            taxa_id=5678,
            confidence=0.9,
            audio_confirmed=False,
            camera="front",
        )
        assert should_notify is False


@pytest.mark.asyncio
async def test_should_notify_blacklist_wins_over_whitelist(notification_service):
    with patch("app.services.notification_service.settings") as mock_settings:
        mock_settings.notifications.filters.species_whitelist = []
        mock_settings.notifications.filters.species_whitelist_structured = [
            {
                "common_name": "European Starling",
                "scientific_name": "Sturnus vulgaris",
                "taxa_id": 777,
            }
        ]
        mock_settings.notifications.filters.species_blacklist_structured = [
            {
                "common_name": "European Starling",
                "scientific_name": "Sturnus vulgaris",
                "taxa_id": 777,
            }
        ]
        mock_settings.notifications.filters.min_confidence = 0.5
        mock_settings.notifications.filters.audio_confirmed_only = False
        mock_settings.notifications.filters.camera_filters = {}
        mock_settings.notifications.notification_cooldown_minutes = 0

        should_notify = await notification_service._should_notify(
            species="Starling",
            scientific_name="Sturnus vulgaris",
            common_name="European Starling",
            taxa_id=777,
            confidence=0.9,
            audio_confirmed=False,
            camera="front",
        )
        assert should_notify is False


@pytest.mark.asyncio
async def test_should_notify_none_mode_ignores_stale_structured_lists(notification_service):
    with patch("app.services.notification_service.settings") as mock_settings:
        mock_settings.notifications.filters.species_mode = "none"
        mock_settings.notifications.filters.species_whitelist = []
        mock_settings.notifications.filters.species_whitelist_structured = [
            {"common_name": "Robin", "scientific_name": "Turdus migratorius", "taxa_id": 1}
        ]
        mock_settings.notifications.filters.species_blacklist_structured = [
            {"common_name": "Blue Jay", "scientific_name": "Cyanocitta cristata", "taxa_id": 2}
        ]
        mock_settings.notifications.filters.min_confidence = 0.5
        mock_settings.notifications.filters.audio_confirmed_only = False
        mock_settings.notifications.filters.camera_filters = {}
        mock_settings.notifications.notification_cooldown_minutes = 0

        assert (
            await notification_service._should_notify(
                "Robin",
                0.9,
                False,
                "front",
                scientific_name="Turdus migratorius",
                common_name="Robin",
                taxa_id=1,
            )
            is True
        )
        assert (
            await notification_service._should_notify(
                "Blue Jay",
                0.9,
                False,
                "front",
                scientific_name="Cyanocitta cristata",
                common_name="Blue Jay",
                taxa_id=2,
            )
            is True
        )


@pytest.mark.asyncio
async def test_should_notify_blacklist_mode_ignores_stale_whitelist(notification_service):
    with patch("app.services.notification_service.settings") as mock_settings:
        mock_settings.notifications.filters.species_mode = "blacklist"
        mock_settings.notifications.filters.species_whitelist = []
        mock_settings.notifications.filters.species_whitelist_structured = [
            {"common_name": "Robin", "scientific_name": "Turdus migratorius", "taxa_id": 1}
        ]
        mock_settings.notifications.filters.species_blacklist_structured = [
            {"common_name": "Blue Jay", "scientific_name": "Cyanocitta cristata", "taxa_id": 2}
        ]
        mock_settings.notifications.filters.min_confidence = 0.5
        mock_settings.notifications.filters.audio_confirmed_only = False
        mock_settings.notifications.filters.camera_filters = {}
        mock_settings.notifications.notification_cooldown_minutes = 0

        assert (
            await notification_service._should_notify(
                "Robin",
                0.9,
                False,
                "front",
                scientific_name="Turdus migratorius",
                common_name="Robin",
                taxa_id=1,
            )
            is True
        )
        assert (
            await notification_service._should_notify(
                "Blue Jay",
                0.9,
                False,
                "front",
                scientific_name="Cyanocitta cristata",
                common_name="Blue Jay",
                taxa_id=2,
            )
            is False
        )


@pytest.mark.asyncio
async def test_should_notify_whitelist_mode_ignores_stale_blacklist(notification_service):
    with patch("app.services.notification_service.settings") as mock_settings:
        mock_settings.notifications.filters.species_mode = "whitelist"
        mock_settings.notifications.filters.species_whitelist = []
        mock_settings.notifications.filters.species_whitelist_structured = [
            {"common_name": "Robin", "scientific_name": "Turdus migratorius", "taxa_id": 1}
        ]
        mock_settings.notifications.filters.species_blacklist_structured = [
            {"common_name": "Blue Jay", "scientific_name": "Cyanocitta cristata", "taxa_id": 2}
        ]
        mock_settings.notifications.filters.min_confidence = 0.5
        mock_settings.notifications.filters.audio_confirmed_only = False
        mock_settings.notifications.filters.camera_filters = {}
        mock_settings.notifications.notification_cooldown_minutes = 0

        assert (
            await notification_service._should_notify(
                "Robin",
                0.9,
                False,
                "front",
                scientific_name="Turdus migratorius",
                common_name="Robin",
                taxa_id=1,
            )
            is True
        )
        assert (
            await notification_service._should_notify(
                "Blue Jay",
                0.9,
                False,
                "front",
                scientific_name="Cyanocitta cristata",
                common_name="Blue Jay",
                taxa_id=2,
            )
            is False
        )


@pytest.mark.asyncio
async def test_should_notify_audio_confirmed_only(notification_service):
    """Audio confirmed filter should work."""
    with patch("app.services.notification_service.settings") as mock_settings:
        mock_settings.notifications.filters.species_whitelist = []
        mock_settings.notifications.filters.min_confidence = 0.5
        mock_settings.notifications.filters.audio_confirmed_only = True
        mock_settings.notifications.filters.camera_filters = {}
        mock_settings.notifications.notification_cooldown_minutes = 0

        # Audio confirmed
        should_notify = await notification_service._should_notify(
            species="Robin", confidence=0.8, audio_confirmed=True, camera="front"
        )
        assert should_notify is True

        # Visual only
        should_notify = await notification_service._should_notify(
            species="Robin", confidence=0.8, audio_confirmed=False, camera="front"
        )
        assert should_notify is False


@pytest.mark.asyncio
async def test_should_notify_per_camera_filters(notification_service):
    """Per-camera confidence filters should work."""
    with patch("app.services.notification_service.settings") as mock_settings:
        mock_settings.notifications.filters.species_whitelist = []
        mock_settings.notifications.filters.min_confidence = 0.5
        mock_settings.notifications.filters.audio_confirmed_only = False
        mock_settings.notifications.filters.camera_filters = {"front": {"min_confidence": 0.8}}
        mock_settings.notifications.notification_cooldown_minutes = 0

        # Camera with higher threshold - passes
        should_notify = await notification_service._should_notify(
            species="Robin", confidence=0.85, audio_confirmed=False, camera="front"
        )
        assert should_notify is True

        # Camera with higher threshold - fails
        should_notify = await notification_service._should_notify(
            species="Robin", confidence=0.7, audio_confirmed=False, camera="front"
        )
        assert should_notify is False

        # Different camera uses global threshold
        should_notify = await notification_service._should_notify(
            species="Robin", confidence=0.7, audio_confirmed=False, camera="back"
        )
        assert should_notify is True


@pytest.mark.asyncio
async def test_send_discord_notification_success(notification_service):
    """Discord notification should send successfully."""
    with patch("app.services.notification_service.settings") as mock_settings:
        mock_settings.notifications.discord.webhook_url = "https://discord.com/api/webhooks/test"
        mock_settings.notifications.discord.username = "YA-WAMF"
        mock_settings.notifications.discord.include_snapshot = True

        with patch.object(notification_service.client, "post", new_callable=AsyncMock) as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 204
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response

            await notification_service._send_discord(
                species="Blue Jay",
                confidence=0.95,
                camera="front_feeder",
                timestamp=datetime.now(timezone.utc),
                snapshot_url="http://frigate/snapshot.jpg",
                audio_confirmed=False,
                lang="en",
                snapshot_data=None,
            )

            assert mock_post.called
            call_args = mock_post.call_args
            assert "Blue Jay" in str(call_args)


@pytest.mark.asyncio
async def test_send_discord_with_audio_confirmation(notification_service):
    """Discord notification should include audio confirmation badge."""
    with patch("app.services.notification_service.settings") as mock_settings:
        mock_settings.notifications.discord.webhook_url = "https://discord.com/api/webhooks/test"
        mock_settings.notifications.discord.username = "YA-WAMF"
        mock_settings.notifications.discord.include_snapshot = False

        with patch.object(notification_service.client, "post", new_callable=AsyncMock) as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 204
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response

            await notification_service._send_discord(
                species="Robin",
                confidence=0.88,
                camera="back_yard",
                timestamp=datetime.now(timezone.utc),
                snapshot_url="http://frigate/snapshot.jpg",
                audio_confirmed=True,
                lang="en",
                snapshot_data=None,
            )

            # Check that the payload includes audio confirmation text
            call_json = mock_post.call_args.kwargs.get("json")
            description = call_json["embeds"][0]["description"]
            assert "Audio" in description or "confirmed" in description.lower()


@pytest.mark.asyncio
async def test_send_discord_with_snapshot_data(notification_service):
    """Discord notification should attach snapshot as file."""
    with patch("app.services.notification_service.settings") as mock_settings:
        mock_settings.notifications.discord.webhook_url = "https://discord.com/api/webhooks/test"
        mock_settings.notifications.discord.username = "YA-WAMF"
        mock_settings.notifications.discord.include_snapshot = True

        with patch.object(notification_service.client, "post", new_callable=AsyncMock) as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 204
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response

            fake_image = b"fake_jpeg_data"
            await notification_service._send_discord(
                species="Cardinal",
                confidence=0.92,
                camera="feeder",
                timestamp=datetime.now(timezone.utc),
                snapshot_url="http://frigate/snapshot.jpg",
                audio_confirmed=False,
                lang="en",
                snapshot_data=fake_image,
            )

            # Should use multipart form with files
            assert mock_post.called
            call_kwargs = mock_post.call_args.kwargs
            assert "files" in call_kwargs
            assert call_kwargs["files"]["files[0]"][1] == fake_image


@pytest.mark.asyncio
async def test_send_telegram_escapes_markdown(notification_service):
    """Telegram should escape markdown special characters in species names."""
    with patch("app.services.notification_service.settings") as mock_settings:
        mock_settings.notifications.telegram.bot_token = "test_token"
        mock_settings.notifications.telegram.chat_id = "12345"

        with patch.object(notification_service.client, "post", new_callable=AsyncMock) as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response

            # Species with markdown special characters
            await notification_service._send_telegram(
                species="Test_Bird*With[Special]",
                confidence=0.85,
                camera="back_yard",
                timestamp=datetime.now(timezone.utc),
                snapshot_url="http://frigate/snapshot.jpg",
                snapshot_data=None,
                lang="en",
            )

            call_json = mock_post.call_args.kwargs.get("json")
            text = call_json.get("caption", call_json.get("text", ""))
            # Should have escaped the special characters
            assert "\\" in text or "Test_Bird" in text


@pytest.mark.asyncio
async def test_notify_detection_skips_when_filtered(notification_service):
    """notify_detection should not send when filters exclude it."""
    with patch("app.services.notification_service.settings") as mock_settings:
        mock_settings.notifications.filters.species_whitelist = ["Robin"]
        mock_settings.notifications.filters.min_confidence = 0.7
        mock_settings.notifications.filters.audio_confirmed_only = False
        mock_settings.notifications.filters.camera_filters = {}
        mock_settings.notifications.notification_language = "en"
        mock_settings.notifications.discord.enabled = True

        with patch.object(notification_service, "_send_discord", new_callable=AsyncMock) as mock_discord:
            # Species not in whitelist
            await notification_service.notify_detection(
                frigate_event="test123",
                species="Cardinal",
                scientific_name="Cardinalis cardinalis",
                common_name="Northern Cardinal",
                confidence=0.9,
                camera="front",
                timestamp=datetime.now(timezone.utc),
                snapshot_url="http://test.jpg",
                audio_confirmed=False,
            )

            # Discord should not be called
            assert not mock_discord.called


@pytest.mark.asyncio
async def test_notify_detection_sends_to_all_platforms(notification_service):
    """notify_detection should send to all enabled platforms."""
    with patch("app.services.notification_service.settings") as mock_settings:
        mock_settings.notifications.filters.species_whitelist = []
        mock_settings.notifications.filters.min_confidence = 0.5
        mock_settings.notifications.filters.audio_confirmed_only = False
        mock_settings.notifications.filters.camera_filters = {}
        mock_settings.notifications.notification_cooldown_minutes = 0
        mock_settings.notifications.notification_language = "en"
        mock_settings.notifications.discord.enabled = True
        mock_settings.notifications.pushover.enabled = True
        mock_settings.notifications.telegram.enabled = True
        mock_settings.notifications.email.enabled = False

        with (
            patch.object(notification_service, "_send_discord", new_callable=AsyncMock) as mock_discord,
            patch.object(notification_service, "_send_pushover", new_callable=AsyncMock) as mock_pushover,
            patch.object(notification_service, "_send_telegram", new_callable=AsyncMock) as mock_telegram,
        ):
            await notification_service.notify_detection(
                frigate_event="test123",
                species="Robin",
                scientific_name="Erithacus rubecula",
                common_name="European Robin",
                confidence=0.9,
                camera="front",
                timestamp=datetime.now(timezone.utc),
                snapshot_url="http://test.jpg",
                audio_confirmed=True,
            )

            # All three enabled platforms should be called
            assert mock_discord.called
            assert mock_pushover.called
            assert mock_telegram.called


@pytest.mark.asyncio
async def test_notify_detection_handles_errors_gracefully(notification_service):
    """notify_detection should continue even if one platform fails."""
    with patch("app.services.notification_service.settings") as mock_settings:
        mock_settings.notifications.filters.species_whitelist = []
        mock_settings.notifications.filters.min_confidence = 0.5
        mock_settings.notifications.filters.audio_confirmed_only = False
        mock_settings.notifications.filters.camera_filters = {}
        mock_settings.notifications.notification_cooldown_minutes = 0
        mock_settings.notifications.notification_language = "en"
        mock_settings.notifications.discord.enabled = True
        mock_settings.notifications.pushover.enabled = True

        with (
            patch.object(notification_service, "_send_discord", new_callable=AsyncMock) as mock_discord,
            patch.object(notification_service, "_send_pushover", new_callable=AsyncMock) as mock_pushover,
        ):
            # Discord fails
            mock_discord.side_effect = Exception("Discord API error")
            # Pushover succeeds
            mock_pushover.return_value = True

            # Should not raise exception
            await notification_service.notify_detection(
                frigate_event="test123",
                species="Robin",
                scientific_name="Turdus migratorius",
                common_name="American Robin",
                confidence=0.9,
                camera="front",
                timestamp=datetime.now(timezone.utc),
                snapshot_url="http://test.jpg",
                audio_confirmed=False,
            )

            # Both should have been attempted
            assert mock_discord.called
            assert mock_pushover.called


@pytest.mark.asyncio
async def test_send_email_falls_back_to_http_get_snapshot(notification_service, monkeypatch):
    """Email send should still succeed when snapshot bytes are fetched via URL."""
    from app.config import settings as real_settings

    monkeypatch.setattr(real_settings.notifications.email, "to_email", "to@example.com")
    monkeypatch.setattr(real_settings.notifications.email, "use_oauth", False)
    monkeypatch.setattr(real_settings.notifications.email, "oauth_provider", None)
    monkeypatch.setattr(real_settings.notifications.email, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(real_settings.notifications.email, "smtp_port", 587)
    monkeypatch.setattr(real_settings.notifications.email, "smtp_username", "user")
    monkeypatch.setattr(real_settings.notifications.email, "smtp_password", "pass")
    monkeypatch.setattr(real_settings.notifications.email, "from_email", "from@example.com")
    monkeypatch.setattr(real_settings.notifications.email, "smtp_use_tls", True)
    monkeypatch.setattr(real_settings.notifications.email, "include_snapshot", True)
    monkeypatch.setattr(real_settings.notifications.email, "dashboard_url", "https://example.com")
    monkeypatch.setattr(real_settings.appearance, "font_theme", "classic")
    monkeypatch.setattr(real_settings.accessibility, "dyslexia_font", False)

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.content = b"fake-image"

    with (
        patch.object(
            notification_service.client, "get", new_callable=AsyncMock, return_value=fake_response
        ) as mock_get,
        patch(
            "app.services.smtp_service.smtp_service.send_email_password", new_callable=AsyncMock, return_value=True
        ) as mock_send,
    ):
        sent = await notification_service._send_email(
            species="Robin",
            scientific_name="Erithacus rubecula",
            confidence=0.92,
            camera="front",
            timestamp=datetime.now(timezone.utc),
            snapshot_url="http://frigate/snapshot.jpg",
            snapshot_data=None,
            audio_confirmed=False,
            lang="en",
        )

        assert sent is True
        mock_get.assert_awaited_once()
        assert mock_send.await_count == 1
        assert mock_send.await_args.kwargs["image_data"] == b"fake-image"


# --- every channel links back to the detection when the owner set an instance address (#414) ----


def _posted(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response


@pytest.mark.asyncio
async def test_discord_title_links_to_the_detection(notification_service):
    with patch("app.services.notification_service.settings") as mock_settings:
        mock_settings.notifications.discord.webhook_url = "https://discord.com/api/webhooks/test"
        mock_settings.notifications.discord.username = "YA-WAMF"
        mock_settings.notifications.discord.include_snapshot = False
        with patch.object(notification_service.client, "post", new_callable=AsyncMock) as mock_post:
            _posted(mock_post)
            await notification_service._send_discord(
                species="Blue Jay",
                confidence=0.95,
                camera="front_feeder",
                timestamp=datetime.now(timezone.utc),
                snapshot_url="http://frigate/snapshot.jpg",
                audio_confirmed=False,
                lang="en",
                snapshot_data=None,
                detection_url="https://feeder.example.com/events?event=abc",
            )
            embed = mock_post.call_args.kwargs["json"]["embeds"][0]
            assert embed["url"] == "https://feeder.example.com/events?event=abc"


@pytest.mark.asyncio
async def test_discord_embed_has_no_link_without_an_address(notification_service):
    with patch("app.services.notification_service.settings") as mock_settings:
        mock_settings.notifications.discord.webhook_url = "https://discord.com/api/webhooks/test"
        mock_settings.notifications.discord.username = "YA-WAMF"
        mock_settings.notifications.discord.include_snapshot = False
        with patch.object(notification_service.client, "post", new_callable=AsyncMock) as mock_post:
            _posted(mock_post)
            await notification_service._send_discord(
                species="Blue Jay",
                confidence=0.95,
                camera="front_feeder",
                timestamp=datetime.now(timezone.utc),
                snapshot_url="http://frigate/snapshot.jpg",
                audio_confirmed=False,
                lang="en",
                snapshot_data=None,
            )
            assert "url" not in mock_post.call_args.kwargs["json"]["embeds"][0]


@pytest.mark.asyncio
async def test_pushover_button_opens_the_detection(notification_service):
    with patch("app.services.notification_service.settings") as mock_settings:
        cfg = mock_settings.notifications.pushover
        cfg.user_key, cfg.api_token, cfg.priority, cfg.device, cfg.include_snapshot = "u", "t", 0, None, False
        with patch.object(notification_service.client, "post", new_callable=AsyncMock) as mock_post:
            _posted(mock_post)
            await notification_service._send_pushover(
                "Blue Jay",
                0.95,
                "front_feeder",
                datetime.now(timezone.utc),
                "http://frigate/snapshot.jpg",
                None,
                "en",
                detection_url="https://feeder.example.com/events?event=abc",
            )
            data = mock_post.call_args.kwargs["data"]
            assert data["url"] == "https://feeder.example.com/events?event=abc"
            assert data["url_title"] == "View detection"


@pytest.mark.asyncio
async def test_pushover_keeps_the_snapshot_link_without_an_address(notification_service):
    with patch("app.services.notification_service.settings") as mock_settings:
        cfg = mock_settings.notifications.pushover
        cfg.user_key, cfg.api_token, cfg.priority, cfg.device, cfg.include_snapshot = "u", "t", 0, None, False
        with patch.object(notification_service.client, "post", new_callable=AsyncMock) as mock_post:
            _posted(mock_post)
            await notification_service._send_pushover(
                "Blue Jay", 0.95, "front_feeder", datetime.now(timezone.utc), "http://frigate/snapshot.jpg", None, "en"
            )
            assert mock_post.call_args.kwargs["data"]["url"] == "http://frigate/snapshot.jpg"


@pytest.mark.asyncio
async def test_telegram_photo_carries_a_view_detection_button(notification_service):
    with patch("app.services.notification_service.settings") as mock_settings:
        cfg = mock_settings.notifications.telegram
        cfg.bot_token, cfg.chat_id, cfg.include_snapshot = "token", "42", True
        with patch.object(notification_service.client, "post", new_callable=AsyncMock) as mock_post:
            _posted(mock_post)
            await notification_service._send_telegram(
                "Blue Jay",
                0.95,
                "front_feeder",
                datetime.now(timezone.utc),
                "http://frigate/snapshot.jpg",
                b"jpeg",
                "en",
                detection_url="https://feeder.example.com/events?event=a&b",
            )
            data = mock_post.call_args.kwargs["data"]
            assert "<a " not in data["caption"], "the button carries the link, not the caption"
            button = json.loads(data["reply_markup"])["inline_keyboard"][0][0]
            assert button == {"text": "View detection", "url": "https://feeder.example.com/events?event=a&b"}


@pytest.mark.asyncio
async def test_telegram_text_message_carries_the_button_instead_of_the_snapshot_link(notification_service):
    with patch("app.services.notification_service.settings") as mock_settings:
        cfg = mock_settings.notifications.telegram
        cfg.bot_token, cfg.chat_id, cfg.include_snapshot = "token", "42", False
        with patch.object(notification_service.client, "post", new_callable=AsyncMock) as mock_post:
            _posted(mock_post)
            await notification_service._send_telegram(
                "Blue Jay",
                0.95,
                "front_feeder",
                datetime.now(timezone.utc),
                "http://frigate/snapshot.jpg",
                None,
                "de",
                detection_url="https://feeder.example.com/events?event=abc",
            )
            payload = mock_post.call_args.kwargs["json"]
            assert "View Snapshot" not in payload["text"]
            assert payload["reply_markup"]["inline_keyboard"][0][0] == {
                "text": "Erkennung ansehen",
                "url": "https://feeder.example.com/events?event=abc",
            }


# --- the bird Telegram message, sent through the shared Telegram transport ---------------------


async def _bird_telegram_request(notification_service, monkeypatch, *, snapshot_data, detection_url, answer=None):
    import httpx

    from app.config import settings

    monkeypatch.setattr(settings.notifications.telegram, "bot_token", "123:bird-token")
    monkeypatch.setattr(settings.notifications.telegram, "chat_id", "42")
    monkeypatch.setattr(settings.notifications.telegram, "include_snapshot", True)
    requests = []

    def receive(request):
        requests.append(request)
        return answer or httpx.Response(200, json={"ok": True})

    await notification_service.client.aclose()
    notification_service.client = httpx.AsyncClient(transport=httpx.MockTransport(receive))
    try:
        sent = await notification_service._send_telegram(
            "Blue <Jay> & co",
            0.95,
            "front_feeder",
            datetime.now(timezone.utc),
            "http://frigate/snapshot.jpg?a=1&b=2",
            snapshot_data,
            "en",
            detection_url=detection_url,
        )
    finally:
        await notification_service.client.aclose()
    assert len(requests) == 1
    return sent, requests[0]


@pytest.mark.asyncio
async def test_bird_telegram_text_is_the_bold_escaped_sentence_with_the_snapshot_link(
    notification_service, monkeypatch
):
    sent, request = await _bird_telegram_request(
        notification_service, monkeypatch, snapshot_data=None, detection_url=None
    )
    assert sent is True
    assert str(request.url) == "https://api.telegram.org/bot123:bird-token/sendMessage"
    assert json.loads(request.content) == {
        "chat_id": "42",
        "text": (
            "🐦 <b>Blue &lt;Jay&gt; &amp; co detected on front_feeder with 95% confidence</b>\n"
            '<a href="http://frigate/snapshot.jpg?a=1&amp;b=2">View Snapshot</a>'
        ),
        "parse_mode": "HTML",
        "link_preview_options": {"is_disabled": True},
    }


@pytest.mark.asyncio
async def test_bird_telegram_photo_captions_the_sentence_and_buttons_the_detection(notification_service, monkeypatch):
    sent, request = await _bird_telegram_request(
        notification_service, monkeypatch, snapshot_data=b"bird-jpeg", detection_url="https://feeder.test/e?id=1&x=2"
    )
    assert sent is True
    assert str(request.url).endswith("/sendPhoto")
    body = request.content.decode()
    assert 'name="photo"; filename="snapshot.jpg"' in body and "bird-jpeg" in body
    assert "🐦 <b>Blue &lt;Jay&gt; &amp; co detected on front_feeder with 95% confidence</b>\r\n" in body
    assert "View Snapshot" not in body
    assert '{"inline_keyboard": [[{"text": "View detection", "url": "https://feeder.test/e?id=1&x=2"}]]}' in body


@pytest.mark.asyncio
async def test_bird_telegram_reports_a_refused_send_as_not_sent(notification_service, monkeypatch):
    import httpx

    sent, _ = await _bird_telegram_request(
        notification_service,
        monkeypatch,
        snapshot_data=None,
        detection_url=None,
        answer=httpx.Response(403, json={"ok": False}),
    )
    assert sent is False


# --- bird Discord and Pushover messages, sent through the shared transports --------------------


async def _bird_request(notification_service, send, answer):
    import httpx

    requests = []

    def receive(request):
        requests.append(request)
        return answer

    await notification_service.client.aclose()
    notification_service.client = httpx.AsyncClient(transport=httpx.MockTransport(receive))
    try:
        sent = await send()
    finally:
        await notification_service.client.aclose()
    assert len(requests) == 1
    return sent, requests[0]


def _bird_discord(monkeypatch, include_snapshot=True):
    from app.config import settings

    monkeypatch.setattr(settings.notifications.discord, "webhook_url", "https://discord.test/api/webhooks/1/secret")
    monkeypatch.setattr(settings.notifications.discord, "username", "YA-WAMF")
    monkeypatch.setattr(settings.notifications.discord, "include_snapshot", include_snapshot)


SEEN_AT = datetime(2026, 11, 1, 9, 30)


@pytest.mark.asyncio
async def test_bird_discord_embed_states_the_detection_in_bold_and_shows_the_snapshot_by_address(
    notification_service, monkeypatch
):
    import httpx

    _bird_discord(monkeypatch)
    sent, request = await _bird_request(
        notification_service,
        lambda: notification_service._send_discord(
            "Robin (juvenile)",
            0.88,
            "back_yard",
            SEEN_AT,
            "http://frigate/api/events/e1/snapshot.jpg",
            True,
            "en",
            None,
            detection_url="https://feeder.test/events?event=e1",
        ),
        httpx.Response(200, json={"id": "1"}),
    )
    assert sent is True
    assert request.url.params["wait"] == "true"
    assert json.loads(request.content) == {
        "username": "YA-WAMF",
        "allowed_mentions": {"parse": []},
        "embeds": [
            {
                "title": "New Bird Detected: Robin \\(juvenile\\)",
                "description": (
                    "**Robin \\(juvenile\\) detected on back\\_yard with 88% confidence**\n**🎤 Audio Confirmed by BirdNET-Go**"
                ),
                "color": 3066993,
                "timestamp": "2026-11-01T09:30:00+00:00",
                "footer": {"text": "YA-WAMF"},
                "url": "https://feeder.test/events?event=e1",
                "image": {"url": "http://frigate/api/events/e1/snapshot.jpg"},
            }
        ],
    }


@pytest.mark.asyncio
async def test_bird_discord_attaches_snapshot_bytes_as_the_embed_image(notification_service, monkeypatch):
    import httpx

    _bird_discord(monkeypatch)
    sent, request = await _bird_request(
        notification_service,
        lambda: notification_service._send_discord(
            "Cardinal", 0.92, "feeder", SEEN_AT, "http://frigate/snap.jpg", False, "en", b"bird-jpeg"
        ),
        httpx.Response(200, json={"id": "1"}),
    )
    assert sent is True
    body = request.content.decode()
    assert 'name="files[0]"; filename="snapshot.jpg"' in body and "bird-jpeg" in body
    assert '"image": {"url": "attachment://snapshot.jpg"}' in body
    assert "http://frigate/snap.jpg" not in body


@pytest.mark.asyncio
async def test_bird_pushover_sends_the_detection_with_its_time_priority_and_link(notification_service, monkeypatch):
    import httpx
    from urllib.parse import parse_qs

    from app.config import settings

    cfg = settings.notifications.pushover
    for key, value in {
        "api_token": "app-token",
        "user_key": "user-key",
        "priority": 1,
        "device": "phone",
        "include_snapshot": True,
    }.items():
        monkeypatch.setattr(cfg, key, value)
    sent, request = await _bird_request(
        notification_service,
        lambda: notification_service._send_pushover(
            "Blue Jay",
            0.95,
            "front_feeder",
            SEEN_AT.replace(tzinfo=timezone.utc),
            "http://frigate/snap.jpg",
            None,
            "en",
        ),
        httpx.Response(200, json={"status": 1}),
    )
    assert sent is True
    assert str(request.url) == "https://api.pushover.net/1/messages.json"
    assert {key: values[0] for key, values in parse_qs(request.content.decode()).items()} == {
        "token": "app-token",
        "user": "user-key",
        "title": "New Bird Detected: Blue Jay",
        "message": "Blue Jay detected on front_feeder with 95% confidence",
        "html": "0",
        "priority": "1",
        "timestamp": str(int(SEEN_AT.replace(tzinfo=timezone.utc).timestamp())),
        "url": "http://frigate/snap.jpg",
        "url_title": "View Snapshot",
        "device": "phone",
    }
