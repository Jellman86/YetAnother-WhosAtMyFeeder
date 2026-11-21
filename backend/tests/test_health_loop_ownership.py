"""The health report reads state the event loop owns, so it must read it on the loop.

The services in the health report keep their counters, windows and maps on the
event loop and update them without locks. A read from a worker thread can be
interrupted by a loop write part-way through iterating one of those collections,
which is how `/health` answered 500 with "deque mutated during iteration" on a
busy feeder.

The interleaving here is forced rather than hoped for. A value planted in the
collection calls back into Python when the reader compares, hashes or reads it,
and at that moment, if the reader is a worker thread, the loop is asked to make
one ordinary write and the reader waits until it has. On the loop thread no write
can land mid-read, so the value does nothing there. Each test is therefore
deterministic in both directions: an off-loop read fails every time, an on-loop
read never does.
"""

import asyncio
import operator
import sys
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from collections.abc import Callable, Iterator
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
import pytest_asyncio

import app.database as database_module
from app.database import DatabasePool
from app.main import app
from app.services.auto_video_classifier_service import auto_video_classifier
from app.services.classifier_service import get_classifier
from app.services.high_quality_snapshot_service import high_quality_snapshot_service
from app.services.mqtt_service import mqtt_service

# Long enough for a loaded CI runner, short enough that a broken test cannot hang.
_INTERLEAVE_DEADLINE_SECONDS = 5.0

HEALTH_READERS = ["/health", "/api/diagnostics/workspace"]


class _Interleaving:
    """One point in a read where, reached from a worker thread, the loop writes once."""

    def __init__(self, write: Callable[[], None]) -> None:
        self.loop = asyncio.get_running_loop()
        self.loop_thread_id = threading.get_ident()
        self.write = write
        self.reader_threads: list[int] = []
        self._written = False

    def reached(self) -> None:
        reader = threading.get_ident()
        self.reader_threads.append(reader)
        if reader == self.loop_thread_id or self._written:
            return
        self._written = True
        written = threading.Event()

        def write_on_loop() -> None:
            try:
                self.write()
            finally:
                written.set()

        self.loop.call_soon_threadsafe(write_on_loop)
        assert written.wait(_INTERLEAVE_DEADLINE_SECONDS), "the event loop never ran the interleaved write"

    def assert_read_only_on_the_loop(self) -> None:
        assert self.reader_threads, "the read never reached the planted value, so this test proves nothing"
        assert set(self.reader_threads) == {self.loop_thread_id}, "loop-owned state was read off the event loop"


class _Reading(float):
    """A time or duration the reader compares or subtracts."""

    point: _Interleaving

    def __new__(cls, value: float, point: _Interleaving) -> "_Reading":
        reading = super().__new__(cls, value)
        reading.point = point
        return reading

    def _compared(self, other: object, compare: Callable[[float, float], bool]) -> bool:
        self.point.reached()
        return compare(float(self), float(other))  # type: ignore[arg-type]

    def __lt__(self, other: object) -> bool:
        return self._compared(other, operator.lt)

    def __gt__(self, other: object) -> bool:
        return self._compared(other, operator.gt)

    def __le__(self, other: object) -> bool:
        return self._compared(other, operator.le)

    def __ge__(self, other: object) -> bool:
        return self._compared(other, operator.ge)

    def __rsub__(self, other: object) -> float:
        self.point.reached()
        return float(other) - float(self)  # type: ignore[arg-type]

    __hash__ = float.__hash__


class _Label(str):
    """A name the reader hashes or compares, such as a topic or a priority."""

    point: _Interleaving

    def __new__(cls, value: str, point: _Interleaving) -> "_Label":
        label = super().__new__(cls, value)
        label.point = point
        return label

    def __hash__(self) -> int:
        self.point.reached()
        return str.__hash__(self)

    def __eq__(self, other: object) -> bool:
        self.point.reached()
        return str.__eq__(self, other)


