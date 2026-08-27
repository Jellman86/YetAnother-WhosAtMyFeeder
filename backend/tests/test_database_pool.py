import asyncio

import pytest

from app.database import DatabasePool


@pytest.mark.asyncio
async def test_close_all_closes_tracked_connections_even_when_checked_out(tmp_path):
    db_path = tmp_path / "pool-close.db"
    pool = DatabasePool(str(db_path), pool_size=2)
    await pool.initialize()

    checked_out = await pool.acquire()

    assert pool._initialized is True
    assert len(pool._all_connections) == 2

    await pool.close_all()

    assert pool._initialized is False
    assert pool._pool.qsize() == 0
    assert len(pool._all_connections) == 0

    with pytest.raises(Exception):
        await checked_out.execute("SELECT 1")


@pytest.mark.asyncio
async def test_acquire_wait_max_ms_is_windowed_and_lifetime_is_preserved(tmp_path, monkeypatch):
    """The live `acquire_wait_max_ms` reflects recent acquire waits only; the
    lifetime high-water mark is preserved separately so diagnostics still have
    the all-time peak without pinning health to `degraded` forever."""
    from app import database as database_module

    # Shrink window to 2 s so the test runs quickly
    monkeypatch.setattr(database_module, "DB_POOL_WAIT_WINDOW_SECONDS", 2.0)

    db_path = tmp_path / "pool-window.db"
    pool = DatabasePool(str(db_path), pool_size=1)
    await pool.initialize()

    # Simulate a single very slow acquire in the past — outside the window
    now = [1_000.0]
    monkeypatch.setattr(database_module.time, "monotonic", lambda: now[0])

    pool._record_wait_sample(waited_ms=10_000.0)

    status = pool.get_status()
    assert status["acquire_wait_max_ms"] == 10_000.0
    assert status["acquire_wait_lifetime_max_ms"] == 10_000.0

    # Advance past the window; the old sample should age out of the live max
    now[0] += 5.0
    pool._record_wait_sample(waited_ms=50.0)

    status = pool.get_status()
    assert status["acquire_wait_max_ms"] == 50.0, "Stale sample should have aged out of the live windowed max"
    assert status["acquire_wait_lifetime_max_ms"] == 10_000.0, "Lifetime max must be preserved for diagnostics"

    await pool.close_all()


@pytest.mark.asyncio
async def test_acquire_wait_sample_buffer_is_bounded(tmp_path, monkeypatch):
    """Under sustained load the sample buffer must not grow unbounded — this
    guards against a memory leak on a system doing >100 acquires/sec for hours.
    """
    from app import database as database_module

    monkeypatch.setattr(database_module, "DB_POOL_WAIT_WINDOW_SECONDS", 3600.0)

    db_path = tmp_path / "pool-bounded.db"
    pool = DatabasePool(str(db_path), pool_size=1)
    await pool.initialize()

    # Push many samples with monotonic timestamps so none age out
    ts = [1_000.0]
    monkeypatch.setattr(database_module.time, "monotonic", lambda: ts[0])
    for i in range(50_000):
        pool._record_wait_sample(waited_ms=float(i % 100))
        ts[0] += 0.001

    assert len(pool._wait_samples) <= database_module.DB_POOL_WAIT_SAMPLE_CAP, (
        "Sample buffer must be capped to prevent unbounded growth"
    )

    await pool.close_all()


@pytest.mark.asyncio
async def test_hold_time_is_measured_so_the_cause_of_exhaustion_is_visible(tmp_path):
    """Acquire wait is the symptom of pool exhaustion; hold time is the cause.

    A pool that only measures waiting can say "requests queued for 17 seconds"
    without saying what held the connections. Diagnostics need both.
    """
    from app import database as database_module

    pool = DatabasePool(str(tmp_path / "pool-hold.db"), pool_size=2)
    await pool.initialize()

    conn = await pool.acquire(label="test:slow-caller")
    await pool.release(conn, hold_ms=1_500.0)

    status = pool.get_status()
    assert status["hold_ms_lifetime_max"] == 1_500.0
    assert status["slow_hold_count"] == 1
    assert status["slow_hold_warn_ms"] == database_module.DB_POOL_SLOW_HOLD_WARN_MS
    assert status["slow_hold_last_label"] == "test:slow-caller"

    await pool.close_all()


