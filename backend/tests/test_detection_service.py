import pytest
import asyncio
import math
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from app.services.detection_service import DetectionService
from app.repositories.detection_repository import Detection

@pytest.fixture
def mock_deps():
    with patch("app.services.detection_service.get_db") as mock_get_db, \
         patch("app.services.detection_service.DetectionRepository") as MockRepo, \
         patch("app.services.detection_service.taxonomy_service") as mock_taxonomy, \
         patch("app.services.detection_service.broadcaster") as mock_broadcaster, \
         patch("app.services.detection_service.birdweather_service") as mock_birdweather, \
         patch("app.services.audio.audio_service.audio_service") as mock_audio:
        
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_get_db.return_value.__aenter__.return_value = mock_db
        
        mock_repo = MockRepo.return_value
        mock_repo.update_video_classification = AsyncMock()
        mock_taxonomy.get_names = AsyncMock(return_value={"scientific_name": "New Sci", "common_name": "New Common", "taxa_id": 123})
        
        mock_broadcaster.broadcast = AsyncMock()
        mock_birdweather.report_detection = AsyncMock(return_value=True)
        mock_audio.correlate_species = AsyncMock(return_value=(False, None, None))
        
        yield {
            "db": mock_db,
            "repo": mock_repo,
            "taxonomy": mock_taxonomy,
            "broadcaster": mock_broadcaster,
            "birdweather": mock_birdweather,
            "audio": mock_audio
        }

@pytest.mark.asyncio
async def test_apply_video_result_overrides_lower_score(mock_deps):
    classifier = MagicMock()
    service = DetectionService(classifier)
    
    # Mock existing detection with lower score
    existing = MagicMock(spec=Detection)
    existing.score = 0.5
    existing.display_name = "Old Name"
    existing.category_name = "Old Name"
    existing.detection_time = datetime.now()
    existing.camera_name = "cam1"
    existing.is_hidden = False
    existing.audio_species = None
    existing.audio_score = None
    existing.audio_confirmed = False
    existing.video_classification_label = "New Species"
    existing.video_classification_score = 0.9
    existing.video_classification_status = "completed"
    
    mock_deps["repo"].get_by_frigate_event = AsyncMock(return_value=existing)
    
    await service.apply_video_result("event1", "New Species", 0.9, 5)
    
    # Verify update_video_classification was called
    mock_deps["repo"].update_video_classification.assert_called_once()
    
    # Verify primary fields were updated (using execute on db)
    assert mock_deps["db"].execute.called
    # One of the calls should be the primary UPDATE
    update_call = [call for call in mock_deps["db"].execute.call_args_list if "UPDATE detections" in call[0][0]]
    assert len(update_call) > 0

@pytest.mark.asyncio
async def test_apply_video_result_re_evaluates_audio(mock_deps):
    classifier = MagicMock()
    service = DetectionService(classifier)
    
    # Mock existing detection with audio that didn't match old ID
    # But WILL match the new video ID
    existing = MagicMock(spec=Detection)
    existing.score = 0.5
    existing.display_name = "Unknown Bird"
    existing.category_name = "Unknown Bird"
    existing.detection_time = datetime.now()
    existing.camera_name = "cam1"
    existing.is_hidden = False
    existing.audio_species = "Blue Jay"
    existing.audio_score = 0.9
    existing.audio_confirmed = False
    existing.video_classification_label = "Blue Jay"
    existing.video_classification_score = 0.8
    existing.video_classification_status = "completed"
    
    mock_deps["repo"].get_by_frigate_event = AsyncMock(return_value=existing)
    
    # Mock successful audio correlation
    mock_deps["audio"].correlate_species = AsyncMock(return_value=(True, "Blue Jay", 0.9))
    
    await service.apply_video_result("event1", "Blue Jay", 0.8, 10)
    
    # Verify audio correlation was called with the scientific name
    mock_deps["audio"].correlate_species.assert_called_once()
    
    # Verify the update query set audio_confirmed to 1
    update_call = [call for call in mock_deps["db"].execute.call_args_list if "UPDATE detections" in call.args[0]]
    args = update_call[0].args
    params = args[1]
    
    # Find the index of audio_confirmed in the query
    assert params[7] == 1 # audio_confirmed should be True (1)


