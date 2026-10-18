"""What the accelerators on this host are doing, measured from inside the container.

Three counters are readable without a privileged container, an external tool or a
vendor library, and each measures something different. The panel must say which,
because "GPU 4%" and "NPU 4%" answer different questions:

* **NPU** (Intel VPU): ``/sys/class/accel/accel*/device/npu_busy_time_us`` is a
  device wide busy counter. Whatever is using the NPU, this sees it.
* **GPU** (any driver implementing the DRM fdinfo spec: i915, xe, amdgpu): engine
  time is published per client under ``/proc/<pid>/fdinfo/*``, so only the work
  *this app's own processes* submitted can be measured. Another container's use of
  the same GPU is invisible here and is never guessed at.
* **NVIDIA**: the proprietary driver publishes neither, so a present NVIDIA GPU is
  named and reported as unreadable rather than left out, which would look like a
  bug in the panel.

Everything is best effort and returns ``None`` rather than raising or inventing a
number: an unknown is reported as unknown (CLAUDE.md section 5).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Literal

import structlog

log = structlog.get_logger()

ACCEL_ROOT = Path("/sys/class/accel")
DRM_ROOT = Path("/sys/class/drm")
NVIDIA_GPU_ROOT = Path("/proc/driver/nvidia/gpus")
PROC_ROOT = Path("/proc")

AcceleratorKind = Literal["npu", "gpu"]
# "device" is every user of the accelerator; "app" is only the work this app submitted.
AcceleratorScope = Literal["device", "app"]

_DRIVER_LABELS = {
    "i915": "Intel GPU",
    "xe": "Intel GPU",
    "amdgpu": "AMD GPU",
    "radeon": "AMD GPU",
    "nouveau": "NVIDIA GPU",
    "v3d": "GPU",
    "vc4": "GPU",
}


@dataclass(frozen=True)
class AcceleratorReading:
    """One accelerator at one sample.

    ``utilization_percent`` is ``None`` when the counter exists but cannot be read
    yet (the first sample has nothing to diff against) or cannot be read at all, in
    which case ``unreadable`` says why in words the owner can act on.
    """

    id: str
    kind: AcceleratorKind
    label: str
    scope: AcceleratorScope
    utilization_percent: float | None
    unreadable: str | None = None


def _percent(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 1)


class NpuBusyTimeProbe:
    """Intel NPU busy time, device wide.

    Every ``accel*`` node is scanned rather than only ``accel0``: which number a
    device is given depends on probe order, and a host with a discrete accelerator
    as well can present the NPU as ``accel1``.
    """

    def __init__(self, *, accel_root: Path | str = ACCEL_ROOT) -> None:
        self._accel_root = Path(accel_root)
        self._previous: dict[str, tuple[int, float]] = {}

    def _busy_time_paths(self) -> list[tuple[str, Path]]:
        try:
            entries = sorted(self._accel_root.iterdir())
        except OSError:
            return []
        found: list[tuple[str, Path]] = []
        for entry in entries:
            busy = entry / "device" / "npu_busy_time_us"
            if busy.is_file():
                found.append((entry.name, busy))
        return found

    def read(self, now: float) -> list[AcceleratorReading]:
        readings: list[AcceleratorReading] = []
        seen: dict[str, tuple[int, float]] = {}
        for name, path in self._busy_time_paths():
            try:
                busy_us = int(path.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                continue
            seen[name] = (busy_us, now)
            previous = self._previous.get(name)
            utilization: float | None = None
            if previous is not None:
                busy_delta = busy_us - previous[0]
                elapsed = now - previous[1]
                if busy_delta >= 0 and elapsed > 0:
                    utilization = _percent(busy_delta / (elapsed * 1_000_000.0) * 100.0)
            readings.append(
                AcceleratorReading(
                    id=name,
                    kind="npu",
                    label="NPU",
                    scope="device",
                    utilization_percent=utilization,
                )
            )
        self._previous = seen
        return readings


@dataclass(frozen=True)
class _DrmClient:
    """One open DRM client: its card, and each engine class's cumulative work.

    Drivers report that work in one of two units. i915 publishes engine
    nanoseconds (``drm-engine-*``); xe publishes busy cycles against the
    engine's total cycles (``drm-cycles-*`` / ``drm-total-cycles-*``). The two
    are not interchangeable: cycles only mean something as a fraction of
    their own total.
    """

    pdev: str
    driver: str
    client_id: str
    engine_ns: dict[str, int]
    engine_capacity: dict[str, int]
    engine_cycles: dict[str, int]
    engine_total_cycles: dict[str, int]


class DrmEngineTimeProbe:
    """GPU engine time this app's processes have used, from the DRM fdinfo spec.

    A container can see its own processes and nothing else, so this measures the
    app's share of the GPU and never the whole device. The reading is the busiest
    engine class rather than the sum of all of them: render and video decode run
    concurrently on separate engines, so adding them would report more than a
    hundred percent of a GPU that is half idle.
    """

    def __init__(self, *, proc_root: Path | str = PROC_ROOT, drm_root: Path | str = DRM_ROOT) -> None:
        self._proc_root = Path(proc_root)
        self._drm_root = Path(drm_root)
        # Baselines are per (card, client), never summed across clients first:
        # a joining client's lifetime total is not this interval's work, and a
        # departing client's total must not subtract from the rest.
        self._previous: dict[tuple[str, str], tuple[_DrmClient, float]] = {}

    @staticmethod
    def _parse_fdinfo(raw: str) -> _DrmClient | None:
        driver = ""
        pdev = ""
        client_id = ""
        engine_ns: dict[str, int] = {}
        engine_capacity: dict[str, int] = {}
        engine_cycles: dict[str, int] = {}
        engine_total_cycles: dict[str, int] = {}
        for line in raw.splitlines():
            key, separator, value = line.partition(":")
            if not separator or not key.startswith("drm-"):
                continue
            value = value.strip()
            if key == "drm-driver":
                driver = value
            elif key == "drm-pdev":
                pdev = value
            elif key == "drm-client-id":
                client_id = value
            elif key.startswith("drm-engine-capacity-"):
                try:
                    engine_capacity[key[len("drm-engine-capacity-") :]] = max(1, int(value))
                except ValueError:
                    continue
            elif key.startswith("drm-total-cycles-"):
                try:
                    engine_total_cycles[key[len("drm-total-cycles-") :]] = int(value.split()[0])
                except (ValueError, IndexError):
                    continue
            elif key.startswith("drm-cycles-"):
                try:
                    engine_cycles[key[len("drm-cycles-") :]] = int(value.split()[0])
                except (ValueError, IndexError):
                    continue
            elif key.startswith("drm-engine-"):
                # "12345 ns". The unit is always nanoseconds in the spec, but it is
                # written out, so take the number and ignore the rest.
                try:
                    engine_ns[key[len("drm-engine-") :]] = int(value.split()[0])
                except (ValueError, IndexError):
                    continue
        if not driver or not (engine_ns or engine_cycles):
            return None
        return _DrmClient(
            pdev=pdev or driver,
            driver=driver,
            client_id=client_id,
            engine_ns=engine_ns,
            engine_capacity=engine_capacity,
            engine_cycles=engine_cycles,
            engine_total_cycles=engine_total_cycles,
        )

    def _clients(self, pids: Iterable[int]) -> list[_DrmClient]:
        # A client id can appear on several file descriptors once a process dups the
        # DRM fd, and the counters on each are the same cumulative totals. Keying on
        # (card, client id) counts that work once.
        unique: dict[tuple[str, str], _DrmClient] = {}
        for pid in pids:
            try:
                entries = list((self._proc_root / str(pid) / "fdinfo").iterdir())
            except OSError:
                continue
            for entry in entries:
                try:
                    raw = entry.read_text(encoding="utf-8")
                except OSError:
                    continue
                if "drm-driver" not in raw:
                    continue
                client = self._parse_fdinfo(raw)
                if client is None:
                    continue
                unique[(client.pdev, client.client_id)] = client
        return list(unique.values())

    def _label_for(self, driver: str, pdev: str, cards: int) -> str:
        label = _DRIVER_LABELS.get(driver, "GPU")
        # One GPU needs no address to identify it; several do.
        return f"{label} {pdev}" if cards > 1 and pdev else label

    def _engine_percents(self, clients: list[_DrmClient], now: float) -> dict[str, float]:
        """This interval's busy percent per engine class, from per-client deltas.

        Nanosecond engines sum each client's own share of its elapsed wall
        time. Cycle engines sum busy-cycle deltas over the largest
        total-cycle delta: clients on one card share the same engine clock,
        so summing their totals would count the same denominator twice. A
        client with no baseline, a rolled-back counter, or a total that did
        not advance contributes nothing rather than an invented number.
        Nanoseconds win when an engine reports both units."""
        capacity: dict[str, int] = {}
        for client in clients:
            for engine, slots in client.engine_capacity.items():
                capacity[engine] = max(capacity.get(engine, 1), slots)

        ns_percent: dict[str, float] = {}
        cycle_busy: dict[str, int] = {}
        cycle_total: dict[str, int] = {}
        for client in clients:
            previous = self._previous.get((client.pdev, client.client_id))
            if previous is None:
                continue
            before, before_at = previous
            elapsed = now - before_at
            for engine, nanoseconds in client.engine_ns.items():
                if engine not in before.engine_ns or elapsed <= 0:
                    continue
                delta = nanoseconds - before.engine_ns[engine]
                if delta < 0:
                    continue
                slots = capacity.get(engine, 1)
                ns_percent[engine] = ns_percent.get(engine, 0.0) + delta / (elapsed * 1_000_000_000.0 * slots) * 100.0
            for engine, cycles in client.engine_cycles.items():
                if engine not in before.engine_cycles or engine not in before.engine_total_cycles:
                    continue
                if engine not in client.engine_total_cycles:
                    continue
                busy_delta = cycles - before.engine_cycles[engine]
                total_delta = client.engine_total_cycles[engine] - before.engine_total_cycles[engine]
                if busy_delta < 0 or total_delta <= 0:
                    continue
                cycle_busy[engine] = cycle_busy.get(engine, 0) + busy_delta
                cycle_total[engine] = max(cycle_total.get(engine, 0), total_delta)

        percents = dict(ns_percent)
        for engine, busy in cycle_busy.items():
            if engine in percents:
                continue
            percents[engine] = busy / (cycle_total[engine] * capacity.get(engine, 1)) * 100.0
        return percents

    def read(self, now: float, pids: Iterable[int]) -> list[AcceleratorReading]:
        pid_list = list(pids)
        if not pid_list:
            # No processes to attribute means nothing was measured, which is not the
            # same as "the GPU went idle". Keep the last counters so the next read
            # with a real process list still has something to diff against.
            return []
        clients = self._clients(pid_list)
        by_card: dict[str, list[_DrmClient]] = {}
        for client in clients:
            by_card.setdefault(client.pdev, []).append(client)

        readings: list[AcceleratorReading] = []
        for pdev, card_clients in sorted(by_card.items()):
            percents = self._engine_percents(card_clients, now)
            # A card whose clients all have baselines but no measurable delta
            # (for example a restarted nanosecond counter) reports the work
            # that was measured: none. A card with no baseline at all, or only
            # cycle totals that never advanced, stays unknown.
            had_ns_baseline = any(
                client.engine_ns and (client.pdev, client.client_id) in self._previous for client in card_clients
            )
            if percents:
                utilization: float | None = _percent(max(percents.values()))
            elif had_ns_baseline:
                utilization = 0.0
            else:
                utilization = None
            readings.append(
                AcceleratorReading(
                    id=f"gpu-{pdev}",
                    kind="gpu",
                    label=self._label_for(card_clients[0].driver, pdev, len(by_card)),
                    scope="app",
                    utilization_percent=utilization,
                )
            )
        self._previous = {(client.pdev, client.client_id): (client, now) for client in clients}
        return readings


class NvidiaPresenceProbe:
    """Name an NVIDIA GPU that is present, and say its counter cannot be read.

    The proprietary driver publishes no busy time in sysfs and implements no DRM
    fdinfo engine counters, so utilization needs NVML. Reporting the card as
    unreadable is honest; leaving it out would read as a broken panel on the one
    host where the owner most expects a line.
    """

    def __init__(self, *, gpu_root: Path | str = NVIDIA_GPU_ROOT) -> None:
        self._gpu_root = Path(gpu_root)

    def read(self) -> list[AcceleratorReading]:
        try:
            entries = sorted(entry.name for entry in self._gpu_root.iterdir())
        except OSError:
            return []
        return [
            AcceleratorReading(
                id=f"nvidia-{name}",
                kind="gpu",
                label="NVIDIA GPU" if len(entries) == 1 else f"NVIDIA GPU {name}",
                scope="device",
                utilization_percent=None,
                unreadable="nvidia_no_counter",
            )
            for name in entries
        ]


class AcceleratorSampler:
    """Every accelerator this container can see, sampled together."""

    def __init__(
        self,
        *,
        npu_probe: NpuBusyTimeProbe | None = None,
        drm_probe: DrmEngineTimeProbe | None = None,
        nvidia_probe: NvidiaPresenceProbe | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._npu = npu_probe if npu_probe is not None else NpuBusyTimeProbe()
        self._drm = drm_probe if drm_probe is not None else DrmEngineTimeProbe()
        self._nvidia = nvidia_probe if nvidia_probe is not None else NvidiaPresenceProbe()
        self._clock = clock

    def sample(self, pids: Iterable[int] = ()) -> list[AcceleratorReading]:
        now = self._clock()
        pid_list = list(pids)
        readings: list[AcceleratorReading] = []
        for probe in (lambda: self._npu.read(now), lambda: self._drm.read(now, pid_list), self._nvidia.read):
            try:
                readings.extend(probe())
            except Exception as exc:  # noqa: BLE001 - one unreadable device must not hide the others
                log.warning("Accelerator probe failed", error=str(exc))
        return readings
