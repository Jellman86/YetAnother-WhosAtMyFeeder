"""The bundle and the backend must agree on what a build calls itself (#432).

A stable image stamped its bundle `2.19.4-stable+hash` while the backend said `2.19.4+hash`;
the browser read the two as different deployments, reloaded once and warned on every load.
"""

import re
from pathlib import Path

from app.version import RELEASE_LIKE_CHANNELS, compose_app_version, is_release_like_channel, normalize_app_branch


def test_release_like_channels_carry_no_label():
    for channel in RELEASE_LIKE_CHANNELS:
        assert compose_app_version("2.19.4", channel, "e6f3ea6") == "2.19.4+e6f3ea6"


def test_a_tag_name_is_a_release_not_a_branch():
    assert normalize_app_branch("v2.19.4") == "main"
    assert normalize_app_branch("v2.7.9.1") == "main"
    assert is_release_like_channel("v2.19.4")
    assert compose_app_version("2.19.4", "v2.19.4", "e6f3ea6") == "2.19.4+e6f3ea6"


def test_a_working_channel_keeps_its_label():
    assert normalize_app_branch("dev") == "dev"
    assert compose_app_version("2.19.4", "dev", "e6f3ea6") == "2.19.4-dev+e6f3ea6"


def test_the_bundle_uses_the_same_channel_list():
    frontend = (
        Path(__file__).resolve().parents[2] / "apps" / "ui" / "src" / "lib" / "app" / "app-version.ts"
    ).read_text(encoding="utf-8")
    match = re.search(r"RELEASE_LIKE_CHANNELS = \[([^\]]*)\]", frontend)
    assert match, "the frontend no longer declares RELEASE_LIKE_CHANNELS"
    frontend_channels = tuple(re.findall(r"'([^']+)'", match.group(1)))
    assert frontend_channels == RELEASE_LIKE_CHANNELS
