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
