import math
from datetime import datetime, timezone


# The owner chooses the gap under Settings (`settings.visits.gap_seconds`); these bound it.
# Below five seconds a bird that hops off the perch and back would become two visits.
DEFAULT_VISIT_GAP_SECONDS = 60
MIN_VISIT_GAP_SECONDS = 5
MAX_VISIT_GAP_SECONDS = 300
MAX_EVENT_DURATION_SECONDS = 86400


def valid_event_bounds(start: object, end: object) -> tuple[datetime, datetime] | None:
    if isinstance(start, bool) or isinstance(end, bool):
        return None
    if not isinstance(start, (float, int)) or not isinstance(end, (float, int)):
        return None
    if start < 0 or start > 253402300799 or end < 0 or end > 253402300799:
        return None
    if not math.isfinite(start) or not math.isfinite(end):
        return None
    if start < 0 or not 0 <= end - start <= MAX_EVENT_DURATION_SECONDS:
        return None
    try:
        return tuple(datetime.fromtimestamp(value, timezone.utc).replace(tzinfo=None) for value in (start, end))
    except (OverflowError, OSError, ValueError):
        return None