@pytest.mark.asyncio
async def test_apply_video_result_normalizes_birder_taxonomy_labels(mock_deps):
    classifier = MagicMock()
    service = DetectionService(classifier)

    existing = MagicMock(spec=Detection)
    existing.score = 0.1
    existing.display_name = "Unknown Bird"
    existing.category_name = "Unknown Bird"
    existing.sub_label = None
    existing.frigate_score = 0.0
    existing.detection_time = datetime.now()
    existing.camera_name = "cam1"
    existing.is_hidden = False
    existing.audio_species = None
    existing.audio_score = None
    existing.audio_confirmed = False
    existing.video_classification_label = None
    existing.video_classification_score = None
    existing.video_classification_status = "pending"

    mock_deps["repo"].get_by_frigate_event = AsyncMock(return_value=existing)
    mock_deps["taxonomy"].get_names = AsyncMock(return_value={"scientific_name": "Panthera tigris", "common_name": "Tiger", "taxa_id": 321})

    await service.apply_video_result(
        "event1",
        "04853_Animalia_Chordata_Mammalia_Carnivora_Felidae_Panthera_tigris",
        0.9,
        5,
    )

    mock_deps["repo"].update_video_classification.assert_called_once()
    assert mock_deps["repo"].update_video_classification.call_args.kwargs["label"] == "Panthera tigris"
    mock_deps["taxonomy"].get_names.assert_called_with("Panthera tigris")


@pytest.mark.asyncio
async def test_apply_video_result_does_not_override_known_species_with_lower_score(mock_deps):
    classifier = MagicMock()
    service = DetectionService(classifier)

    existing = MagicMock(spec=Detection)
    existing.score = 0.95
    existing.display_name = "Great Tit"
    existing.category_name = "Great Tit"
    existing.detection_time = datetime.now()
    existing.camera_name = "cam1"
    existing.is_hidden = False
    existing.audio_species = None
    existing.audio_score = None
    existing.audio_confirmed = False
    existing.video_classification_label = None
    existing.video_classification_score = None
    existing.video_classification_status = "pending"

    mock_deps["repo"].get_by_frigate_event = AsyncMock(return_value=existing)

    await service.apply_video_result("event1", "Blue Jay", 0.40, 2)

    mock_deps["repo"].update_video_classification.assert_called_once()
    # No primary UPDATE should run when lower-confidence video result does not beat a known species
    primary_updates = [call for call in mock_deps["db"].execute.call_args_list if "UPDATE detections" in call.args[0]]
    assert primary_updates == []
    mock_deps["audio"].correlate_species.assert_not_called()


@pytest.mark.asyncio
async def test_apply_video_result_does_not_override_when_video_stays_below_floor(mock_deps):
    classifier = MagicMock()
    service = DetectionService(classifier)

    existing = MagicMock(spec=Detection)
    existing.score = 0.35
    existing.display_name = "Great Tit"
    existing.category_name = "Parus major"
    existing.sub_label = None
    existing.frigate_score = 0.6
    existing.detection_time = datetime.now()
    existing.camera_name = "cam1"
    existing.is_hidden = False
    existing.audio_species = None
    existing.audio_score = None
    existing.audio_confirmed = False
    existing.video_classification_label = None
    existing.video_classification_score = None
    existing.video_classification_status = "pending"

    mock_deps["repo"].get_by_frigate_event = AsyncMock(return_value=existing)

    # Even for a low-confidence primary label, auto video should not promote a
    # candidate that never clears the classifier floor.
    await service.apply_video_result("event1", "Blue Jay", 0.39, 2)

    mock_deps["repo"].update_video_classification.assert_called_once()
    primary_updates = [call for call in mock_deps["db"].execute.call_args_list if "UPDATE detections" in call.args[0]]
    assert primary_updates == []
    mock_deps["audio"].correlate_species.assert_not_called()


