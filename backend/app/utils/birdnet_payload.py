"""Read identity and source out of a BirdNET-Go detection payload.

Pure parsing shared by audio ingest and audio history, so the repository and
the audio service agree on which keys identify a detection and its microphone
without importing each other.
"""

import json
import re


def extract_birdnet_id(raw_data: dict | None) -> int | None:
    """Pull a stable BirdNET-Go detection id out of an MQTT payload.

    Modern BirdNET-Go publishes ``detectionId`` as an integer; older builds
    sometimes used ``id`` or string-typed ``detection_id``. We accept any of
    those and reject anything non-numeric.
    """
    if not isinstance(raw_data, dict):
        return None
    for key in ("detectionId", "detection_id", "id"):
        value = raw_data.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int) and value > 0:
            return value
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.isdigit():
                return int(stripped)
    return None


def normalize_mapping_key(value: str | None) -> str:
    if not value:
        return ""
    return str(value).strip().casefold()


def parse_mapping_filter_values(mapping_value: str | None) -> tuple[bool, set[str]]:
    """A camera's microphone mapping as (matches every source, the source keys it names)."""
    if not isinstance(mapping_value, str):
        return False, set()
    tokens = {normalize_mapping_key(token) for token in re.split(r"[,\n;|]+", mapping_value)}
    tokens.discard("")
    if "*" in tokens:
        return True, set()
    return False, tokens


def extract_audio_mapping_keys(sensor_id: str | None, raw_data: str | None) -> set[str]:
    """Every name or id a stored detection's microphone could be mapped by."""
    keys: set[str] = set()
    normalized_sensor = normalize_mapping_key(sensor_id)
    if normalized_sensor:
        keys.add(normalized_sensor)

    if not raw_data:
        return keys

    try:
        payload = json.loads(raw_data)
    except Exception:
        return keys

    if not isinstance(payload, dict):
        return keys

    source = payload.get("Source")
    source = source if isinstance(source, dict) else {}
    for candidate in (
        payload.get("nm"),
        payload.get("sourceName"),
        source.get("displayName"),
        payload.get("src"),
        payload.get("sourceId"),
        source.get("id"),
        payload.get("id"),
        payload.get("sensor_id"),
    ):
        normalized = normalize_mapping_key(candidate)
        if normalized:
            keys.add(normalized)
    return keys


def extract_birdnet_source_name(sensor_id: str | None, raw_data: str | None) -> str | None:
    """Return the best human-readable BirdNET source label for history views."""
    if raw_data:
        try:
            payload = json.loads(raw_data)
        except Exception:
            payload = None
        if isinstance(payload, dict):
            source = payload.get("Source")
            source = source if isinstance(source, dict) else {}
            for candidate in (
                payload.get("nm"),
                payload.get("sourceName"),
                source.get("displayName"),
                sensor_id,
                payload.get("sourceId"),
                payload.get("src"),
                source.get("id"),
            ):
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip()

    if isinstance(sensor_id, str) and sensor_id.strip():
        return sensor_id.strip()
    return None
