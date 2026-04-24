from __future__ import annotations

import statistics
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Literal, NamedTuple


Outcome = Literal["ok", "timeout", "lease_expired", "exception"]
Verdict = Literal["healthy", "degraded", "unhealthy"]


class RuntimeKey(NamedTuple):
    backend: str
    provider: str
    model_id: str

    @classmethod
    def from_values(
        cls,
        backend: str | None,
        provider: str | None,
        model_id: str | None,
    ) -> "RuntimeKey":
        return cls(
            str(backend or "unknown"),
            str(provider or "unknown"),
            str(model_id or "unknown"),
        )

    def display(self) -> str:
        return "/".join(self)


@dataclass
class _RuntimeHealth:
    outcomes: deque[Outcome]
    latencies: deque[float]
    baseline_p95_latency_seconds: float | None = None
    first_recorded_at: float | None = None
    last_recorded_at: float | None = None
    last_outcome: Outcome | None = None
    cooldown_until_monotonic: float = 0.0
    last_verdict: Verdict = "healthy"


@dataclass(frozen=True)
class _HealthConfig:
    window_size: int = 32
    min_samples: int = 8
    degraded_error_rate: float = 0.2
    unhealthy_error_rate: float = 0.5
    degraded_latency_multiplier: float = 2.0
    unhealthy_latency_multiplier: float = 5.0
    cooldown_seconds: float = 600.0


class InferenceHealth:
    """Additive runtime health telemetry for classifier inference paths."""

    def __init__(
        self,
        *,
        window_size: int = 32,
        min_samples: int = 8,
        degraded_error_rate: float = 0.2,
        unhealthy_error_rate: float = 0.5,
        degraded_latency_multiplier: float = 2.0,
        unhealthy_latency_multiplier: float = 5.0,
        cooldown_seconds: float = 600.0,
    ) -> None:
        self._config = _HealthConfig(
            window_size=max(1, int(window_size)),
            min_samples=max(1, int(min_samples)),
            degraded_error_rate=max(0.0, float(degraded_error_rate)),
            unhealthy_error_rate=max(0.0, float(unhealthy_error_rate)),
            degraded_latency_multiplier=max(1.0, float(degraded_latency_multiplier)),
            unhealthy_latency_multiplier=max(1.0, float(unhealthy_latency_multiplier)),
            cooldown_seconds=max(0.0, float(cooldown_seconds)),
        )
        self._runtimes: dict[RuntimeKey, _RuntimeHealth] = {}
        self._lock = threading.RLock()

    def set_baseline(self, key: RuntimeKey, *, p95_latency_seconds: float | None) -> None:
        with self._lock:
            state = self._state_for(key)
            if isinstance(p95_latency_seconds, (int, float)) and p95_latency_seconds > 0:
                state.baseline_p95_latency_seconds = float(p95_latency_seconds)

    def record(
        self,
        key: RuntimeKey,
        *,
        outcome: Outcome,
        latency_seconds: float | None,
    ) -> None:
        now_wall = time.time()
        with self._lock:
            state = self._state_for(key)
            if state.first_recorded_at is None:
                state.first_recorded_at = now_wall
            state.last_recorded_at = now_wall
            state.last_outcome = outcome
            state.outcomes.append(outcome)
            if isinstance(latency_seconds, (int, float)) and latency_seconds >= 0:
                state.latencies.append(float(latency_seconds))

            verdict = self._compute_verdict(state)
            if verdict == "unhealthy" and state.last_verdict != "unhealthy":
                state.cooldown_until_monotonic = time.monotonic() + self._config.cooldown_seconds
            state.last_verdict = verdict

    def verdict(self, key: RuntimeKey) -> Verdict:
        with self._lock:
            state = self._runtimes.get(key)
            if state is None:
                return "healthy"
            return self._compute_verdict(state)

    def cooldown_remaining(self, key: RuntimeKey) -> float:
        with self._lock:
            state = self._runtimes.get(key)
            if state is None:
                return 0.0
            return max(0.0, state.cooldown_until_monotonic - time.monotonic())

    def snapshot(self) -> dict:
        with self._lock:
            runtimes = {
                key.display(): self._snapshot_runtime(state)
                for key, state in sorted(self._runtimes.items(), key=lambda item: item[0].display())
            }
            status = "ok"
            if any(runtime["verdict"] == "unhealthy" for runtime in runtimes.values()):
                status = "unhealthy"
            elif any(runtime["verdict"] == "degraded" for runtime in runtimes.values()):
                status = "degraded"
            return {
                "status": status,
                "runtimes": runtimes,
            }

    def _state_for(self, key: RuntimeKey) -> _RuntimeHealth:
        state = self._runtimes.get(key)
        if state is None:
            state = _RuntimeHealth(
                outcomes=deque(maxlen=self._config.window_size),
                latencies=deque(maxlen=self._config.window_size),
            )
            self._runtimes[key] = state
        return state

    def _compute_verdict(self, state: _RuntimeHealth) -> Verdict:
        if len(state.outcomes) < self._config.min_samples:
            return "healthy"

        error_rate = self._error_rate(state)
        if error_rate >= self._config.unhealthy_error_rate:
            return "unhealthy"
        if state.baseline_p95_latency_seconds and self._p95(state.latencies) is not None:
            p95 = self._p95(state.latencies) or 0.0
            if p95 >= state.baseline_p95_latency_seconds * self._config.unhealthy_latency_multiplier:
                return "unhealthy"
            if p95 >= state.baseline_p95_latency_seconds * self._config.degraded_latency_multiplier:
                return "degraded"
        if error_rate >= self._config.degraded_error_rate:
            return "degraded"
        return "healthy"

    def _snapshot_runtime(self, state: _RuntimeHealth) -> dict:
        latencies = list(state.latencies)
        return {
            "verdict": self._compute_verdict(state),
            "samples": len(state.outcomes),
            "recent_failures": sum(1 for outcome in state.outcomes if outcome != "ok"),
            "error_rate": round(self._error_rate(state), 4),
            "last_outcome": state.last_outcome,
            "first_recorded_at": state.first_recorded_at,
            "last_recorded_at": state.last_recorded_at,
            "baseline_p95_latency_seconds": state.baseline_p95_latency_seconds,
            "latency_seconds": {
                "p50": self._round_or_none(self._p50(latencies)),
                "p95": self._round_or_none(self._p95(latencies)),
                "max": self._round_or_none(max(latencies) if latencies else None),
            },
            "cooldown_remaining_seconds": self._round_or_none(
                max(0.0, state.cooldown_until_monotonic - time.monotonic())
            ),
        }

    @staticmethod
    def _error_rate(state: _RuntimeHealth) -> float:
        if not state.outcomes:
            return 0.0
        failures = sum(1 for outcome in state.outcomes if outcome != "ok")
        return failures / len(state.outcomes)

    @staticmethod
    def _p50(values: list[float] | deque[float]) -> float | None:
        if not values:
            return None
        return float(statistics.median(values))

    @staticmethod
    def _p95(values: list[float] | deque[float]) -> float | None:
        if not values:
            return None
        ordered = sorted(values)
        index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95 + 0.999999) - 1))
        return float(ordered[index])

    @staticmethod
    def _round_or_none(value: float | None) -> float | None:
        if value is None:
            return None
        return round(float(value), 6)