@pytest.mark.asyncio
async def test_apply_video_result_overrides_low_confidence_primary_when_video_clears_floor(mock_deps):
    classifier = MagicMock()
    service = DetectionService(classifier)

    existing = MagicMock(spec=Detection)
    existing.score = 0.43
    existing.display_name = "Anna's Hummingbird"
    existing.category_name = "Calypte anna"
    existing.scientific_name = "Calypte anna"
    existing.common_name = "Anna's Hummingbird"
    existing.sub_label = None
    existing.frigate_score = 0.55
    existing.detection_time = datetime.now()
    existing.camera_name = "cam1"
    existing.is_hidden = False
    existing.audio_species = None
    existing.audio_score = None
    existing.audio_confirmed = False
    existing.video_classification_label = None
    existing.video_classification_score = None
    existing.video_classification_status = "pending"
    existing.frigate_event = "event1"
    existing.manual_tagged = False
    existing.is_favorite = False
    existing.video_classification_provider = None
    existing.video_classification_backend = None
    existing.video_classification_model_id = None
    existing.video_classification_timestamp = None

    updated = MagicMock(spec=Detection)
    updated.frigate_event = "event1"
    updated.display_name = "Ruby-throated Hummingbird"
    updated.category_name = "Archilochus colubris"
    updated.scientific_name = "Archilochus colubris"
    updated.common_name = "Ruby-throated Hummingbird"
    updated.taxa_id = 111
    updated.score = 0.434
    updated.detection_time = existing.detection_time
    updated.camera_name = existing.camera_name
    updated.is_hidden = False
    updated.is_favorite = False
    updated.manual_tagged = False
    updated.audio_confirmed = False
    updated.audio_species = None
    updated.audio_score = None
    updated.video_classification_label = "Archilochus colubris"
    updated.video_classification_score = 0.434
    updated.video_classification_status = "completed"
    updated.video_classification_provider = "cuda"
    updated.video_classification_backend = "onnxruntime"
    updated.video_classification_model_id = "rope_vit_b14_inat21"
    updated.video_classification_timestamp = datetime.now()

    mock_deps["repo"].get_by_frigate_event = AsyncMock(side_effect=[existing, updated])
    mock_deps["taxonomy"].get_names = AsyncMock(
        return_value={
            "scientific_name": "Archilochus colubris",
            "common_name": "Ruby-throated Hummingbird",
            "taxa_id": 111,
        }
    )

    await service.apply_video_result("event1", "Archilochus colubris", 0.434, 2)

    primary_updates = [call for call in mock_deps["db"].execute.call_args_list if "UPDATE detections" in call.args[0]]
    assert len(primary_updates) == 1
    params = primary_updates[0].args[1]
    assert params[0] == "Ruby-throated Hummingbird"
    assert params[1] == "Archilochus colubris"
    assert params[2] == 0.434
    mock_deps["broadcaster"].broadcast.assert_awaited()


@pytest.mark.asyncio
async def test_apply_video_result_respects_frigate_sublabel_disagreement_guard(mock_deps):
    classifier = MagicMock()
    service = DetectionService(classifier)

    existing = MagicMock(spec=Detection)
    existing.score = 0.60
    existing.display_name = "Woodpigeon"
    existing.category_name = "Columba palumbus"
    existing.sub_label = "Columba palumbus"
    existing.frigate_score = 0.82
    existing.detection_time = datetime.now()
    existing.camera_name = "cam1"
    existing.is_hidden = False
    existing.audio_species = None
    existing.audio_score = None
    existing.audio_confirmed = False
    existing.video_classification_label = None
    existing.video_classification_score = None
    existing.video_classification_status = "pending"

    mock_deps["repo"].get_by_frigate_event = AsyncMock(return_value=existing)

    # Video disagrees with Frigate sublabel and is not confident enough to force override.
    await service.apply_video_result("event1", "Aegithalos caudatus", 0.80, 3688)

    mock_deps["repo"].update_video_classification.assert_called_once()
    primary_updates = [call for call in mock_deps["db"].execute.call_args_list if "UPDATE detections" in call.args[0]]
    assert primary_updates == []
    mock_deps["audio"].correlate_species.assert_not_called()


@pytest.mark.asyncio
async def test_save_detection_falls_back_when_taxonomy_lookup_times_out(mock_deps):
    classifier = MagicMock()
    service = DetectionService(classifier)

    async def _slow_taxonomy(_label):
        await asyncio.sleep(0.05)
        return {"scientific_name": "ShouldNotReach"}

    mock_deps["taxonomy"].get_names = AsyncMock(side_effect=_slow_taxonomy)
    mock_deps["repo"].upsert_if_higher_score = AsyncMock(return_value=(True, False))
    mock_deps["repo"].get_by_frigate_event = AsyncMock(return_value=None)

    with patch("app.services.detection_service.TAXONOMY_LOOKUP_TIMEOUT_SECONDS", 0.01), \
         patch("app.services.detection_service.create_background_task", side_effect=lambda coro, name=None: coro.close()), \
         patch("app.services.detection_service.log") as mock_log:
        changed, inserted = await service.save_detection(
            frigate_event="evt-tax-timeout",
            camera="cam1",
            start_time=1700000000,
            classification={"label": "Parus major", "score": 0.93, "index": 1},
            frigate_score=0.88,
            sub_label=None,
        )

    assert changed is True
    assert inserted is True
    detection = mock_deps["repo"].upsert_if_higher_score.await_args.args[0]
    assert detection.scientific_name == "Parus major"
    assert detection.common_name is None
    assert detection.display_name == "Parus major"
    mock_log.warning.assert_any_call(
        "Taxonomy lookup timed out during detection save",
        label="Parus major",
        timeout_seconds=0.01,
    )


