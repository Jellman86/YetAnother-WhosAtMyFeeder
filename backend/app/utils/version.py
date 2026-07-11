"""Pure version parsing and comparison helpers for the update check.

Kept free of I/O so the "is a newer release available?" decision is deterministic
and unit-testable without a network or the GitHub API.
"""

import re

_SEMVER_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:\.(\d+))?")


def parse_version(value: str | None) -> tuple[int, ...] | None:
    """Parse the numeric release core of a version string.

    Accepts forms like ``2.12.0``, ``v2.12.0``, ``2.12.0-dev+abc1234`` and ``2.7.9.1``;
    the pre-release/build suffix is ignored. Returns ``None`` for anything unparseable
    (e.g. ``unknown``), so callers treat an unknown version as "can't compare".
    """
    if not value:
        return None
    match = _SEMVER_RE.match(str(value).strip())
    if not match:
        return None
    return tuple(int(group) for group in match.groups() if group is not None)


def is_update_available(current: str | None, latest: str | None) -> bool:
    """Return True only when ``latest`` is a strictly newer release than ``current``.

    Comparison is on the numeric release core only, so a dev build of the same version
    (``2.12.0-dev+abc`` vs release ``2.12.0``) is not "an update", and a dev build ahead
    of the latest release does not nag. Unparseable versions never report an update.
    """
    current_parsed = parse_version(current)
    latest_parsed = parse_version(latest)
    if current_parsed is None or latest_parsed is None:
        return False
    length = max(len(current_parsed), len(latest_parsed))
    padded_current = current_parsed + (0,) * (length - len(current_parsed))
    padded_latest = latest_parsed + (0,) * (length - len(latest_parsed))
    return padded_latest > padded_current