@pytest.mark.asyncio
async def test_status_names_what_is_holding_a_connection_right_now(tmp_path):
    """The live culprit, not just the historical peak.

    When an owner opens diagnostics *during* a stall, the question is "what is
    holding the pool", and a lifetime maximum cannot answer it.
    """
    pool = DatabasePool(str(tmp_path / "pool-live.db"), pool_size=2)
    await pool.initialize()

    conn = await pool.acquire(label="events:reclassify")

    status = pool.get_status()
    assert status["checked_out"] == 1
    assert status["longest_active_hold_label"] == "events:reclassify"
    assert status["longest_active_hold_ms"] >= 0.0

    await pool.release(conn)
    assert pool.get_status()["longest_active_hold_label"] is None

    await pool.close_all()


@pytest.mark.asyncio
async def test_acquire_fails_honestly_instead_of_waiting_forever(tmp_path, monkeypatch):
    """An exhausted pool must report itself, not hang.

    The reported 17.8 s waits were requests queued behind held connections with
    no upper bound. A request that cannot be served is better refused with a
    diagnosable error than left to a client timeout with nothing in the log.
    """
    from app import database as database_module
    from app.database import DatabasePoolTimeout

    monkeypatch.setattr(database_module, "DB_POOL_ACQUIRE_TIMEOUT_SECONDS", 0.2)

    pool = DatabasePool(str(tmp_path / "pool-timeout.db"), pool_size=1)
    await pool.initialize()

    held = await pool.acquire(label="test:hog")
    try:
        with pytest.raises(DatabasePoolTimeout) as excinfo:
            await pool.acquire(label="test:waiter")
        assert "test:hog" in str(excinfo.value), "The error must name what held the pool"
        assert pool.get_status()["acquire_timeouts"] == 1
    finally:
        await pool.release(held)

    await pool.close_all()


@pytest.mark.asyncio
async def test_a_zero_timeout_setting_disables_the_deadline(tmp_path, monkeypatch):
    """An owner on slow hardware must be able to opt out of the deadline.

    Refusing a request that would have succeeded is worse than serving it late,
    so the deadline has to be escapable without editing code.
    """
    from app import database as database_module

    monkeypatch.setattr(database_module, "DB_POOL_ACQUIRE_TIMEOUT_SECONDS", 0.0)

    pool = DatabasePool(str(tmp_path / "pool-nodeadline.db"), pool_size=1)
    await pool.initialize()

    held = await pool.acquire()
    waiter = asyncio.create_task(pool.acquire())
    await asyncio.sleep(0.3)
    assert not waiter.done(), "With the deadline disabled the acquire must keep waiting"

    await pool.release(held)
    conn = await waiter
    await pool.release(conn)
    await pool.close_all()


@pytest.mark.asyncio
async def test_get_db_labels_the_calling_module_and_function(tmp_path, monkeypatch):
    """A stall must name real application code, not `contextlib`.

    `get_db` is an async context manager, so the frames directly above the pool
    belong to `contextlib`'s wrapper. Labelling those would make every hold look
    identical and tell an owner nothing.
    """
    from app import database as database_module

    pool = DatabasePool(str(tmp_path / "pool-label.db"), pool_size=2)
    await pool.initialize()
    monkeypatch.setattr(database_module, "_db_pool", pool)

    seen: dict[str, object] = {}

    async def caller_that_holds_a_connection():
        async with database_module.get_db():
            seen["label"] = pool.get_status()["longest_active_hold_label"]

    await caller_that_holds_a_connection()

    assert seen["label"] == f"{__name__}:caller_that_holds_a_connection"

    await pool.close_all()


@pytest.mark.asyncio
async def test_a_released_connection_is_not_counted_as_still_held(tmp_path, monkeypatch):
    """Checked-out bookkeeping must not leak.

    A leaked entry would make `longest_active_hold_ms` grow without bound and
    point every future diagnosis at a caller that finished long ago.
    """
    from app import database as database_module

    pool = DatabasePool(str(tmp_path / "pool-leak.db"), pool_size=2)
    await pool.initialize()
    monkeypatch.setattr(database_module, "_db_pool", pool)

    for _ in range(25):
        async with database_module.get_db() as db:
            await db.execute("SELECT 1")

    status = pool.get_status()
    assert status["checked_out"] == 0
    assert status["longest_active_hold_label"] is None
    assert pool._checked_out == {}

    await pool.close_all()