def test_filter_and_label_rejects_non_finite_score():
    service = DetectionService(MagicMock())

    result, reason = service.filter_and_label(
        {"label": "Blue Jay", "score": math.nan, "index": 4},
        "evt-invalid-score",
    )

    assert result is None
    assert reason == "invalid_score"


@pytest.mark.asyncio
async def test_save_detection_skips_structured_blocked_species_by_taxa_id(mock_deps):
    classifier = MagicMock()
    service = DetectionService(classifier)

    with patch("app.services.detection_service.settings") as mock_settings, \
         patch("app.services.detection_service.create_background_task", side_effect=lambda coro, name=None: coro.close()):
        mock_settings.classification.blocked_labels = []
        mock_settings.classification.blocked_species = [
            {
                "scientific_name": "Columba livia",
                "common_name": "Rock Pigeon",
                "taxa_id": 3017,
            }
        ]
        mock_settings.classification.display_common_names = True
        mock_settings.classification.threshold = 0.7
        mock_settings.classification.min_confidence = 0.4
        mock_deps["taxonomy"].get_names = AsyncMock(
            return_value={"scientific_name": "Columba livia", "common_name": "Rock Pigeon", "taxa_id": 3017}
        )

        changed, inserted = await service.save_detection(
            frigate_event="evt-blocked-save",
            camera="cam1",
            start_time=1700000000,
            classification={"label": "Rock Pigeon", "score": 0.93, "index": 1},
            frigate_score=0.88,
            sub_label=None,
        )

    assert changed is False
    assert inserted is False
    mock_deps["repo"].upsert_if_higher_score.assert_not_called()


@pytest.mark.asyncio
async def test_save_detection_treats_noncanonical_model_labels_as_unknown_bird(mock_deps):
    classifier = MagicMock()
    service = DetectionService(classifier)

    mock_deps["taxonomy"].get_names = AsyncMock(
        return_value={"scientific_name": "Life", "common_name": "Life", "taxa_id": 1}
    )
    mock_deps["repo"].upsert_if_higher_score = AsyncMock(return_value=(True, True))
    mock_deps["repo"].get_by_frigate_event = AsyncMock(return_value=None)

    with patch("app.services.detection_service.create_background_task", side_effect=lambda coro, name=None: coro.close()):
        changed, inserted = await service.save_detection(
            frigate_event="evt-life-label",
            camera="cam1",
            start_time=1700000000,
            classification={"label": "Life (life)", "score": 0.93, "index": 1},
            frigate_score=0.88,
            sub_label=None,
        )

    assert changed is True
    assert inserted is True
    detection = mock_deps["repo"].upsert_if_higher_score.await_args.args[0]
    assert detection.display_name == "Unknown Bird"
    assert detection.category_name == "Life (life)"
    assert detection.scientific_name is None
    assert detection.common_name is None
    assert detection.taxa_id is None
    broadcast_payload = mock_deps["broadcaster"].broadcast.await_args.args[0]
    assert broadcast_payload["data"]["display_name"] == "Unknown Bird"
    assert broadcast_payload["data"]["category_name"] == "Unknown Bird"
    assert broadcast_payload["data"]["scientific_name"] is None
    assert broadcast_payload["data"]["common_name"] is None
    assert broadcast_payload["data"]["taxa_id"] is None
    assert broadcast_payload["data"]["timestamp"].endswith("Z")
    mock_deps["birdweather"].report_detection.assert_not_called()


@pytest.mark.asyncio
async def test_save_detection_broadcasts_explicit_utc_timestamp(mock_deps):
    classifier = MagicMock()
    service = DetectionService(classifier)

    mock_deps["taxonomy"].get_names = AsyncMock(
        return_value={"scientific_name": "Columba palumbus", "common_name": "Common Wood-Pigeon", "taxa_id": 3048}
    )
    mock_deps["repo"].upsert_if_higher_score = AsyncMock(return_value=(True, True))
    mock_deps["repo"].get_by_frigate_event = AsyncMock(return_value=None)

    with patch("app.services.detection_service.create_background_task", side_effect=lambda coro, name=None: coro.close()):
        changed, inserted = await service.save_detection(
            frigate_event="evt-timestamp-z",
            camera="cam1",
            start_time=1774952605.446665,
            classification={"label": "Columba palumbus", "score": 0.93, "index": 1},
            frigate_score=0.88,
            sub_label=None,
        )

    assert changed is True
    assert inserted is True
    broadcast_payload = mock_deps["broadcaster"].broadcast.await_args.args[0]
    assert broadcast_payload["data"]["timestamp"] == "2026-03-31T10:23:25.446665Z"


