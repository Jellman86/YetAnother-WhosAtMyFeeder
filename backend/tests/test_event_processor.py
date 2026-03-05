import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from types import SimpleNamespace
from app.services.event_processor import EventProcessor

@pytest.mark.asyncio
async def test_process_mqtt_message_valid_bird():
    # Mock classifier
    classifier = MagicMock()
    classifier.classify_async = AsyncMock(return_value=[{"label": "Cardinal", "score": 0.95, "index": 1}])

    # Mock dependencies
    with patch("app.services.event_processor.frigate_client") as mock_frigate, \
         patch("app.services.event_processor.DetectionService") as MockDetectionService, \
         patch("app.services.event_processor.media_cache") as mock_cache, \
         patch("app.services.event_processor.audio_service") as mock_audio, \
         patch("app.services.event_processor.weather_service") as mock_weather, \
         patch("app.services.event_processor.notification_service") as mock_notif, \
         patch("app.services.event_processor.taxonomy_service") as mock_taxonomy, \
         patch("app.services.event_processor.Image.open"):

        # Mock EventProcessor with dependencies already patched
        processor = EventProcessor(classifier)

        mock_frigate.get_snapshot = AsyncMock(return_value=b"fakeimage")
        mock_frigate.set_sublabel = AsyncMock()

        mock_cache.cache_snapshot = AsyncMock()

        mock_taxonomy.get_names = AsyncMock(return_value={"scientific_name": "Cardinalis cardinalis", "common_name": "Northern Cardinal"})

        mock_det_service = MockDetectionService.return_value
        mock_det_service.filter_and_label.return_value = ({"label": "Cardinal", "score": 0.95}, None)
        mock_det_service.save_detection = AsyncMock(return_value=(True, True))
        mock_det_service.get_detection_by_frigate_event = AsyncMock(return_value=MagicMock(notified_at=None))

        mock_audio.find_match = AsyncMock(return_value=None)
        mock_weather.get_current_weather = AsyncMock(return_value={})
        mock_notif.notify_detection = AsyncMock(return_value=False)

        payload = b'{"after": {"id": "123", "label": "bird", "camera": "cam1", "start_time": 1700000000}}'

        await processor.process_mqtt_message(payload)

        mock_det_service.save_detection.assert_called_once()
        mock_frigate.set_sublabel.assert_called_with("123", "Cardinal")


@pytest.mark.asyncio
async def test_process_mqtt_message_skips_frigate_write_back_when_disabled():
    classifier = MagicMock()
    classifier.classify_async = AsyncMock(return_value=[{"label": "Cardinal", "score": 0.95, "index": 1}])

    with patch("app.services.event_processor.frigate_client") as mock_frigate, \
         patch("app.services.event_processor.DetectionService") as MockDetectionService, \
         patch("app.services.event_processor.media_cache") as mock_cache, \
         patch("app.services.event_processor.audio_service") as mock_audio, \
         patch("app.services.event_processor.weather_service") as mock_weather, \
         patch("app.services.event_processor.notification_service") as mock_notif, \
         patch("app.services.event_processor.taxonomy_service") as mock_taxonomy, \
         patch("app.services.event_processor.Image.open"), \
         patch("app.services.event_processor.settings.classification.write_frigate_sublabel", False, create=True):

        processor = EventProcessor(classifier)

        mock_frigate.get_snapshot = AsyncMock(return_value=b"fakeimage")
        mock_frigate.set_sublabel = AsyncMock()
        mock_cache.cache_snapshot = AsyncMock()
        mock_taxonomy.get_names = AsyncMock(return_value={"scientific_name": "Cardinalis cardinalis", "common_name": "Northern Cardinal"})

        mock_det_service = MockDetectionService.return_value
        mock_det_service.filter_and_label.return_value = ({"label": "Cardinal", "score": 0.95}, None)
        mock_det_service.save_detection = AsyncMock(return_value=(True, True))
        mock_det_service.get_detection_by_frigate_event = AsyncMock(return_value=MagicMock(notified_at=None))

        mock_audio.find_match = AsyncMock(return_value=None)
        mock_weather.get_current_weather = AsyncMock(return_value={})
        mock_notif.notify_detection = AsyncMock(return_value=False)

        payload = b'{"after": {"id": "123", "label": "bird", "camera": "cam1", "start_time": 1700000000}}'
        await processor.process_mqtt_message(payload)

        mock_det_service.save_detection.assert_called_once()
        mock_frigate.set_sublabel.assert_not_called()

