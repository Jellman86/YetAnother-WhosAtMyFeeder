import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from types import SimpleNamespace
from app.services.event_processor import EventProcessor

@pytest.mark.asyncio
async def test_process_mqtt_message_valid_bird():
    # Mock classifier
    classifier = MagicMock()
    classifier.classify_async_live = AsyncMock(return_value=[{"label": "Cardinal", "score": 0.95, "index": 1}])

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
    classifier.classify_async_live = AsyncMock(return_value=[{"label": "Cardinal", "score": 0.95, "index": 1}])

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


def test_parse_event_skips_end_events():
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
    assert event is None


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
async def test_process_mqtt_message_skips_end_event_classification():
    processor = EventProcessor(MagicMock())
    processor._classify_snapshot = AsyncMock(  # type: ignore[method-assign]
        return_value=([{"label": "Cardinal", "score": 0.9, "index": 1}], b"img")
    )

    end_payload = b'{"type":"end","after":{"id":"evt-end-skip-1","label":"bird","camera":"cam1","start_time":1700000000}}'
    await processor.process_mqtt_message(end_payload)

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


@pytest.mark.asyncio
async def test_handle_detection_save_and_notify_schedules_high_quality_snapshot_replacement():
    processor = EventProcessor(MagicMock())

    event = SimpleNamespace(
        frigate_event="evt-hq-1",
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
         patch("app.services.event_processor.media_cache") as mock_cache, \
         patch("app.services.event_processor.high_quality_snapshot_service") as mock_hq, \
         patch("app.services.event_processor.settings.classification.write_frigate_sublabel", False, create=True), \
         patch("app.services.event_processor.settings.classification.auto_video_classification", False, create=True), \
         patch("app.services.event_processor.settings.media_cache.enabled", True, create=True), \
         patch("app.services.event_processor.settings.media_cache.cache_snapshots", True, create=True), \
         patch("app.services.event_processor.settings.media_cache.high_quality_event_snapshots", True, create=True):
        mock_dispatcher.enqueue = AsyncMock(return_value=True)
        mock_cache.cache_snapshot = AsyncMock()
        mock_hq.schedule_replacement = MagicMock(return_value=True)

        await processor._handle_detection_save_and_notify(
            event=event,
            classification=classification,
            snapshot_data=b"img",
            context=context,
        )

    mock_cache.cache_snapshot.assert_awaited_once_with("evt-hq-1", b"img")
    mock_hq.schedule_replacement.assert_called_once_with("evt-hq-1")


@pytest.mark.asyncio
async def test_handle_detection_save_and_notify_skips_high_quality_snapshot_replacement_when_unchanged():
    processor = EventProcessor(MagicMock())

    event = SimpleNamespace(
        frigate_event="evt-hq-unchanged",
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

    processor.detection_service.save_detection = AsyncMock(return_value=(False, False))  # type: ignore[attr-defined]
    processor.notification_orchestrator.handle_notifications = AsyncMock()  # type: ignore[method-assign]

    with patch("app.services.event_processor.notification_dispatcher") as mock_dispatcher, \
         patch("app.services.event_processor.media_cache") as mock_cache, \
         patch("app.services.event_processor.high_quality_snapshot_service") as mock_hq, \
         patch("app.services.event_processor.settings.classification.write_frigate_sublabel", False, create=True), \
         patch("app.services.event_processor.settings.classification.auto_video_classification", False, create=True), \
         patch("app.services.event_processor.settings.media_cache.enabled", True, create=True), \
         patch("app.services.event_processor.settings.media_cache.cache_snapshots", True, create=True), \
         patch("app.services.event_processor.settings.media_cache.high_quality_event_snapshots", True, create=True):
        mock_dispatcher.enqueue = AsyncMock(return_value=True)
        mock_cache.cache_snapshot = AsyncMock()
        mock_hq.schedule_replacement = MagicMock(return_value=True)

        await processor._handle_detection_save_and_notify(
            event=event,
            classification=classification,
            snapshot_data=b"img",
            context=context,
        )

    mock_cache.cache_snapshot.assert_not_awaited()
    mock_hq.schedule_replacement.assert_not_called()


@pytest.mark.asyncio
async def test_process_mqtt_message_logs_filter_drop_reason():
    classifier = MagicMock()
    processor = EventProcessor(classifier)
    processor._classify_snapshot = AsyncMock(  # type: ignore[method-assign]
        return_value=([{"label": "Sparrow", "score": 0.12, "index": 1}], b"img")
    )
    processor._handle_detection_save_and_notify = AsyncMock()  # type: ignore[method-assign]
    processor.detection_service.filter_and_label = MagicMock(return_value=(None, "low_confidence"))  # type: ignore[attr-defined]

    payload = b'{"type":"new","after":{"id":"evt-drop-1","label":"bird","camera":"cam1","start_time":1700000000}}'

    with patch("app.services.event_processor.log") as mock_log:
        await processor.process_mqtt_message(payload)

    processor._handle_detection_save_and_notify.assert_not_called()
    mock_log.info.assert_any_call(
        "Dropping MQTT event after classification filter",
        event_id="evt-drop-1",
        reason="low_confidence",
        label="Sparrow",
        score=0.12,
    )
    status = processor.get_status()
    assert status["started_events"] == 1
    assert status["dropped_events"] == 1
    assert status["drop_reasons"]["filter_low_confidence"] == 1


@pytest.mark.asyncio
async def test_process_mqtt_message_logs_stage_timeout_for_classification():
    classifier = MagicMock()
    processor = EventProcessor(classifier)
    processor._handle_detection_save_and_notify = AsyncMock()  # type: ignore[method-assign]

    async def _slow_classify(_event):
        await asyncio.sleep(0.05)
        return ([{"label": "Sparrow", "score": 0.82, "index": 1}], b"img")

    processor._classify_snapshot = _slow_classify  # type: ignore[method-assign]
    payload = b'{"type":"new","after":{"id":"evt-timeout-1","label":"bird","camera":"cam1","start_time":1700000000}}'

    with patch("app.services.event_processor.log") as mock_log, \
         patch("app.services.event_processor.EVENT_STAGE_TIMEOUT_CLASSIFY_SECONDS", 0.01):
        await processor.process_mqtt_message(payload)

    processor._handle_detection_save_and_notify.assert_not_called()
    mock_log.warning.assert_any_call(
        "MQTT event stage timed out",
        event_id="evt-timeout-1",
        stage="classify_snapshot",
        timeout_seconds=0.01,
    )
    status = processor.get_status()
    assert status["stage_timeouts"]["classify_snapshot"] == 1
    assert status["drop_reasons"]["classify_snapshot_unavailable"] == 1
    assert status["critical_failures"] == 1


@pytest.mark.asyncio
async def test_process_mqtt_message_records_distinct_overload_drop_reason():
    classifier = MagicMock()
    processor = EventProcessor(classifier)
    processor._handle_detection_save_and_notify = AsyncMock()  # type: ignore[method-assign]

    async def _overloaded_classify(_event):
        raise RuntimeError("classify_snapshot_overloaded")

    processor._classify_snapshot = _overloaded_classify  # type: ignore[method-assign]
    payload = b'{"type":"new","after":{"id":"evt-overload-1","label":"bird","camera":"cam1","start_time":1700000000}}'

    await processor.process_mqtt_message(payload)

    status = processor.get_status()
    assert status["drop_reasons"]["classify_snapshot_overloaded"] == 1
    assert "classify_snapshot_unavailable" not in status["drop_reasons"]


@pytest.mark.asyncio
async def test_process_mqtt_message_audio_taxonomy_lookup_timeout_falls_back():
    classifier = MagicMock()
    processor = EventProcessor(classifier)
    processor._handle_detection_save_and_notify = AsyncMock()  # type: ignore[method-assign]
    processor._classify_snapshot = AsyncMock(  # type: ignore[method-assign]
        return_value=([{"label": "Blue Tit", "score": 0.9, "index": 1}], b"img")
    )
    processor.detection_service.filter_and_label = MagicMock(  # type: ignore[attr-defined]
        return_value=({"label": "Blue Tit", "score": 0.9, "index": 1}, None)
    )

    audio_match = MagicMock()
    audio_match.species = "Woodpigeon"
    audio_match.scientific_name = None
    audio_match.confidence = 0.88
    processor._gather_context_data = AsyncMock(  # type: ignore[method-assign]
        return_value={"audio_match": audio_match, "weather_data": {}}
    )

    async def _slow_taxonomy(_query):
        await asyncio.sleep(0.05)
        return {"scientific_name": "columba palumbus", "common_name": "Common Wood-Pigeon"}

    payload = b'{"type":"new","after":{"id":"evt-audio-tax-timeout","label":"bird","camera":"cam1","start_time":1700000000}}'

    with patch("app.services.event_processor.log") as mock_log, \
         patch("app.services.event_processor.taxonomy_service.get_names", new=AsyncMock(side_effect=_slow_taxonomy)), \
         patch("app.services.event_processor.EVENT_TAXONOMY_LOOKUP_TIMEOUT_SECONDS", 0.01):
        await processor.process_mqtt_message(payload)

    processor._handle_detection_save_and_notify.assert_called_once()
    mock_log.warning.assert_any_call(
        "Taxonomy alias lookup timed out during audio correlation",
        event_id="evt-audio-tax-timeout",
        query="Blue Tit",
        timeout_seconds=0.01,
    )


@pytest.mark.asyncio
async def test_process_mqtt_message_status_tracks_completed_event():
    classifier = MagicMock()
    processor = EventProcessor(classifier)
    processor._classify_snapshot = AsyncMock(  # type: ignore[method-assign]
        return_value=([{"label": "Sparrow", "score": 0.95, "index": 1}], b"img")
    )
    processor._gather_context_data = AsyncMock(  # type: ignore[method-assign]
        return_value={"audio_match": None, "weather_data": {}}
    )
    processor._correlate_audio = AsyncMock(return_value={  # type: ignore[method-assign]
        "label": "Sparrow",
        "score": 0.95,
        "index": 1,
        "audio_confirmed": False,
        "audio_species": None,
        "audio_score": None,
    })
    processor._handle_detection_save_and_notify = AsyncMock()  # type: ignore[method-assign]
    processor.detection_service.filter_and_label = MagicMock(  # type: ignore[attr-defined]
        return_value=({"label": "Sparrow", "score": 0.95, "index": 1}, None)
    )

    payload = b'{"type":"new","after":{"id":"evt-done-1","label":"bird","camera":"cam1","start_time":1700000000}}'
    await processor.process_mqtt_message(payload)

    status = processor.get_status()
    assert status["started_events"] == 1
    assert status["completed_events"] == 1
    assert status["dropped_events"] == 0
    assert status["critical_failures"] == 0