@pytest.mark.asyncio
async def test_a_timed_out_acquire_does_not_lose_a_connection(tmp_path, monkeypatch):
    """Cancelling a queued getter must not swallow the connection it raced.

    The deadline cancels an in-flight `Queue.get()`. If that cancellation landed
    between a connection being handed over and the getter resuming, the
    connection would vanish from the pool and every timeout would shrink the
    pool by one until nothing worked at all.
    """
    from app import database as database_module
    from app.database import DatabasePoolTimeout

    monkeypatch.setattr(database_module, "DB_POOL_ACQUIRE_TIMEOUT_SECONDS", 0.05)

    pool = DatabasePool(str(tmp_path / "pool-race.db"), pool_size=2)
    await pool.initialize()

    for _ in range(40):
        first = await pool.acquire()
        second = await pool.acquire()
        # Release exactly as the waiter's deadline expires, to race the two.
        releaser = asyncio.create_task(_release_after(pool, first, 0.05))
        try:
            third = await pool.acquire()
        except DatabasePoolTimeout:
            third = None
        await releaser
        if third is not None:
            await pool.release(third)
        else:
            pass
        await pool.release(second)
        # Drain back to a known-full pool before the next round.
        while pool._pool.qsize() < 2:
            await asyncio.sleep(0)

    assert pool._pool.qsize() == 2, "Every connection must return to the pool"
    assert len(pool._all_connections) == 2
    assert pool._checked_out == {}

    await pool.close_all()


async def _release_after(pool, conn, delay):
    await asyncio.sleep(delay)
    await pool.release(conn)


@pytest.mark.asyncio
async def test_close_all_clears_checked_out_bookkeeping(tmp_path):
    """A pool closed with connections outstanding must not report them forever."""
    pool = DatabasePool(str(tmp_path / "pool-close-held.db"), pool_size=2)
    await pool.initialize()

    await pool.acquire(label="test:holder")
    assert pool.get_status()["checked_out"] == 1

    await pool.close_all()

    assert pool._checked_out == {}
    assert pool.get_status()["longest_active_hold_label"] is None


@pytest.mark.asyncio
async def test_pool_exhaustion_answers_503_not_500(monkeypatch):
    """An exhausted pool is a temporary capacity problem, not a server fault.

    503 with `Retry-After` tells a client (and a reverse proxy) to come back;
    500 tells it something is broken and invites a retry storm on a pool that
    is already saturated.
    """
    from fastapi.testclient import TestClient

    from app.database import DatabasePoolTimeout
    from app.main import app

    @app.get("/api/_test_pool_exhausted")
    async def _exhausted():  # pragma: no cover - exercised via the client below
        raise DatabasePoolTimeout("Longest holder: routers.ai:analyze for 42.0s.")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/_test_pool_exhausted")

    assert response.status_code == 503
    assert response.headers.get("Retry-After")
    body = response.json()
    assert "busy" in body["detail"].lower()
    # The holder is an internal detail; clients get a plain-language cause.
    assert "routers.ai" not in response.text


def test_db_pool_degrades_health_on_long_connection_holds():
    """Health must react to the cause, not only the symptom.

    Long acquire waits already degrade health. But by the time requests are
    queueing the damage is done; a connection held for seconds is the earlier
    and more actionable signal, and it names the code responsible.
    """
    from app.main import db_pool_is_degraded

    healthy = {"acquire_wait_max_ms": 12.0, "hold_ms_max": 60.0}
    assert db_pool_is_degraded(healthy) is False

    queueing = {"acquire_wait_max_ms": 9_000.0, "hold_ms_max": 60.0}
    assert db_pool_is_degraded(queueing) is True

    holding = {"acquire_wait_max_ms": 12.0, "hold_ms_max": 9_000.0}
    assert db_pool_is_degraded(holding) is True


def test_db_pool_health_recovers_once_long_holds_age_out():
    """A single bad hold must not pin health to degraded forever.

    `hold_ms_max` is windowed for the same reason `acquire_wait_max_ms` is: an
    owner who fixes the cause needs to see the system report itself well again.
    The lifetime peak stays in diagnostics but must not drive status.
    """
    from app.main import db_pool_is_degraded

    recovered = {
        "acquire_wait_max_ms": 3.0,
        "hold_ms_max": 40.0,
        "hold_ms_lifetime_max": 17_785.0,
        "acquire_wait_lifetime_max_ms": 17_785.0,
    }
    assert db_pool_is_degraded(recovered) is False, "Lifetime peaks must not hold health down"


def test_db_pool_degradation_tolerates_a_missing_or_empty_status():
    """An uninitialised pool is not a degraded one."""
    from app.main import db_pool_is_degraded

    assert db_pool_is_degraded({}) is False
    assert db_pool_is_degraded({"acquire_wait_max_ms": None, "hold_ms_max": None}) is False


