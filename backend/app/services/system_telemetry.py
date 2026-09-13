import asyncio
import os
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Callable, Iterable, Literal

import structlog

log = structlog.get_logger()


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


ProcessRole = Literal["main", "live_worker", "background_worker", "video_worker", "ffmpeg", "other_child"]


@dataclass(frozen=True)
class ProcessLoad:
    """One process this container started, and what it cost at the last sample."""

    pid: int
    role: ProcessRole
    label: str
    detail: str | None
    cpu_percent: float | None
    rss_bytes: int | None


class ProcessLoadSampler:
    """
    Attribute CPU and memory to this process and its descendants, read straight from
    ``/proc``. The share of the host each one takes is its CPU time over the sample
    interval divided by the number of CPUs, so the app's processes and the host figure
    from :class:`SystemTelemetrySampler` are on the same scale.

    Only this container's own process tree is named. Everything else on the host is the
    remainder and is never identified; the container cannot see other containers and this
    does not try to.
    """

    def __init__(
        self,
        *,
        proc_root: Path | str = Path("/proc"),
        pid: int | None = None,
        cpu_count: int | None = None,
        clock_ticks_per_second: int | None = None,
        page_size: int | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._proc_root = Path(proc_root)
        self._pid = pid if pid is not None else os.getpid()
        self._cpu_count = max(1, cpu_count if cpu_count is not None else (os.cpu_count() or 1))
        self._clock_ticks = clock_ticks_per_second or int(os.sysconf("SC_CLK_TCK"))
        self._page_size = page_size or int(os.sysconf("SC_PAGE_SIZE"))
        self._clock = clock
        self._previous: dict[int, tuple[int, float]] = {}
        self._lock = Lock()

    def _read_stat(self, pid: int) -> tuple[int, int, str] | None:
        """Return (ppid, cpu ticks, comm) for a pid, or None when it is gone."""
        try:
            raw = (self._proc_root / str(pid) / "stat").read_text(encoding="utf-8")
        except OSError:
            return None
        # The comm field is parenthesised and may itself contain spaces.
        open_paren = raw.find("(")
        close_paren = raw.rfind(")")
        if open_paren == -1 or close_paren == -1:
            return None
        comm = raw[open_paren + 1 : close_paren]
        rest = raw[close_paren + 2 :].split()
        try:
            ppid = int(rest[1])
            ticks = int(rest[11]) + int(rest[12])
        except (IndexError, ValueError):
            return None
        return ppid, ticks, comm

    def _read_rss(self, pid: int) -> int | None:
        try:
            fields = (self._proc_root / str(pid) / "statm").read_text(encoding="utf-8").split()
            return int(fields[1]) * self._page_size
        except (OSError, ValueError, IndexError):
            return None

    def _read_cmdline(self, pid: int) -> list[str]:
        try:
            raw = (self._proc_root / str(pid) / "cmdline").read_bytes()
        except OSError:
            return []
        return [part.decode("utf-8", errors="replace") for part in raw.split(b"\0") if part]

    def _descendants(self) -> list[int]:
        children: dict[int, list[int]] = {}
        try:
            entries = list(self._proc_root.iterdir())
        except OSError:
            # No procfs (a developer's laptop): there is nothing to attribute, and that is
            # not an error worth logging five hundred times an hour.
            return []
        for entry in entries:
            if not entry.name.isdigit():
                continue
            pid = int(entry.name)
            stat = self._read_stat(pid)
            if stat is None:
                continue
            children.setdefault(stat[0], []).append(pid)
        ordered: list[int] = []
        queue = [self._pid]
        while queue:
            current = queue.pop(0)
            ordered.append(current)
            queue.extend(sorted(children.get(current, [])))
        return ordered

    def _identify(self, pid: int, comm: str) -> tuple[ProcessRole, str, str | None]:
        if pid == self._pid:
            return "main", "YA-WAMF", None
        cmdline = self._read_cmdline(pid)
        if "app.services.classifier_worker_process" in cmdline:
            index = cmdline.index("app.services.classifier_worker_process")
            worker_name = cmdline[index + 1] if index + 1 < len(cmdline) else ""
            pool = worker_name.split("-", 1)[0]
            role: ProcessRole = (
                "live_worker"
                if pool == "live"
                else "background_worker"
                if pool == "background"
                else "video_worker"
                if pool == "video"
                else "other_child"
            )
            return role, worker_name or comm, None
        if comm == "ffmpeg":
            return "ffmpeg", "ffmpeg", None
        return "other_child", comm, None

    def sample(self) -> list[ProcessLoad]:
        with self._lock:
            now = self._clock()
            seen: dict[int, tuple[int, float]] = {}
            loads: list[ProcessLoad] = []
            for pid in self._descendants():
                stat = self._read_stat(pid)
                if stat is None:
                    continue
                _ppid, ticks, comm = stat
                seen[pid] = (ticks, now)
                cpu_percent: float | None = None
                previous = self._previous.get(pid)
                if previous is not None:
                    tick_delta = ticks - previous[0]
                    elapsed = now - previous[1]
                    if tick_delta >= 0 and elapsed > 0:
                        seconds_of_cpu = tick_delta / self._clock_ticks
                        cpu_percent = round(min(100.0, seconds_of_cpu / elapsed / self._cpu_count * 100.0), 1)
                role, label, detail = self._identify(pid, comm)
                loads.append(
                    ProcessLoad(
                        pid=pid,
                        role=role,
                        label=label,
                        detail=detail,
                        cpu_percent=cpu_percent,
                        rss_bytes=self._read_rss(pid),
                    )
                )
            self._previous = seen
            return loads


@dataclass(frozen=True)
class SystemHistoryPoint:
    """One 5-second sample: the host, this app's share of it, and the rest."""

    at: float
    cpu_percent: float | None
    accelerator_percent: float | None
    app_cpu_percent: float | None
    other_cpu_percent: float | None


@dataclass(frozen=True)
class SystemHistorySnapshot:
    window_seconds: int
    interval_seconds: float
    accelerator_kind: str | None
    accelerator_label: str | None
    points: list[SystemHistoryPoint]
    processes: list[ProcessLoad]


class SystemTelemetryHistory:
    """A rolling window of samples, kept in memory so the graph is full when it opens."""

    def __init__(self, *, window_seconds: int = 1800, interval_seconds: float = 5.0) -> None:
        self.window_seconds = int(window_seconds)
        self.interval_seconds = float(interval_seconds)
        self._points: deque[SystemHistoryPoint] = deque(maxlen=max(1, int(window_seconds / interval_seconds)))
        self._processes: list[ProcessLoad] = []
        self._accelerator: tuple[str | None, str | None] = (None, None)
        self._lock = Lock()

    def record(self, sample: SystemTelemetrySample, processes: Iterable[ProcessLoad], *, at: float) -> None:
        process_list = list(processes)
        measured = [load.cpu_percent for load in process_list if load.cpu_percent is not None]
        app_cpu = round(sum(measured), 1) if measured else None
        other_cpu = None
        if sample.cpu_percent is not None and app_cpu is not None:
            other_cpu = round(max(0.0, sample.cpu_percent - app_cpu), 1)
        with self._lock:
            self._points.append(
                SystemHistoryPoint(
                    at=at,
                    cpu_percent=sample.cpu_percent,
                    accelerator_percent=sample.accelerator_percent,
                    app_cpu_percent=app_cpu,
                    other_cpu_percent=other_cpu,
                )
            )
            self._processes = process_list
            self._accelerator = (sample.accelerator_kind, sample.accelerator_label)

    def snapshot(self) -> SystemHistorySnapshot:
        with self._lock:
            return SystemHistorySnapshot(
                window_seconds=self.window_seconds,
                interval_seconds=self.interval_seconds,
                accelerator_kind=self._accelerator[0],
                accelerator_label=self._accelerator[1],
                points=list(self._points),
                processes=list(self._processes),
            )


class SystemTelemetryHistoryService:
    """Samples the host and this app's processes every few seconds while the app runs."""

    def __init__(
        self,
        *,
        history: SystemTelemetryHistory,
        sampler: SystemTelemetrySampler,
        process_sampler: ProcessLoadSampler,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        self._history = history
        self._sampler = sampler
        self._process_sampler = process_sampler
        self._wall_clock = wall_clock
        self._task: asyncio.Task[None] | None = None
        self._running = False

    async def sample_once(self) -> None:
        # /proc reads are small but they are file I/O; keep them off the event loop.
        sample, processes = await asyncio.to_thread(self._sample_sync)
        self._history.record(sample, processes, at=self._wall_clock())

    def _sample_sync(self) -> tuple[SystemTelemetrySample, list[ProcessLoad]]:
        return self._sampler.sample(), self._process_sampler.sample()

    async def _loop(self) -> None:
        while self._running:
            try:
                await self.sample_once()
            except Exception as exc:  # noqa: BLE001 - a bad sample must not stop the next one
                log.warning("System telemetry sample failed", error=str(exc))
            await asyncio.sleep(self._history.interval_seconds)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="system_telemetry_history")

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None


system_telemetry_history = SystemTelemetryHistory()
process_load_sampler = ProcessLoadSampler()
system_telemetry_history_service = SystemTelemetryHistoryService(
    history=system_telemetry_history,
    sampler=system_telemetry_sampler,
    process_sampler=process_load_sampler,
)
