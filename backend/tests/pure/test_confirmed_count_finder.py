"""Only a finder validated for counting may publish confirmed counts (#734)."""

from app.services.bird_crop_service import BirdCropService


def _service(model_id, *, loaded=True):
    service = BirdCropService()
    service._loaded_model_ids["accurate"] = model_id
    service._models_loaded["accurate"] = loaded
    return service


def test_loaded_rfdetr_finder_supports_confirmed_counts():
    assert _service("bird_crop_detector_accurate_rfdetr_nano").confirmed_count_finder_loaded() is True


def test_yolox_finder_keeps_the_earlier_count():
    assert _service("bird_crop_detector_accurate_yolox_tiny").confirmed_count_finder_loaded() is False


def test_selected_but_unloaded_rfdetr_finder_does_not_qualify():
    assert _service("bird_crop_detector_accurate_rfdetr_nano", loaded=False).confirmed_count_finder_loaded() is False


def test_nothing_loaded_does_not_qualify():
    assert BirdCropService().confirmed_count_finder_loaded() is False
