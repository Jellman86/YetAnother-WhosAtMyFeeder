from app.services.photo_quality import materially_improves_photo


def test_tiny_weak_crop_does_not_displace_clear_incumbent():
    incumbent = {"classifier_score": 0.924, "image_quality_score": 0.94, "crop_confidence": 0.317}
    tiny = {"classifier_score": 0.943, "image_quality_score": 0.7, "crop_confidence": 0.12}
    assert not materially_improves_photo(tiny, incumbent)


def test_materially_better_photo_can_replace_incumbent():
    incumbent = {"classifier_score": 0.85, "image_quality_score": 0.55, "crop_confidence": 0.4}
    better = {"classifier_score": 0.94, "image_quality_score": 0.9, "crop_confidence": 0.8}
    assert materially_improves_photo(better, incumbent)


def test_marginal_photo_change_does_not_cause_churn():
    incumbent = {"classifier_score": 0.94, "image_quality_score": 0.9, "crop_confidence": 0.8}
    assert not materially_improves_photo({**incumbent, "classifier_score": 0.945}, incumbent)


def test_a_quality_measured_on_one_side_only_is_not_compared():
    incumbent = {"classifier_score": 0.8, "image_quality_score": 0.95, "crop_confidence": 0.9}
    challenger = {"classifier_score": 0.99, "crop_confidence": 0.9}
    assert materially_improves_photo(challenger, incumbent)
