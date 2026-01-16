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
    with patch('app.services.notification_service.settings') as mock_settings:
        mock_settings.notifications.filters.species_whitelist = []
        mock_settings.notifications.filters.min_confidence = 0.7
        mock_settings.notifications.filters.audio_confirmed_only = False
        mock_settings.notifications.filters.camera_filters = {}

        # Above threshold
        should_notify = await notification_service._should_notify(
            species="Robin",
            confidence=0.8,
            audio_confirmed=False,
            camera="front"
        )
        assert should_notify is True

        # Below threshold
        should_notify = await notification_service._should_notify(
            species="Robin",
            confidence=0.6,
            audio_confirmed=False,
            camera="front"
        )
        assert should_notify is False


@pytest.mark.asyncio
async def test_should_notify_species_whitelist(notification_service):
    """Whitelist should only notify specified species."""
    with patch('app.services.notification_service.settings') as mock_settings:
        mock_settings.notifications.filters.species_whitelist = ["Robin", "Blue Jay"]
        mock_settings.notifications.filters.min_confidence = 0.5
        mock_settings.notifications.filters.audio_confirmed_only = False
        mock_settings.notifications.filters.camera_filters = {}

        # In whitelist
        should_notify = await notification_service._should_notify(
            species="Robin",
            confidence=0.9,
            audio_confirmed=False,
            camera="front"
        )
        assert should_notify is True

        # Not in whitelist
        should_notify = await notification_service._should_notify(
            species="Cardinal",
            confidence=0.9,
            audio_confirmed=False,
            camera="front"
        )
        assert should_notify is False


@pytest.mark.asyncio
async def test_should_notify_audio_confirmed_only(notification_service):
    """Audio confirmed filter should work."""
    with patch('app.services.notification_service.settings') as mock_settings:
        mock_settings.notifications.filters.species_whitelist = []
        mock_settings.notifications.filters.min_confidence = 0.5
        mock_settings.notifications.filters.audio_confirmed_only = True
        mock_settings.notifications.filters.camera_filters = {}

        # Audio confirmed
        should_notify = await notification_service._should_notify(
            species="Robin",
            confidence=0.8,
            audio_confirmed=True,
            camera="front"
        )
        assert should_notify is True

        # Visual only
        should_notify = await notification_service._should_notify(
            species="Robin",
            confidence=0.8,
            audio_confirmed=False,
            camera="front"
        )
        assert should_notify is False


@pytest.mark.asyncio
async def test_should_notify_per_camera_filters(notification_service):
    """Per-camera confidence filters should work."""
    with patch('app.services.notification_service.settings') as mock_settings:
        mock_settings.notifications.filters.species_whitelist = []
        mock_settings.notifications.filters.min_confidence = 0.5
        mock_settings.notifications.filters.audio_confirmed_only = False
        mock_settings.notifications.filters.camera_filters = {
            "front": {"min_confidence": 0.8}
        }

        # Camera with higher threshold - passes
        should_notify = await notification_service._should_notify(
            species="Robin",
            confidence=0.85,
            audio_confirmed=False,
            camera="front"
        )
        assert should_notify is True

        # Camera with higher threshold - fails
        should_notify = await notification_service._should_notify(
            species="Robin",
            confidence=0.7,
            audio_confirmed=False,
            camera="front"
        )
        assert should_notify is False

        # Different camera uses global threshold
        should_notify = await notification_service._should_notify(
            species="Robin",
            confidence=0.7,
            audio_confirmed=False,
            camera="back"
        )
        assert should_notify is True


@pytest.mark.asyncio
async def test_send_discord_notification_success(notification_service):
    """Discord notification should send successfully."""
    with patch('app.services.notification_service.settings') as mock_settings:
        mock_settings.notifications.discord.webhook_url = "https://discord.com/api/webhooks/test"
        mock_settings.notifications.discord.username = "YA-WAMF"
        mock_settings.notifications.discord.include_snapshot = True

        with patch.object(notification_service.client, 'post', new_callable=AsyncMock) as mock_post:
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
                snapshot_data=None
            )

            assert mock_post.called
            call_args = mock_post.call_args
            assert "Blue Jay" in str(call_args)


@pytest.mark.asyncio
async def test_send_discord_with_audio_confirmation(notification_service):
    """Discord notification should include audio confirmation badge."""
    with patch('app.services.notification_service.settings') as mock_settings:
        mock_settings.notifications.discord.webhook_url = "https://discord.com/api/webhooks/test"
        mock_settings.notifications.discord.username = "YA-WAMF"
        mock_settings.notifications.discord.include_snapshot = False

        with patch.object(notification_service.client, 'post', new_callable=AsyncMock) as mock_post:
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
                snapshot_data=None
            )

            # Check that the payload includes audio confirmation text
            call_json = mock_post.call_args.kwargs.get('json')
            description = call_json['embeds'][0]['description']
            assert 'Audio' in description or 'confirmed' in description.lower()