def test_the_acquire_deadline_clears_the_sqlite_busy_timeout():
    """The deadline must not fire on a legitimately lock-blocked statement.

    A writer blocked on the database lock waits up to `busy_timeout` (30 s by
    default) while holding its connection. If the acquire deadline were equal to
    or shorter than that, an install under normal write contention would start
    refusing requests that were about to be served — converting a slow moment
    into an outage. The deadline exists to bound a hang, not to shed load.
    """
    from app import database as database_module

    assert database_module.DB_POOL_ACQUIRE_TIMEOUT_SECONDS > (database_module.DEFAULT_DB_BUSY_TIMEOUT_MS / 1000.0), (
        "The acquire deadline must be longer than the SQLite busy timeout"
    )


@pytest.mark.asyncio
async def test_ingest_waits_for_a_connection_rather_than_dropping_a_detection(tmp_path, monkeypatch):
    """Work that cannot be retried must never be refused a connection.

    A Frigate event arrives once. `process_mqtt_message` logs and returns on any
    exception, so a refused acquire during ingest is a detection lost for good —
    exactly what §1 forbids. The acquire deadline exists to stop an HTTP request
    hanging behind a browser that has already given up; an ingest task has no
    one waiting, so making it wait only delays a write, while refusing it
    destroys one.
    """
    from app import database as database_module
    from app.database import DatabasePool, DatabasePoolTimeout, durable_work

    monkeypatch.setattr(database_module, "DB_POOL_ACQUIRE_TIMEOUT_SECONDS", 0.2)
    pool = DatabasePool(str(tmp_path / "pool-ingest.db"), pool_size=1)
    await pool.initialize()
    monkeypatch.setattr(database_module, "_db_pool", pool)

    held = await pool.acquire(label="test:hog")

    # An ordinary request is refused, because something is waiting on it.
    with pytest.raises(DatabasePoolTimeout):
        async with database_module.get_db():
            pass

    # Ingest is not.
    async def ingest():
        with durable_work():
            async with database_module.get_db() as db:
                await db.execute("SELECT 1")
                return "written"

    waiting = asyncio.create_task(ingest())
    await asyncio.sleep(0.5)
    assert not waiting.done(), "Ingest must keep waiting rather than be refused"

    await pool.release(held)
    assert await asyncio.wait_for(waiting, timeout=5) == "written"

    await pool.close_all()


@pytest.mark.asyncio
async def test_durable_work_marking_reaches_nested_service_calls(tmp_path, monkeypatch):
    """The marking has to survive the call chain, not just the first frame.

    Ingest reaches the database through the event processor, the detection
    service and a repository. Annotating each call site would leave the
    guarantee one missed argument away from silent data loss, so it rides on the
    task context and every await below it inherits it.
    """
    from app import database as database_module
    from app.database import DatabasePool, durable_work

    monkeypatch.setattr(database_module, "DB_POOL_ACQUIRE_TIMEOUT_SECONDS", 0.2)
    pool = DatabasePool(str(tmp_path / "pool-nested.db"), pool_size=1)
    await pool.initialize()
    monkeypatch.setattr(database_module, "_db_pool", pool)

    held = await pool.acquire(label="test:hog")

    async def deep_repository_write():
        async with database_module.get_db() as db:
            await db.execute("SELECT 1")
            return "written"

    async def service_layer():
        return await deep_repository_write()

    async def ingest_entry_point():
        with durable_work():
            # A child task inherits the context it was created in.
            return await asyncio.create_task(service_layer())

    waiting = asyncio.create_task(ingest_entry_point())
    await asyncio.sleep(0.5)
    assert not waiting.done(), "The marking must reach nested and child-task calls"

    await pool.release(held)
    assert await asyncio.wait_for(waiting, timeout=5) == "written"

    await pool.close_all()


@pytest.mark.asyncio
async def test_releasing_into_a_closed_pool_does_not_resurrect_a_connection(tmp_path):
    """Shutdown must stay shut.

    `close_all` closes checked-out connections too, so an in-flight request
    releasing afterwards hands back a connection that is already closed. The
    rollback then fails, which is the corrupt-connection path — and that path
    opens a *replacement* and puts it in the pool. A pool that has been closed
    would come back holding a live connection nothing will ever close, on every
    shutdown that raced a request.
    """
    pool = DatabasePool(str(tmp_path / "pool-shutdown.db"), pool_size=2)
    await pool.initialize()

    in_flight = await pool.acquire(label="test:in-flight")
    await pool.close_all()

    await pool.release(in_flight)

    assert pool._pool.qsize() == 0, "A closed pool must not gain a connection"
    assert pool._all_connections == set()
    assert pool._initialized is False