@pytest.mark.asyncio
async def test_process_mqtt_message_ignore_non_bird():
    classifier = MagicMock()
    processor = EventProcessor(classifier)
    
    payload = b'{"after": {"id": "124", "label": "person", "camera": "cam1"}}'
    await processor.process_mqtt_message(payload)
    
    classifier.classify_async.assert_not_called()


def test_parse_event_skips_update_events():
    processor = EventProcessor(MagicMock())
    event = processor._parse_and_validate_event({
        "type": "update",
        "after": {
            "id": "evt-update-1",
            "label": "bird",
            "camera": "cam1",
            "start_time": 1700000000,
        },
    })
    assert event is None


def test_parse_event_accepts_end_events():
    processor = EventProcessor(MagicMock())
    event = processor._parse_and_validate_event({
        "type": "end",
        "after": {
            "id": "evt-end-1",
            "label": "bird",
            "camera": "cam1",
            "start_time": 1700000000,
        },
    })
    assert event is not None
    assert event.type == "end"


def test_parse_event_accepts_false_positive_updates():
    processor = EventProcessor(MagicMock())
    event = processor._parse_and_validate_event({
        "type": "update",
        "after": {
            "id": "evt-fp-1",
            "label": "bird",
            "camera": "cam1",
            "false_positive": True,
            "start_time": 1700000000,
        },
    })
    assert event is not None
    assert event.is_false_positive is True


@pytest.mark.asyncio
async def test_process_mqtt_message_skips_new_after_false_positive_update():
    processor = EventProcessor(MagicMock())
    processor._handle_false_positive = AsyncMock()  # type: ignore[method-assign]
    processor._classify_snapshot = AsyncMock(return_value=([{"label": "Cardinal", "score": 0.9, "index": 1}], b"img"))  # type: ignore[method-assign]

    fp_payload = b'{"type":"update","after":{"id":"evt-race-1","label":"bird","camera":"cam1","start_time":1700000000,"false_positive":true}}'
    new_payload = b'{"type":"new","after":{"id":"evt-race-1","label":"bird","camera":"cam1","start_time":1700000000}}'

    await processor.process_mqtt_message(fp_payload)
    await processor.process_mqtt_message(new_payload)

    processor._handle_false_positive.assert_called_once_with("evt-race-1")
    processor._classify_snapshot.assert_not_called()


@pytest.mark.asyncio
async def test_handle_detection_save_and_notify_uses_dispatcher_queue():
    processor = EventProcessor(MagicMock())

    event = SimpleNamespace(
        frigate_event="evt-dispatch-1",
        camera="cam1",
        start_time_ts=1700000000,
        frigate_score=0.95,
        sub_label=None,
        type="new",
        detection_dt=None,
    )
    classification = {
        "label": "Cardinal",
        "score": 0.95,
        "audio_confirmed": False,
        "audio_species": None,
        "audio_score": None,
    }
    context = {"weather_data": {}, "audio_match": None}

    processor.detection_service.save_detection = AsyncMock(return_value=(True, True))  # type: ignore[attr-defined]
    processor.notification_orchestrator.handle_notifications = AsyncMock()  # type: ignore[method-assign]

    with patch("app.services.event_processor.notification_dispatcher") as mock_dispatcher, \
         patch("app.services.event_processor.settings.classification.write_frigate_sublabel", False, create=True), \
         patch("app.services.event_processor.settings.classification.auto_video_classification", False, create=True), \
         patch("app.services.event_processor.settings.media_cache.enabled", False, create=True), \
         patch("app.services.event_processor.settings.media_cache.cache_snapshots", False, create=True):
        mock_dispatcher.enqueue = AsyncMock(return_value=True)

        await processor._handle_detection_save_and_notify(
            event=event,
            classification=classification,
            snapshot_data=b"img",
            context=context,
        )

    mock_dispatcher.enqueue.assert_awaited_once()
    processor.notification_orchestrator.handle_notifications.assert_not_awaited()
