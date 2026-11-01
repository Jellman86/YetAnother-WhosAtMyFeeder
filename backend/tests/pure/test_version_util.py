from app.utils.version import is_update_available, parse_version


def test_parse_version_accepts_common_forms():
    assert parse_version("2.12.0") == (2, 12, 0)
    assert parse_version("v2.12.0") == (2, 12, 0)
    assert parse_version("2.12.0-dev+abc1234") == (2, 12, 0)
    assert parse_version("2.7.9.1") == (2, 7, 9, 1)


def test_parse_version_returns_none_for_unparseable():
    assert parse_version("unknown") is None
    assert parse_version("") is None
    assert parse_version(None) is None


def test_update_available_when_latest_is_newer():
    assert is_update_available("2.10.0", "2.12.0") is True
    assert is_update_available("2.9.15", "2.12.0") is True
    assert is_update_available("2.12.0", "2.12.1") is True


def test_no_update_when_same_or_older():
    assert is_update_available("2.12.0", "2.12.0") is False
    assert is_update_available("2.12.0", "2.11.0") is False


def test_dev_build_of_the_same_release_is_not_an_update():
    # Running the unreleased 2.12.0 dev build; latest release is 2.12.0.
    assert is_update_available("2.12.0-dev+abc1234", "v2.12.0") is False


def test_dev_build_ahead_of_latest_release_does_not_nag():
    assert is_update_available("2.13.0-dev+abc1234", "v2.12.0") is False


def test_unparseable_versions_never_report_an_update():
    assert is_update_available("unknown", "2.12.0") is False
    assert is_update_available("2.12.0", None) is False
