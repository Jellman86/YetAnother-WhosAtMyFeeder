"""Storage walks outlive individual HTTP requests without restarting on each poll."""

import asyncio

import pytest

from app.services.cache_stats_measurements import CacheStatsMeasurements


@pytest.mark.asyncio
async def test_pending_measurements_return_immediately_and_poll_one_shared_result():
    release = asyncio.Event()
    calls = 0

    async def collect():
        nonlocal calls
        calls += 1
        await release.wait()
        return {"total_size_bytes": 123}

    measurements = CacheStatsMeasurements(collect)
    first = measurements.get()
    assert first["status"] == "running"
    assert first["stats"] is None
    await asyncio.sleep(0)
    assert measurements.get()["id"] == first["id"]
    assert measurements.get(first["id"])["status"] == "running"
    assert calls == 1
    release.set()
    await asyncio.sleep(0)
    result = measurements.get(first["id"])
    assert result["status"] == "completed"
    assert result["stats"] == {"total_size_bytes": 123}
    assert measurements.get(first["id"])["stats"] == result["stats"]
    assert calls == 1


@pytest.mark.asyncio
async def test_a_new_measurement_does_not_discard_another_clients_completed_result():
    async def collect():
        return {"total_size_bytes": 12}

    measurements = CacheStatsMeasurements(collect)
    first = measurements.get()
    await asyncio.sleep(0)
    second = measurements.get()
    assert second["id"] != first["id"]
    assert measurements.get(first["id"])["status"] == "completed"
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_failed_measurement_hides_internal_details_and_allows_retry():
    async def collect():
        raise OSError("private-storage-details")

    measurements = CacheStatsMeasurements(collect)
    first = measurements.get()
    await asyncio.sleep(0)
    result = measurements.get(first["id"])
    assert result["status"] == "failed"
    assert "private-storage-details" not in str(result)
    assert result["stats"] is None
    assert measurements.get()["id"] != first["id"]
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_retained_results_are_bounded_and_unknown_ids_do_not_start_work():
    calls = 0

    async def collect():
        nonlocal calls
        calls += 1
        return {"total_size_bytes": calls}

    measurements = CacheStatsMeasurements(collect, max_retained=2)
    first = measurements.get()
    await asyncio.sleep(0)
    second = measurements.get()
    await asyncio.sleep(0)
    third = measurements.get()
    await asyncio.sleep(0)
    with pytest.raises(KeyError):
        measurements.get(first["id"])
    assert measurements.get(second["id"])["status"] == "completed"
    assert measurements.get(third["id"])["status"] == "completed"
    assert calls == 3
