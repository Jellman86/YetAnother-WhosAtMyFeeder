from app.routers.backfill import _build_skipped_message


def test_build_skipped_message_without_reasons():
    assert _build_skipped_message(0, None) == ""
    assert _build_skipped_message(3, None) == "3 skipped"


def test_build_skipped_message_already_exists_only():
    assert _build_skipped_message(4, {"already_exists": 4}) == "4 already existed"


def test_build_skipped_message_mixed_reasons():
    msg = _build_skipped_message(
        15,
        {
            "already_exists": 5,
            "low_confidence": 7,
            "blocked_label": 3,
        },
    )
    assert msg == "5 already existed, 10 skipped by filters/validation"