@pytest.mark.asyncio
async def test_save_detection_blocks_hidden_noncanonical_label_when_unknown_bird_is_blocked(mock_deps):
    classifier = MagicMock()
    service = DetectionService(classifier)

    mock_deps["taxonomy"].get_names = AsyncMock(
        return_value={"scientific_name": "Life", "common_name": "Life", "taxa_id": 1}
    )

    with patch("app.services.detection_service.settings.classification.blocked_labels", ["Unknown Bird"]):
        changed, inserted = await service.save_detection(
            frigate_event="evt-life-blocked",
            camera="cam1",
            start_time=1700000000,
            classification={"label": "Life (life)", "score": 0.93, "index": 1},
            frigate_score=0.88,
            sub_label=None,
        )

    assert changed is False
    assert inserted is False
    mock_deps["repo"].upsert_if_higher_score.assert_not_called()
    mock_deps["broadcaster"].broadcast.assert_not_called()


@pytest.mark.asyncio
async def test_apply_video_result_does_not_override_known_species_with_hidden_noncanonical_label(mock_deps):
    classifier = MagicMock()
    service = DetectionService(classifier)

    existing = MagicMock(spec=Detection)
    existing.score = 0.2
    existing.display_name = "Great Tit"
    existing.category_name = "Parus major"
    existing.scientific_name = "Parus major"
    existing.common_name = "Great Tit"
    existing.sub_label = None
    existing.frigate_score = 0.0
    existing.detection_time = datetime.now()
    existing.camera_name = "cam1"
    existing.is_hidden = False
    existing.audio_species = None
    existing.audio_score = None
    existing.audio_confirmed = False
    existing.video_classification_label = None
    existing.video_classification_score = None
    existing.video_classification_status = "pending"

    mock_deps["repo"].get_by_frigate_event = AsyncMock(return_value=existing)
    mock_deps["taxonomy"].get_names = AsyncMock(return_value={"scientific_name": "Life", "common_name": "Life", "taxa_id": 1})

    await service.apply_video_result("event1", "Life (life)", 0.95, 2)

    mock_deps["repo"].update_video_classification.assert_called_once()
    primary_updates = [call for call in mock_deps["db"].execute.call_args_list if "UPDATE detections" in call.args[0]]
    assert primary_updates == []
    mock_deps["audio"].correlate_species.assert_not_called()


@pytest.mark.asyncio
async def test_apply_video_result_records_blocked_flag_and_skips_promotion(mock_deps):
    """When video label is blocked, video_result_blocked=True is stored but primary fields stay unchanged."""
    classifier = MagicMock()
    service = DetectionService(classifier)

    existing = MagicMock(spec=Detection)
    existing.score = 0.85
    existing.display_name = "House Sparrow"
    existing.category_name = "House Sparrow"
    existing.detection_time = datetime.now()
    existing.camera_name = "cam1"
    existing.is_hidden = False
    existing.audio_species = None
    existing.audio_score = None
    existing.audio_confirmed = False
    existing.video_classification_label = None
    existing.video_classification_score = None
    existing.video_classification_status = "pending"

    mock_deps["repo"].get_by_frigate_event = AsyncMock(return_value=existing)

    with patch("app.services.detection_service.settings") as mock_settings, \
         patch("app.services.detection_service.create_background_task", side_effect=lambda coro, name=None: coro.close()):
        mock_settings.classification.blocked_labels = ["House Sparrow"]
        mock_settings.classification.blocked_species = []
        mock_settings.classification.min_detection_confidence = 0.6
        mock_settings.frigate.trust_frigate_sublabels = False

        await service.apply_video_result("event1", "House Sparrow", 0.92, 5)

    # update_video_classification must be called with blocked=True
    mock_deps["repo"].update_video_classification.assert_called_once()
    call_kwargs = mock_deps["repo"].update_video_classification.call_args.kwargs
    assert call_kwargs.get("blocked") is True

    # Primary species fields must NOT be updated (no UPDATE detections statement)
    primary_updates = [call for call in mock_deps["db"].execute.call_args_list if "UPDATE detections" in call.args[0]]
    assert primary_updates == []

    # No audio correlation or broadcast since we returned early
    mock_deps["audio"].correlate_species.assert_not_called()
    mock_deps["broadcaster"].broadcast.assert_not_called()