class _Record(dict):
    """A metadata or state record the reader looks into or copies."""

    def __init__(self, data: dict[str, Any], point: _Interleaving) -> None:
        super().__init__(data)
        self.point = point

    def get(self, key: str, default: Any = None) -> Any:
        self.point.reached()
        return super().get(key, default)

    def keys(self) -> Any:
        self.point.reached()
        return super().keys()

    def __iter__(self) -> Iterator[str]:
        self.point.reached()
        return super().__iter__()


class _Task:
    """Stands in for an asyncio task the reader asks whether it is done."""

    def __init__(self, point: _Interleaving | None = None) -> None:
        self.point = point

    def done(self) -> bool:
        if self.point is not None:
            self.point.reached()
        return False

    def get_name(self) -> str:
        return "stand-in"


class _NestedReading:
    """A value inside a nested dict of the loop's state, met when that dict is deep-copied."""

    def __init__(self, point: _Interleaving) -> None:
        self.point = point

    def __deepcopy__(self, memo: dict[int, Any]) -> float:
        self.point.reached()
        return 1.0


class _ReleasedConnection:
    """Stands in for an aiosqlite connection: the pool keys holds on its identity only."""


@pytest_asyncio.fixture
async def client():
    # A 500 must come back as a response the test can assert on, not escape as the exception.
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture(autouse=True)
def no_startup_warnings() -> None:
    app.state.startup_warnings = []


@pytest.fixture
def pool(tmp_path, monkeypatch: pytest.MonkeyPatch) -> DatabasePool:
    """A pool the health report reads; it never opens a connection."""
    pool = DatabasePool(str(tmp_path / "health-race.db"), pool_size=2)
    monkeypatch.setattr(database_module, "_db_pool", pool)
    return pool


# --- The DB pool: the reported crash ----------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("path", HEALTH_READERS)
async def test_a_hold_released_while_health_reads_the_hold_window_never_fails_the_read(
    client: httpx.AsyncClient, pool: DatabasePool, path: str
):
    """The reported crash: a connection released mid-read, while the read walks `_hold_samples`."""
    point = _Interleaving(lambda: pool._record_hold_sample(_ReleasedConnection(), hold_ms=12.0))  # type: ignore[arg-type]
    now = time.monotonic()
    pool._hold_samples.extend([(now, _Reading(40.0, point)), (now, 25.0)])

    response = await client.get(path)

    assert response.status_code == 200, response.text
    point.assert_read_only_on_the_loop()


@pytest.mark.asyncio
@pytest.mark.parametrize("path", HEALTH_READERS)
async def test_an_acquire_wait_recorded_while_health_reads_the_wait_window_never_fails_the_read(
    client: httpx.AsyncClient, pool: DatabasePool, path: str
):
    point = _Interleaving(lambda: pool._record_wait_sample(12.0))
    now = time.monotonic()
    pool._wait_samples.extend([(now, _Reading(40.0, point)), (now, 25.0)])

    response = await client.get(path)

    assert response.status_code == 200, response.text
    point.assert_read_only_on_the_loop()


@pytest.mark.asyncio
@pytest.mark.parametrize("path", HEALTH_READERS)
async def test_a_connection_released_while_health_names_the_longest_holder_never_fails_the_read(
    client: httpx.AsyncClient, pool: DatabasePool, path: str
):
    """`_longest_active_hold` walks the checked-out map, which every release shrinks."""
    first, second = _ReleasedConnection(), _ReleasedConnection()
    point = _Interleaving(lambda: pool._record_hold_sample(second))  # type: ignore[arg-type]
    pool._checked_out[id(first)] = (_Reading(time.monotonic() - 1.0, point), "first_holder")
    pool._checked_out[id(second)] = (time.monotonic(), "second_holder")

    response = await client.get(path)

    assert response.status_code == 200, response.text
    point.assert_read_only_on_the_loop()