@pytest.mark.asyncio
async def test_a_task_holding_a_connection_never_waits_without_a_deadline(tmp_path, monkeypatch):
    """The unbounded wait must not apply to a caller that already holds one.

    Waiting forever is safe only while holding nothing. A task that holds a
    connection and waits for a second is the deadlock this whole change exists
    to remove, and for durable work there would be no deadline to break it —
    ingest would stop permanently, losing every later detection rather than
    delaying one. So depth beyond the first acquire always takes the deadline.
    """
    from app import database as database_module
    from app.database import DatabasePool, DatabasePoolTimeout, durable_work

    monkeypatch.setattr(database_module, "DB_POOL_ACQUIRE_TIMEOUT_SECONDS", 0.2)
    pool = DatabasePool(str(tmp_path / "pool-depth.db"), pool_size=1)
    await pool.initialize()
    monkeypatch.setattr(database_module, "_db_pool", pool)

    async def nested_durable_acquire():
        with durable_work():
            async with database_module.get_db():
                # Already holding the only connection; asking for a second must
                # fail rather than hang the ingest pipeline for good.
                async with database_module.get_db():
                    pass

    # Bounded so the failure mode is a failing test rather than a hung suite.
    with pytest.raises(DatabasePoolTimeout):
        await asyncio.wait_for(nested_durable_acquire(), timeout=5)

    assert pool.get_status()["nested_acquires"] >= 1
    await pool.close_all()


@pytest.mark.asyncio
async def test_nested_acquisition_is_counted_and_named(tmp_path, monkeypatch):
    """Nesting is the deadlock mechanism, so it must be visible before it bites."""
    from app import database as database_module
    from app.database import DatabasePool

    pool = DatabasePool(str(tmp_path / "pool-nest-count.db"), pool_size=3)
    await pool.initialize()
    monkeypatch.setattr(database_module, "_db_pool", pool)

    assert pool.get_status()["nested_acquires"] == 0

    async def holds_then_asks_again():
        async with database_module.get_db() as outer:
            await outer.execute("SELECT 1")
            async with database_module.get_db() as inner:
                await inner.execute("SELECT 1")

    await holds_then_asks_again()

    status = pool.get_status()
    assert status["nested_acquires"] == 1
    assert "holds_then_asks_again" in (status["last_nested_acquire_label"] or "")
    assert status["checked_out"] == 0

    await pool.close_all()


def test_reported_wait_average_never_exceeds_the_reported_wait_maximum():
    """The average and the maximum must describe the same span of time.

    A lifetime average printed beside a windowed maximum reads as broken
    arithmetic on any long-running install: once the early slow waits age out
    of the window, the average sits above the maximum and an owner reasonably
    concludes the pool numbers cannot be trusted.
    """
    pool = DatabasePool("unused.db", pool_size=2)

    pool._record_wait_sample(900.0)
    pool._acquire_count = 1
    pool._acquire_wait_total_ms = 900.0

    # The slow wait ages out of the live window; a fast one replaces it.
    pool._wait_samples.clear()
    pool._record_wait_sample(4.0)
    pool._acquire_count = 2
    pool._acquire_wait_total_ms = 904.0

    status = pool.get_status()

    assert status["acquire_wait_max_ms"] == 4.0
    assert status["acquire_wait_avg_ms"] <= status["acquire_wait_max_ms"]
    assert status["acquire_wait_lifetime_max_ms"] == 900.0


def test_reported_hold_average_never_exceeds_the_reported_hold_maximum():
    """Same contract for hold times, which drive the slow-holder diagnosis."""
    pool = DatabasePool("unused.db", pool_size=2)

    pool._hold_samples.append((0.0, 4000.0))
    pool._hold_count = 1
    pool._hold_total_ms = 4000.0
    pool._hold_lifetime_max_ms = 4000.0

    pool._hold_samples.clear()
    pool._record_hold_sample(object(), hold_ms=12.0)

    status = pool.get_status()

    assert status["hold_ms_max"] == 12.0
    assert status["hold_ms_avg"] <= status["hold_ms_max"]
    assert status["hold_ms_lifetime_max"] == 4000.0
