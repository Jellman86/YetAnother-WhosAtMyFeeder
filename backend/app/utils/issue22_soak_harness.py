from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


_PRESSURE_RANK = {
    "normal": 0,
    "elevated": 1,
    "high": 2,
    "critical": 3,
}


@dataclass(frozen=True)
class SoakSample:
    observed_at: datetime
    health_status: str
    mqtt_pressure_level: str
    mqtt_topic_liveness_reconnects: int
    mqtt_frigate_count: int | None
    mqtt_birdnet_count: int | None
    mqtt_frigate_age_seconds: float | None
    mqtt_birdnet_age_seconds: float | None

    def to_json(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["observed_at"] = self.observed_at.astimezone(timezone.utc).isoformat()
        return payload


@dataclass(frozen=True)
class SoakThresholds:
    min_samples: int
    min_frigate_messages_delta: int
    min_birdnet_messages_delta: int
    max_degraded_ratio: float
    max_pressure_level: str
    frigate_stall_age_seconds: float
    max_birdnet_active_age_seconds: float
    min_stall_duration_seconds: float
    max_health_fetch_failures: int = 0


def sample_from_health_payload(payload: dict[str, Any], observed_at: datetime | None = None) -> SoakSample:
    now = observed_at or datetime.now(timezone.utc)
    mqtt = payload.get("mqtt") if isinstance(payload, dict) else {}
    mqtt = mqtt if isinstance(mqtt, dict) else {}
    topic_counts = mqtt.get("topic_message_counts")
    topic_counts = topic_counts if isinstance(topic_counts, dict) else {}
    topic_ages = mqtt.get("topic_last_message_age_seconds")
    topic_ages = topic_ages if isinstance(topic_ages, dict) else {}

    return SoakSample(
        observed_at=now,
        health_status=str(payload.get("status", "unknown")),
        mqtt_pressure_level=str(mqtt.get("pressure_level", "unknown")).lower(),
        mqtt_topic_liveness_reconnects=_safe_int(mqtt.get("topic_liveness_reconnects")),
        mqtt_frigate_count=_safe_int_or_none(topic_counts.get("frigate")),
        mqtt_birdnet_count=_safe_int_or_none(topic_counts.get("birdnet")),
        mqtt_frigate_age_seconds=_safe_float_or_none(topic_ages.get("frigate")),
        mqtt_birdnet_age_seconds=_safe_float_or_none(topic_ages.get("birdnet")),
    )


def evaluate_soak_run(samples: list[SoakSample], thresholds: SoakThresholds, health_fetch_failures: int = 0) -> dict[str, Any]:
    reasons: list[str] = []
    incidents = _detect_stall_incidents(samples, thresholds)

    degraded_count = sum(1 for sample in samples if sample.health_status != "ok")
    degraded_ratio = (degraded_count / len(samples)) if samples else 1.0

    pressure_levels = [sample.mqtt_pressure_level for sample in samples]
    max_pressure = _max_pressure_level(pressure_levels)

    frigate_delta = _count_delta(samples, lambda sample: sample.mqtt_frigate_count)
    birdnet_delta = _count_delta(samples, lambda sample: sample.mqtt_birdnet_count)
    reconnect_delta = _count_delta(samples, lambda sample: sample.mqtt_topic_liveness_reconnects)

    if len(samples) < thresholds.min_samples:
        reasons.append(
            f"Insufficient samples captured ({len(samples)} < {thresholds.min_samples})."
        )

    if health_fetch_failures > thresholds.max_health_fetch_failures:
        reasons.append(
            "Health fetch failures exceeded threshold "
            f"({health_fetch_failures} > {thresholds.max_health_fetch_failures})."
        )

    if frigate_delta is None:
        reasons.append("Unable to compute Frigate topic message delta from health payload.")
    elif frigate_delta < thresholds.min_frigate_messages_delta:
        reasons.append(
            "Frigate topic message growth below threshold "
            f"({frigate_delta} < {thresholds.min_frigate_messages_delta})."
        )

    if birdnet_delta is None:
        reasons.append("Unable to compute BirdNET topic message delta from health payload.")
    elif birdnet_delta < thresholds.min_birdnet_messages_delta:
        reasons.append(
            "BirdNET topic message growth below threshold "
            f"({birdnet_delta} < {thresholds.min_birdnet_messages_delta})."
        )

    if degraded_ratio > thresholds.max_degraded_ratio:
        reasons.append(
            "Degraded health ratio exceeded threshold "
            f"({degraded_ratio:.3f} > {thresholds.max_degraded_ratio:.3f})."
        )

    if _pressure_rank(max_pressure) > _pressure_rank(thresholds.max_pressure_level):
        reasons.append(
            "Pressure level exceeded limit "
            f"(max={max_pressure}, allowed={thresholds.max_pressure_level})."
        )

    if incidents:
        reasons.append(
            f"Frigate stream stalled while BirdNET remained active ({len(incidents)} incident(s))."
        )

    return {
        "passed": len(reasons) == 0,
        "failure_reasons": reasons,
        "sample_count": len(samples),
        "health_fetch_failures": health_fetch_failures,
        "degraded_count": degraded_count,
        "degraded_ratio": degraded_ratio,
        "max_pressure_level": max_pressure,
        "frigate_delta": frigate_delta,
        "birdnet_delta": birdnet_delta,
        "topic_liveness_reconnects_delta": reconnect_delta,
        "stall_incidents": incidents,
    }


def _detect_stall_incidents(samples: list[SoakSample], thresholds: SoakThresholds) -> list[dict[str, Any]]:
    incidents: list[dict[str, Any]] = []
    if len(samples) < 2:
        return incidents

    active_start: datetime | None = None
    last_seen: datetime | None = None
    max_frigate_age = 0.0

    for previous, current in zip(samples, samples[1:]):
        if _is_stall_transition(previous, current, thresholds):
            if active_start is None:
                active_start = previous.observed_at
                max_frigate_age = current.mqtt_frigate_age_seconds or 0.0
            else:
                max_frigate_age = max(max_frigate_age, current.mqtt_frigate_age_seconds or 0.0)
            last_seen = current.observed_at
            continue

        if active_start is not None and last_seen is not None:
            duration = max(0.0, (last_seen - active_start).total_seconds())
            if duration >= thresholds.min_stall_duration_seconds:
                incidents.append(
                    {
                        "start": active_start.astimezone(timezone.utc).isoformat(),
                        "end": last_seen.astimezone(timezone.utc).isoformat(),
                        "duration_seconds": round(duration, 1),
                        "max_frigate_age_seconds": round(max_frigate_age, 1),
                    }
                )
        active_start = None
        last_seen = None
        max_frigate_age = 0.0

    if active_start is not None and last_seen is not None:
        duration = max(0.0, (last_seen - active_start).total_seconds())
        if duration >= thresholds.min_stall_duration_seconds:
            incidents.append(
                {
                    "start": active_start.astimezone(timezone.utc).isoformat(),
                    "end": last_seen.astimezone(timezone.utc).isoformat(),
                    "duration_seconds": round(duration, 1),
                    "max_frigate_age_seconds": round(max_frigate_age, 1),
                }
            )

    return incidents


def _is_stall_transition(previous: SoakSample, current: SoakSample, thresholds: SoakThresholds) -> bool:
    if (
        previous.mqtt_frigate_count is None
        or previous.mqtt_birdnet_count is None
        or current.mqtt_frigate_count is None
        or current.mqtt_birdnet_count is None
    ):
        return False

    if current.mqtt_frigate_age_seconds is None or current.mqtt_birdnet_age_seconds is None:
        return False

    birdnet_progressed = current.mqtt_birdnet_count > previous.mqtt_birdnet_count
    frigate_progressed = current.mqtt_frigate_count > previous.mqtt_frigate_count
    birdnet_active = current.mqtt_birdnet_age_seconds <= thresholds.max_birdnet_active_age_seconds
    frigate_stale = current.mqtt_frigate_age_seconds >= thresholds.frigate_stall_age_seconds
    return birdnet_progressed and (not frigate_progressed) and birdnet_active and frigate_stale


def _count_delta(samples: list[SoakSample], getter) -> int | None:
    values: list[int] = []
    for sample in samples:
        value = getter(sample)
        if value is not None:
            values.append(value)
    if len(values) < 2:
        return None
    return values[-1] - values[0]


def _max_pressure_level(levels: list[str]) -> str:
    if not levels:
        return "unknown"
    return max(levels, key=_pressure_rank)


def _pressure_rank(level: str) -> int:
    return _PRESSURE_RANK.get(str(level).lower(), -1)


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