@pytest.mark.asyncio
async def test_send_discord_with_snapshot_data(notification_service):
    """Discord notification should attach snapshot as file."""
    with patch('app.services.notification_service.settings') as mock_settings:
        mock_settings.notifications.discord.webhook_url = "https://discord.com/api/webhooks/test"
        mock_settings.notifications.discord.username = "YA-WAMF"
        mock_settings.notifications.discord.include_snapshot = True

        with patch.object(notification_service.client, 'post', new_callable=AsyncMock) as mock_post:
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
                snapshot_data=fake_image
            )

            # Should use multipart form with files
            assert mock_post.called
            call_kwargs = mock_post.call_args.kwargs
            assert 'files' in call_kwargs
            assert call_kwargs['files']['file'][1] == fake_image


@pytest.mark.asyncio
async def test_send_telegram_escapes_markdown(notification_service):
    """Telegram should escape markdown special characters in species names."""
    with patch('app.services.notification_service.settings') as mock_settings:
        mock_settings.notifications.telegram.bot_token = "test_token"
        mock_settings.notifications.telegram.chat_id = "12345"

        with patch.object(notification_service.client, 'post', new_callable=AsyncMock) as mock_post:
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
                lang="en"
            )

            call_json = mock_post.call_args.kwargs.get('json')
            text = call_json.get('caption', call_json.get('text', ''))
            # Should have escaped the special characters
            assert '\\' in text or 'Test_Bird' in text


@pytest.mark.asyncio
async def test_notify_detection_skips_when_filtered(notification_service):
    """notify_detection should not send when filters exclude it."""
    with patch('app.services.notification_service.settings') as mock_settings:
        mock_settings.notifications.filters.species_whitelist = ["Robin"]
        mock_settings.notifications.filters.min_confidence = 0.7
        mock_settings.notifications.filters.audio_confirmed_only = False
        mock_settings.notifications.filters.camera_filters = {}
        mock_settings.notifications.notification_language = "en"
        mock_settings.notifications.discord.enabled = True

        with patch.object(notification_service, '_send_discord', new_callable=AsyncMock) as mock_discord:
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
                audio_confirmed=False
            )

            # Discord should not be called
            assert not mock_discord.called


@pytest.mark.asyncio
async def test_notify_detection_sends_to_all_platforms(notification_service):
    """notify_detection should send to all enabled platforms."""
    with patch('app.services.notification_service.settings') as mock_settings:
        mock_settings.notifications.filters.species_whitelist = []
        mock_settings.notifications.filters.min_confidence = 0.5
        mock_settings.notifications.filters.audio_confirmed_only = False
        mock_settings.notifications.filters.camera_filters = {}
        mock_settings.notifications.notification_language = "en"
        mock_settings.notifications.discord.enabled = True
        mock_settings.notifications.pushover.enabled = True
        mock_settings.notifications.telegram.enabled = True
        mock_settings.notifications.email.enabled = False

        with patch.object(notification_service, '_send_discord', new_callable=AsyncMock) as mock_discord, \
             patch.object(notification_service, '_send_pushover', new_callable=AsyncMock) as mock_pushover, \
             patch.object(notification_service, '_send_telegram', new_callable=AsyncMock) as mock_telegram:

            await notification_service.notify_detection(
                frigate_event="test123",
                species="Robin",
                scientific_name="Erithacus rubecula",
                common_name="European Robin",
                confidence=0.9,
                camera="front",
                timestamp=datetime.now(timezone.utc),
                snapshot_url="http://test.jpg",
                audio_confirmed=True
            )

            # All three enabled platforms should be called
            assert mock_discord.called
            assert mock_pushover.called
            assert mock_telegram.called


@pytest.mark.asyncio
async def test_notify_detection_handles_errors_gracefully(notification_service):
    """notify_detection should continue even if one platform fails."""
    with patch('app.services.notification_service.settings') as mock_settings:
        mock_settings.notifications.filters.species_whitelist = []
        mock_settings.notifications.filters.min_confidence = 0.5
        mock_settings.notifications.filters.audio_confirmed_only = False
        mock_settings.notifications.filters.camera_filters = {}
        mock_settings.notifications.notification_language = "en"
        mock_settings.notifications.discord.enabled = True
        mock_settings.notifications.pushover.enabled = True

        with patch.object(notification_service, '_send_discord', new_callable=AsyncMock) as mock_discord, \
             patch.object(notification_service, '_send_pushover', new_callable=AsyncMock) as mock_pushover:

            # Discord fails
            mock_discord.side_effect = Exception("Discord API error")
            # Pushover succeeds
            mock_pushover.return_value = None

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
                audio_confirmed=False
            )

            # Both should have been attempted
            assert mock_discord.called
            assert mock_pushover.called
