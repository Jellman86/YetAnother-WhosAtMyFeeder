"""Whether Frigate's API is answering, so event reads wait for it instead of failing one by one.

Frigate and this app restart together on every deploy. For the first seconds Frigate's web
server answers 500 to every request because its API behind it has not started. Asking it
about fifty events in that window used to produce fifty warnings about one condition.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

import structlog

from app.utils.tasks import create_background_task

log = structlog.get_logger()

# Seconds between readiness checks while Frigate is not answering; the last value repeats.
PROBE_BACKOFF_SECONDS: tuple[float, ...] = (1.0, 2.0, 4.0, 8.0, 15.0, 30.0)
# A burst of reads fails together; waiting this long lets one line carry the whole count.
SUMMARY_DELAY_SECONDS = 2.0
# How long background work waits for Frigate before leaving the read to its own retry path.
BACKGROUND_WAIT_SECONDS = 120.0

FRIGATE_NOT_READY = "frigate_not_ready"


class FrigateReadinessGate:
    """Tracks one measured fact: did Frigate's API answer the last readiness check.

    `None` means not measured yet, which never blocks a read: the read itself is the
    measurement. Only a failed check closes the gate, and only a passed one reopens it.
    """

    def __init__(
        self,
        probe: Callable[[], Awaitable[bool]],
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        summary_delay_seconds: float = SUMMARY_DELAY_SECONDS,
    ) -> None:
        self._probe = probe
        self._clock = clock
        self._sleep = sleep
        self._summary_delay_seconds = summary_delay_seconds
        self._probe_lock: asyncio.Lock | None = None
        self.reset()

    def reset(self) -> None:
        self._ready: bool | None = None
        self._last_probe_at: float | None = None
        self._failed_probes = 0
        self._deferred_reads = 0
        self._summary_task: asyncio.Task | None = None
        self._summary_logged = False
        self._probe_lock = None

    @property
    def ready(self) -> bool | None:
        return self._ready

    def _retry_interval(self) -> float:
        index = min(max(self._failed_probes - 1, 0), len(PROBE_BACKOFF_SECONDS) - 1)
        return PROBE_BACKOFF_SECONDS[index]

    def _probe_is_due(self) -> bool:
        if self._last_probe_at is None:
            return True
        return self._clock() - self._last_probe_at >= self._retry_interval()

    async def _check(self) -> None:
        """Run at most one readiness check per retry interval, however many reads ask."""
        if self._probe_lock is None:
            self._probe_lock = asyncio.Lock()
        async with self._probe_lock:
            if not self._probe_is_due():
                return
            try:
                answered = bool(await self._probe())
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - any failure to answer is the same measurement
                answered = False
            self._last_probe_at = self._clock()
            if answered:
                self._mark_ready()
            else:
                self._ready = False
                self._failed_probes += 1

    def _mark_ready(self) -> None:
        was_waiting = self._ready is False
        self._ready = True
        self._failed_probes = 0
        if was_waiting and self._deferred_reads:
            log.info("Frigate is ready; event reads resumed", deferred_reads=self._deferred_reads)
        self._deferred_reads = 0
        self._summary_logged = False

    def note_answered(self) -> None:
        """An event read got a real answer, which is as good as a passed check."""
        if self._ready is not True:
            self._mark_ready()

    async def admit(self) -> bool:
        """Whether a read may go to Frigate now. Never waits longer than one check."""
        if self._ready is not False:
            return True
        await self._check()
        return self._ready is not False

    async def failure_is_not_ready(self) -> bool:
        """After a read failed on Frigate's side: is Frigate as a whole not answering?

        True means the failure is the transient "starting or unreachable" condition. False
        means Frigate answers and this one read failed, which is a real fault to report.
        """
        await self._check()
        return self._ready is False

    def note_deferred(self) -> None:
        """Count a read put off because Frigate is not ready, and report the batch once."""
        self._deferred_reads += 1
        if self._summary_logged or self._summary_task is not None:
            return
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        self._summary_task = create_background_task(self._log_summary(), name="frigate_not_ready_summary")

    async def _log_summary(self) -> None:
        try:
            if self._summary_delay_seconds > 0:
                await self._sleep(self._summary_delay_seconds)
            if self._ready is False and self._deferred_reads:
                self._summary_logged = True
                log.info(
                    "Frigate not ready; retrying event reads",
                    deferred_reads=self._deferred_reads,
                    retry_in_seconds=self._retry_interval(),
                )
        finally:
            self._summary_task = None

    async def wait_until_ready(self, timeout_seconds: float = BACKGROUND_WAIT_SECONDS) -> bool:
        """Wait, with backoff, until Frigate answers a readiness check or the time runs out.

        Unlike `admit`, an unmeasured Frigate is checked first, so background work started
        alongside Frigate does not use its own read as the first probe.
        """
        deadline = self._clock() + max(0.0, timeout_seconds)
        while True:
            if self._ready is None or (self._ready is False and self._probe_is_due()):
                await self._check()
            if self._ready is True:
                return True
            remaining = deadline - self._clock()
            if remaining <= 0:
                return False
            await self._sleep(min(self._retry_interval(), remaining))
