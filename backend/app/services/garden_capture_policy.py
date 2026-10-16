"""Admission for owner-reviewed animal captures, independent of bird roles."""

from datetime import datetime, timedelta, timezone
import math
import re


ANIMAL_LABELS = frozenset(
    {
        "animal",
        "cat",
        "dog",
        "horse",
        "sheep",
        "cow",
        "bear",
        "zebra",
        "giraffe",
        "fox",
        "squirrel",
        "hedgehog",
        "badger",
        "deer",
        "rabbit",
        "raccoon",
        "skunk",
        "opossum",
        "otter",
        "boar",
        "mouse",
        "rat",
    }
)


def normalize_garden_labels(value: object) -> list[str]:
    if not isinstance(value, list) or not value or len(value) > 100:
        raise ValueError("Choose at least one supported animal label")
    labels = list(dict.fromkeys(str(label).strip().lower() for label in value))
    if any(label not in ANIMAL_LABELS for label in labels):
        raise ValueError(
            "Choose supported garden labels: "
            + ", ".join(sorted(ANIMAL_LABELS))
            + ". Birds, people and vehicles are excluded."
        )
    return labels


def normalize_garden_cameras(value: object) -> list[str]:
    if not isinstance(value, list) or len(value) > 100:
        raise ValueError("Garden cameras must be a list of at most 100 camera names")
    if any(not isinstance(camera, str) or not camera.strip() or len(camera) > 100 for camera in value):
        raise ValueError("Garden camera names must contain between 1 and 100 characters")
    return list(dict.fromkeys(camera.strip() for camera in value))


def safe_event_id(value: object) -> str | None:
    if value in (".", ".."):
        return None
    return value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", value) else None


def garden_collection_cameras() -> list[str]:
    """Cameras Garden may collect from: none while the beta feature is switched off."""
    from app.config import settings

    return list(settings.frigate.garden_cameras) if settings.system.beta_garden_animals else []


def should_handle_garden(data: object, cameras: list[str], labels: list[str], *, has_history: bool = False) -> bool:
    if not isinstance(data, dict):
        return False
    after = data.get("after")
    if not isinstance(after, dict):
        return False
    label = str(after.get("label") or "").strip().lower()
    rejected = label in {"person", "human"} or bool(after.get("false_positive"))
    return (has_history and rejected) or (
        after.get("camera") in cameras and (label in labels or rejected or has_history)
    )


def observation_time(value: object, now: datetime, retention_days: int) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    try:
        observed = datetime.fromtimestamp(value, timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
    if observed > now + timedelta(minutes=5):
        return None
    if retention_days > 0 and observed < now - timedelta(days=retention_days):
        return None
    return observed.replace(tzinfo=None).isoformat()
