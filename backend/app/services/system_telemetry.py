from dataclasses import dataclass
from pathlib import Path
from threading import Lock
import time
from typing import Callable


@dataclass(frozen=True)
class SystemTelemetrySample:
    cpu_percent: float | None
    accelerator_kind: str | None
    accelerator_label: str | None
    accelerator_percent: float | None


class SystemTelemetrySampler:
    """Sample host CPU and supported accelerator counters without external tools."""

    def __init__(
        self,
        *,
        proc_stat_path: Path | str = Path("/proc/stat"),
        npu_busy_path: Path | str = Path("/sys/class/accel/accel0/device/npu_busy_time_us"),
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._proc_stat_path = Path(proc_stat_path)
        self._npu_busy_path = Path(npu_busy_path)
        self._clock = clock
        self._previous_cpu: tuple[int, int] | None = None
        self._previous_npu: tuple[int, float] | None = None
        self._lock = Lock()

    @staticmethod
    def _percent(value: float) -> float:
        return round(max(0.0, min(100.0, value)), 1)

    def _read_cpu_counters(self) -> tuple[int, int] | None:
        try:
            fields = self._proc_stat_path.read_text(encoding="utf-8").splitlines()[0].split()
            if not fields or fields[0] != "cpu":
                return None
            counters = [int(value) for value in fields[1:]]
            total = sum(counters)
            idle = counters[3] + (counters[4] if len(counters) > 4 else 0)
            return total, idle
        except (OSError, ValueError, IndexError):
            return None

    def _sample_cpu(self) -> float | None:
        current = self._read_cpu_counters()
        previous = self._previous_cpu
        self._previous_cpu = current
        if current is None or previous is None:
            return None
        total_delta = current[0] - previous[0]
        idle_delta = current[1] - previous[1]
        if total_delta <= 0 or idle_delta < 0:
            return None
        return self._percent((total_delta - idle_delta) / total_delta * 100.0)

    def _read_npu_busy_time(self) -> int | None:
        try:
            return int(self._npu_busy_path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return None

    def _sample_npu(self, now: float) -> float | None:
        current_busy = self._read_npu_busy_time()
        previous = self._previous_npu
        self._previous_npu = (current_busy, now) if current_busy is not None else None
        if current_busy is None or previous is None:
            return None
        busy_delta = current_busy - previous[0]
        elapsed = now - previous[1]
        if busy_delta < 0 or elapsed <= 0:
            return None
        return self._percent(busy_delta / (elapsed * 1_000_000.0) * 100.0)

    def sample(self) -> SystemTelemetrySample:
        with self._lock:
            now = self._clock()
            cpu_percent = self._sample_cpu()
            has_npu = self._npu_busy_path.is_file()
            accelerator_percent = self._sample_npu(now) if has_npu else None
            return SystemTelemetrySample(
                cpu_percent=cpu_percent,
                accelerator_kind="npu" if has_npu else None,
                accelerator_label="NPU" if has_npu else None,
                accelerator_percent=accelerator_percent,
            )


system_telemetry_sampler = SystemTelemetrySampler()
