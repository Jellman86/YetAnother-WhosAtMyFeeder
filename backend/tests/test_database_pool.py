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
    assert status["acquire_wait_max_ms"] == 50.0, (
        "Stale sample should have aged out of the live windowed max"
    )
    assert status["acquire_wait_lifetime_max_ms"] == 10_000.0, (
        "Lifetime max must be preserved for diagnostics"
    )

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