@pytest.mark.asyncio
async def test_health_answers_200_throughout_while_the_loop_hammers_the_pool(
    client: httpx.AsyncClient, pool: DatabasePool
):
    """A busy feeder, without a forced interleaving: every release records a hold while health is polled."""
    stop = asyncio.Event()
    connection = _ReleasedConnection()
    now = time.monotonic()
    pool._hold_samples.extend((now, float(i % 50)) for i in range(database_module.DB_POOL_WAIT_SAMPLE_CAP))
    pool._wait_samples.extend((now, float(i % 50)) for i in range(database_module.DB_POOL_WAIT_SAMPLE_CAP))

    async def release_connections_continuously() -> None:
        while not stop.is_set():
            for _ in range(200):
                pool._checked_out[id(connection)] = (time.monotonic(), "hammer")
                pool._record_hold_sample(connection)  # type: ignore[arg-type]
                pool._record_wait_sample(1.0)
            await asyncio.sleep(0)

    # Switch threads as often as the interpreter allows, so an off-loop read would meet the writer.
    switch_interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    hammer = asyncio.create_task(release_connections_continuously())
    try:
        statuses = [(await client.get("/health")).status_code for _ in range(40)]
    finally:
        stop.set()
        await hammer
        sys.setswitchinterval(switch_interval)

    assert statuses == [200] * 40


# --- The other loop-owned state the audit found read off the loop ------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("path", HEALTH_READERS)
async def test_an_mqtt_message_arriving_while_health_counts_in_flight_handlers_never_fails_the_read(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch, path: str
):
    """Every MQTT message adds a handler task to the set `get_status` walks."""

    def a_message_arrives() -> None:
        mqtt_service._track_handler_task(asyncio.get_running_loop().create_task(asyncio.sleep(0)), "frigate")

    point = _Interleaving(a_message_arrives)
    handler = _Task()
    monkeypatch.setattr(mqtt_service, "_in_flight_tasks", {handler})
    monkeypatch.setattr(mqtt_service, "_task_kind_by_id", {id(handler): _Label("frigate", point)})

    response = await client.get(path)

    assert response.status_code == 200, response.text
    point.assert_read_only_on_the_loop()


@pytest.mark.asyncio
@pytest.mark.parametrize("path", HEALTH_READERS)
async def test_a_classification_admitted_while_health_ages_the_running_work_never_fails_the_read(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch, path: str
):
    coordinator = get_classifier()._classification_admission

    def another_classification_is_admitted() -> None:
        coordinator._active["admitted-mid-read"] = SimpleNamespace(priority="live", admitted_at=time.monotonic())

    point = _Interleaving(another_classification_is_admitted)
    running = SimpleNamespace(priority=_Label("live", point), admitted_at=time.monotonic())
    monkeypatch.setattr(coordinator, "_active", {"running": running})

    response = await client.get(path)

    assert response.status_code == 200, response.text
    point.assert_read_only_on_the_loop()


@pytest.mark.asyncio
@pytest.mark.parametrize("path", HEALTH_READERS)
async def test_a_classification_queued_while_health_ages_the_queue_never_fails_the_read(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch, path: str
):
    coordinator = get_classifier()._classification_admission
    queued = deque[Any]()

    point = _Interleaving(lambda: queued.append(SimpleNamespace(enqueued_at=time.monotonic())))
    queued.extend([SimpleNamespace(enqueued_at=_Reading(time.monotonic(), point)), SimpleNamespace(enqueued_at=1.0)])
    monkeypatch.setitem(coordinator._pending, "background", queued)

    response = await client.get(path)

    assert response.status_code == 200, response.text
    point.assert_read_only_on_the_loop()


