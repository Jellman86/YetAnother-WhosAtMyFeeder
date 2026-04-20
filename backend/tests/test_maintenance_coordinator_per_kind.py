"""Per-kind capacity tests for MaintenanceCoordinator (issue #33).

Without per-kind capacity, a single long-running `video_classification`
holder (spawned automatically during historical video analysis) blocks
user-initiated kinds like `backfill` and `weather_backfill` — producing
the 962-deep pending_maintenance queue seen in the v2.9.13-dev bundle.

Per-kind capacity means different kinds do not contend for the same
slot; only the same kind throttles itself.
"""

from __future__ import annotations

import asyncio
import types

import pytest

from app.services.maintenance_coordinator import MaintenanceCoordinator


@pytest.mark.asyncio
async def test_different_kinds_do_not_block_each_other(monkeypatch):
    from app import config as config_module

    monkeypatch.setattr(
        config_module.settings,
        "maintenance",
        types.SimpleNamespace(max_concurrent=1, per_kind_capacity={}),
        raising=False,
    )

    coord = MaintenanceCoordinator()
    assert await coord.try_acquire("video-1", kind="video_classification") is True
    # A different kind must still be able to acquire its own slot even though
    # the video_classification slot is held.
    assert await coord.try_acquire("backfill-1", kind="backfill") is True
    assert await coord.try_acquire("weather-1", kind="weather_backfill") is True


@pytest.mark.asyncio
async def test_same_kind_still_throttles_to_per_kind_capacity(monkeypatch):
    from app import config as config_module

    monkeypatch.setattr(
        config_module.settings,
        "maintenance",
        types.SimpleNamespace(max_concurrent=1, per_kind_capacity={}),
        raising=False,
    )

    coord = MaintenanceCoordinator()
    assert await coord.try_acquire("video-1", kind="video_classification") is True
    # Second video_classification request must be rejected — single-slot per-kind.
    assert await coord.try_acquire("video-2", kind="video_classification") is False


@pytest.mark.asyncio
async def test_per_kind_capacity_override_allows_wider_concurrency(monkeypatch):
    from app import config as config_module

    monkeypatch.setattr(
        config_module.settings,
        "maintenance",
        types.SimpleNamespace(
            max_concurrent=1,
            per_kind_capacity={"video_classification": 3},
        ),
        raising=False,
    )

    coord = MaintenanceCoordinator()
    assert await coord.try_acquire("video-1", kind="video_classification") is True
    assert await coord.try_acquire("video-2", kind="video_classification") is True
    assert await coord.try_acquire("video-3", kind="video_classification") is True
    assert await coord.try_acquire("video-4", kind="video_classification") is False


@pytest.mark.asyncio
async def test_release_frees_only_that_kinds_slot(monkeypatch):
    from app import config as config_module

    monkeypatch.setattr(
        config_module.settings,
        "maintenance",
        types.SimpleNamespace(max_concurrent=1, per_kind_capacity={}),
        raising=False,
    )

    coord = MaintenanceCoordinator()
    assert await coord.try_acquire("video-1", kind="video_classification") is True
    assert await coord.try_acquire("backfill-1", kind="backfill") is True

    await coord.release("video-1")
    # Video slot freed; backfill still held.
    assert await coord.try_acquire("video-2", kind="video_classification") is True
    assert await coord.try_acquire("backfill-2", kind="backfill") is False


@pytest.mark.asyncio
async def test_total_max_concurrent_caps_cross_kind_concurrency(monkeypatch):
    # Safety-belt: even with per-kind capacity, an overall total cap prevents
    # DB-pool/CPU saturation when many kinds would otherwise run at once.
    from app import config as config_module

    monkeypatch.setattr(
        config_module.settings,
        "maintenance",
        types.SimpleNamespace(
            max_concurrent=1,
            per_kind_capacity={},
            total_max_concurrent=2,
        ),
        raising=False,
    )

    coord = MaintenanceCoordinator()
    assert await coord.try_acquire("a", kind="backfill") is True
    assert await coord.try_acquire("b", kind="weather_backfill") is True
    # Third kind hits the overall cap even though its per-kind slot is free.
    assert await coord.try_acquire("c", kind="taxonomy_sync") is False

    await coord.release("a")
    # Releasing frees a slot under the overall cap.
    assert await coord.try_acquire("c", kind="taxonomy_sync") is True


@pytest.mark.asyncio
async def test_total_max_concurrent_zero_means_unlimited(monkeypatch):
    from app import config as config_module

    monkeypatch.setattr(
        config_module.settings,
        "maintenance",
        types.SimpleNamespace(
            max_concurrent=1,
            per_kind_capacity={},
            total_max_concurrent=0,
        ),
        raising=False,
    )

    coord = MaintenanceCoordinator()
    for i, kind in enumerate(
        ["backfill", "weather_backfill", "taxonomy_sync", "timezone_repair", "analyze_unknowns"]
    ):
        assert await coord.try_acquire(f"h-{i}", kind=kind) is True


@pytest.mark.asyncio
async def test_status_reports_per_kind_capacity_breakdown(monkeypatch):
    from app import config as config_module

    monkeypatch.setattr(
        config_module.settings,
        "maintenance",
        types.SimpleNamespace(
            max_concurrent=1,
            per_kind_capacity={"video_classification": 2},
        ),
        raising=False,
    )

    coord = MaintenanceCoordinator()
    await coord.try_acquire("video-1", kind="video_classification")
    await coord.try_acquire("backfill-1", kind="backfill")

    status = await coord.get_status()
    assert status["active_total"] == 2
    # Per-kind capacity must be exposed so diagnostics can see which kinds are saturated.
    per_kind = status["capacity_by_kind"]
    assert per_kind["video_classification"] == 2
    assert per_kind["backfill"] == 1
