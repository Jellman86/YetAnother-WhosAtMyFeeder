import pytest

from app.utils.frigate import parse_sub_label


@pytest.mark.parametrize(
    ("payload", "expected_label", "expected_score"),
    [
        (["Columba palumbus", 0.79], "Columba palumbus", 0.79),
        ('["Parus major", 0.91]', "Parus major", 0.91),
        ({"label": "Cyanistes caeruleus", "score": 0.87}, "Cyanistes caeruleus", 0.87),
        ("Erithacus rubecula", "Erithacus rubecula", None),
    ],
)
def test_parse_sub_label_preserves_frigate_classification_confidence(payload, expected_label, expected_score):
    parsed = parse_sub_label(payload)

    assert parsed.label == expected_label
    assert parsed.score == pytest.approx(expected_score) if expected_score is not None else parsed.score is None


@pytest.mark.parametrize("score", [float("nan"), float("inf"), -0.1, 1.1, "invalid"])
def test_parse_sub_label_rejects_invalid_confidence_without_losing_label(score):
    parsed = parse_sub_label(["Columba palumbus", score])

    assert parsed.label == "Columba palumbus"
    assert parsed.score is None