@pytest.mark.asyncio
async def test_native_cpu_recovery_changing_while_the_workspace_reads_it_never_fails_the_read(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    """The classifier status copies the recovery states, which a native crash rewrites on the loop."""
    recovery = get_classifier()._native_cpu_recovery
    point = _Interleaving(lambda: recovery._state("video", "recovering"))
    monkeypatch.setattr(recovery, "_states", {"live": _Record({"status": "degraded", "runtime": None}, point)})

    response = await client.get("/api/diagnostics/workspace")

    assert response.status_code == 200, response.text
    point.assert_read_only_on_the_loop()


@pytest.mark.asyncio
@pytest.mark.parametrize("path", HEALTH_READERS)
async def test_a_video_job_starting_while_health_sweeps_finished_jobs_never_fails_the_read(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch, path: str
):
    """`get_status` sweeps finished jobs out of `_active_tasks`, which every started job adds to."""
    jobs: dict[str, Any] = {}
    point = _Interleaving(lambda: jobs.__setitem__("evt-started-mid-read", _Task()))
    jobs.update({"evt-running": _Task(point), "evt-other": _Task()})
    monkeypatch.setattr(auto_video_classifier, "_active_tasks", jobs)

    response = await client.get(path)

    assert response.status_code == 200, response.text
    point.assert_read_only_on_the_loop()


@pytest.mark.asyncio
@pytest.mark.parametrize("path", HEALTH_READERS)
@pytest.mark.parametrize("queue", ["_pending_metadata", "_active_metadata"])
async def test_a_video_job_queued_while_health_counts_the_queue_never_fails_the_read(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch, path: str, queue: str
):
    jobs: dict[str, Any] = {}
    point = _Interleaving(lambda: jobs.__setitem__("evt-queued-mid-read", {"source": "live"}))
    jobs.update({"evt-1": _Record({"source": "live", "queued_at": time.monotonic()}, point), "evt-2": {}})
    monkeypatch.setattr(auto_video_classifier, queue, jobs)

    response = await client.get(path)

    assert response.status_code == 200, response.text
    point.assert_read_only_on_the_loop()


@pytest.mark.asyncio
@pytest.mark.parametrize("path", HEALTH_READERS)
async def test_health_sweeps_finished_photo_workers_only_on_the_loop(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch, path: str
):
    """The sweep replaces `_worker_tasks`. Off the loop it would drop a worker the loop started
    part-way through, and that worker would escape shutdown."""
    workers: list[Any] = []
    point = _Interleaving(lambda: workers.append(_Task()))
    workers.append(_Task(point))
    monkeypatch.setattr(high_quality_snapshot_service, "_worker_tasks", workers)

    response = await client.get(path)

    assert response.status_code == 200, response.text
    point.assert_read_only_on_the_loop()


@pytest.mark.asyncio
@pytest.mark.parametrize("path", HEALTH_READERS)
async def test_health_reads_loop_owned_state_on_the_loop_and_files_in_a_thread(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch, path: str
):
    """Every reader the audit names, by the thread it runs on.

    Some of these getters write as they read (the video sweep and circuit expiry, the
    photo-worker sweep), so off the loop they could break the loop's own iteration too.
    """
    import app.main as main_module

    loop_thread = threading.get_ident()
    threads: dict[str, set[int]] = {}

    def recorded(name: str, read: Callable[..., Any]) -> Callable[..., Any]:
        def reader(*args: Any, **kwargs: Any) -> Any:
            threads.setdefault(name, set()).add(threading.get_ident())
            return read(*args, **kwargs)

        return reader

    classifier = get_classifier()
    loop_owned = {
        "mqtt": (mqtt_service, "get_status"),
        "video": (auto_video_classifier, "get_status"),
        "video circuit": (auto_video_classifier, "get_circuit_status"),
        "photo workers": (high_quality_snapshot_service, "get_status"),
        "notifications": (main_module.notification_dispatcher, "get_status"),
        "admission": (classifier._classification_admission, "get_metrics"),
        "native recovery": (classifier._native_cpu_recovery, "snapshot"),
    }
    for name, (service, method) in loop_owned.items():
        monkeypatch.setattr(service, method, recorded(name, getattr(service, method)))
    monkeypatch.setattr(main_module, "get_db_pool_status", recorded("db pool", main_module.get_db_pool_status))
    monkeypatch.setattr(classifier, "check_health", recorded("classifier files", classifier.check_health))
    monkeypatch.setattr(main_module, "_read_health_files", recorded("health files", main_module._read_health_files))

    response = await client.get(path)

    assert response.status_code == 200, response.text
    for name in [*loop_owned, "db pool"]:
        assert threads.get(name) == {loop_thread}, f"{name} was read off the event loop"
    for name in ["classifier files", "health files"]:
        assert threads.get(name) and loop_thread not in threads[name], f"{name} blocked the event loop"


def test_a_model_reload_landing_while_the_classifier_reports_never_fails_the_report(
    monkeypatch: pytest.MonkeyPatch,
):
    """Reloads replace models from worker threads, so the status walks a copy of the model map."""
    classifier = get_classifier()
    models: dict[str, Any] = {}

    class _ModelReloadedMidRead:
        loaded = True
        error = None
        labels_path = None

        def get_status(self) -> dict[str, Any]:
            models["wildlife"] = SimpleNamespace(loaded=True, error=None, labels_path=None, get_status=dict)
            return {"loaded": True}

    models["bird"] = _ModelReloadedMidRead()
    monkeypatch.setattr(classifier, "_models", models)

    status = classifier.get_status()

    assert "bird" in status["models"]


@pytest.mark.asyncio
async def test_a_worker_pool_runtime_changed_in_place_while_the_status_is_read_never_fails_it(
    monkeypatch: pytest.MonkeyPatch,
):
    """The supervisor copies its metrics one level deep, so a pool's `runtime` dict is still its own.

    The copy handed to the worker thread must be taken in full on the loop; deep-copying it in
    the thread would walk that dict while the loop changes it in place.
    """
    classifier = get_classifier()
    runtime: dict[str, Any] = {"inference_backend": "onnx"}
    point = _Interleaving(lambda: runtime.__setitem__("model_id", "changed-in-place"))
    runtime["started_at"] = _NestedReading(point)
    supervisor = SimpleNamespace(get_metrics=lambda: {"live": {"workers": 1, "runtime": runtime}})
    monkeypatch.setattr(classifier, "_classifier_supervisor", supervisor)

    status = await classifier.collect_status()

    assert status["worker_pools"]["live"]["runtime"]["started_at"] == 1.0
    point.assert_read_only_on_the_loop()


def test_two_status_reads_meeting_the_finder_on_cpu_at_once_raise_one_incident(monkeypatch: pytest.MonkeyPatch):
    """Status reports run in several threads at once; the finder's CPU incident is raised once."""
    from app.services import error_diagnostics

    classifier = get_classifier()
    history = error_diagnostics.ErrorDiagnosticsHistory()
    monkeypatch.setattr(error_diagnostics, "error_diagnostics_history", history)
    both_comparing = threading.Barrier(2)

    class _EarlierFinder(str):
        """The finder identity recorded last. Comparing against it waits for the other reader to
        compare too, so without the lock both readers see a change before either records it."""

        def __eq__(self, other: object) -> bool:
            try:
                both_comparing.wait(timeout=1.0)
            except threading.BrokenBarrierError:
                pass
            return str.__eq__(self, other)

        __hash__ = str.__hash__

    problem = {
        "active": True,
        "model_id": "bird_crop_detector_accurate_rfdetr_nano",
        "provider": "cpu",
        "reason_code": "accelerator_unverified",
        "reason": "No current passing NPU or GPU evidence.",
        "action": "Check devices for RF-DETR Nano in Settings.",
    }
    monkeypatch.setattr(classifier, "_crop_detector_status", lambda _metrics: {"cpu_fallback": problem})
    earlier = (_EarlierFinder("an_earlier_finder"), "cpu", "rfdetr_cpu_fallback")
    # The attribute appears on the first health read, so it may not exist yet.
    monkeypatch.setattr(classifier, "_finder_cpu_warning", earlier, raising=False)

    with ThreadPoolExecutor(max_workers=2) as readers:
        list(readers.map(lambda _: classifier.check_health(), range(2)))

    incidents = [event for event in history.snapshot()["events"] if event["reason_code"] == "rfdetr_cpu_fallback"]
    assert sum(int(event.get("count") or 1) for event in incidents) == 1
