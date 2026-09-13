import asyncio
from pathlib import Path

import httpx
import pytest

from app.main import app
from app.routers import stats as stats_router
from app.services.system_telemetry import SystemTelemetrySample, SystemTelemetrySampler
from app.services.update_service import update_service


def _write_cpu_stat(path: Path, *, user: int, system: int, idle: int) -> None:
    path.write_text(f"cpu  {user} 0 {system} {idle} 0 0 0 0 0 0\n", encoding="utf-8")


def test_sampler_reports_real_cpu_and_npu_utilization_from_counter_deltas(tmp_path: Path) -> None:
    proc_stat = tmp_path / "stat"
    npu_busy = tmp_path / "npu_busy_time_us"
    _write_cpu_stat(proc_stat, user=100, system=100, idle=800)
    npu_busy.write_text("100000\n", encoding="utf-8")
    clock_values = iter([10.0, 12.0])

    sampler = SystemTelemetrySampler(
        proc_stat_path=proc_stat,
        npu_busy_path=npu_busy,
        clock=lambda: next(clock_values),
    )

    first = sampler.sample()
    assert first.cpu_percent is None
    assert first.accelerator_kind == "npu"
    assert first.accelerator_label == "NPU"
    assert first.accelerator_percent is None

    _write_cpu_stat(proc_stat, user=150, system=150, idle=900)
    npu_busy.write_text("500000\n", encoding="utf-8")

    second = sampler.sample()
    assert second.cpu_percent == 50.0
    assert second.accelerator_kind == "npu"
    assert second.accelerator_label == "NPU"
    assert second.accelerator_percent == 20.0


@pytest.mark.asyncio
async def test_system_telemetry_endpoint_returns_live_sample_without_caching(monkeypatch: pytest.MonkeyPatch) -> None:
    class StubSampler:
        def sample(self) -> SystemTelemetrySample:
            return SystemTelemetrySample(
                cpu_percent=37.5,
                accelerator_kind="npu",
                accelerator_label="NPU",
                accelerator_percent=18.2,
            )

    monkeypatch.setattr(stats_router, "system_telemetry_sampler", StubSampler(), raising=False)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/system-telemetry")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "sampled_at": response.json()["sampled_at"],
        "cpu_percent": 37.5,
        "accelerator": {"kind": "npu", "label": "NPU", "utilization_percent": 18.2},
    }


@pytest.mark.asyncio
async def test_update_status_endpoint_is_never_browser_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    async def stub_status(current_version: str, branch: str, git_hash: str) -> dict:
        return {
            "current_version": current_version,
            "channel": branch,
            "latest_version": f"2.17.0-{branch}+abcdef0",
            "update_available": True,
            "release_url": "https://example.test/tree/dev",
            "checked_at": "2026-08-13T00:00:00+00:00",
            "enabled": True,
            "error": None,
        }

    monkeypatch.setattr(update_service, "get_status", stub_status)
    monkeypatch.setenv("APP_VERSION", "2.17.0-dev+1234567")
    monkeypatch.setenv("APP_BRANCH", "dev")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/update-status")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert response.json()["update_available"] is True


def _write_process(
    proc: Path, pid: int, *, ppid: int, comm: str, ticks: int, rss_pages: int, cmdline: list[str]
) -> None:
    folder = proc / str(pid)
    folder.mkdir(parents=True, exist_ok=True)
    # Field order after the comm: state, ppid, ... utime is the 14th field of the line, stime the 15th.
    rest = ["S", str(ppid), "1", "1", "0", "-1", "0", "0", "0", "0", "0", str(ticks), "0", "0", "0"]
    (folder / "stat").write_text(f"{pid} ({comm}) " + " ".join(rest) + "\n", encoding="utf-8")
    (folder / "statm").write_text(f"{rss_pages + 10} {rss_pages} 0 0 0 0 0\n", encoding="utf-8")
    (folder / "cmdline").write_bytes(b"\0".join(part.encode() for part in cmdline) + b"\0")


def test_process_sampler_names_this_apps_processes_and_only_those(tmp_path: Path) -> None:
    """The app, its classifier workers and an ffmpeg it spawned are named; an unrelated
    process on the host is never listed. CPU is the share of the whole host over the
    interval, so it is on the same scale as the host figure."""
    from app.services.system_telemetry import ProcessLoadSampler

    proc = tmp_path / "proc"
    _write_process(proc, 100, ppid=1, comm="python", ticks=0, rss_pages=100, cmdline=["python", "-m", "uvicorn"])
    _write_process(
        proc,
        101,
        ppid=100,
        comm="python",
        ticks=0,
        rss_pages=50,
        cmdline=["python", "-m", "app.services.classifier_worker_process", "video-0", "3"],
    )
    _write_process(proc, 102, ppid=101, comm="ffmpeg", ticks=0, rss_pages=5, cmdline=["ffmpeg", "-i", "clip.mp4"])
    _write_process(proc, 200, ppid=1, comm="frigate", ticks=0, rss_pages=999, cmdline=["frigate"])
    clock_values = iter([0.0, 2.0])
    sampler = ProcessLoadSampler(
        proc_root=proc,
        pid=100,
        cpu_count=4,
        clock_ticks_per_second=100,
        page_size=4096,
        clock=lambda: next(clock_values),
    )

    first = sampler.sample()
    assert [load.pid for load in first] == [100, 101, 102]
    assert all(load.cpu_percent is None for load in first)

    # Two seconds later: the worker burned 4 s of CPU across 4 cores (50% of the host), the
    # main process 0.4 s (5%), ffmpeg nothing.
    _write_process(proc, 100, ppid=1, comm="python", ticks=40, rss_pages=100, cmdline=["python", "-m", "uvicorn"])
    _write_process(
        proc,
        101,
        ppid=100,
        comm="python",
        ticks=400,
        rss_pages=50,
        cmdline=["python", "-m", "app.services.classifier_worker_process", "video-0", "3"],
    )
    second = {load.pid: load for load in sampler.sample()}

    assert second[100].role == "main" and second[100].label == "YA-WAMF"
    assert second[100].cpu_percent == 5.0
    assert second[100].rss_bytes == 100 * 4096
    assert second[101].role == "video_worker" and second[101].label == "video-0"
    assert second[101].cpu_percent == 50.0
    assert second[102].role == "ffmpeg" and second[102].cpu_percent == 0.0
    assert 200 not in second


def test_history_keeps_a_rolling_window_and_measures_the_rest_of_the_host() -> None:
    from app.services.system_telemetry import ProcessLoad, SystemTelemetryHistory

    history = SystemTelemetryHistory(window_seconds=15, interval_seconds=5)
    sample = SystemTelemetrySample(
        cpu_percent=40.0, accelerator_kind="npu", accelerator_label="NPU", accelerator_percent=12.0
    )
    processes = [
        ProcessLoad(pid=1, role="main", label="YA-WAMF", detail=None, cpu_percent=5.0, rss_bytes=10),
        ProcessLoad(pid=2, role="live_worker", label="live-0", detail=None, cpu_percent=25.5, rss_bytes=20),
    ]
    for at in (0.0, 5.0, 10.0, 15.0):
        history.record(sample, processes, at=at)

    snapshot = history.snapshot()
    assert [point.at for point in snapshot.points] == [5.0, 10.0, 15.0], "the window is three samples wide"
    assert snapshot.points[-1].app_cpu_percent == 30.5
    assert snapshot.points[-1].other_cpu_percent == 9.5
    assert snapshot.accelerator_label == "NPU"
    assert [load.label for load in snapshot.processes] == ["YA-WAMF", "live-0"]

    # The remainder can never be negative, however the per-process reads round.
    history.record(
        SystemTelemetrySample(cpu_percent=3.0, accelerator_kind=None, accelerator_label=None, accelerator_percent=None),
        processes,
        at=20.0,
    )
    assert history.snapshot().points[-1].other_cpu_percent == 0.0


@pytest.mark.asyncio
async def test_system_telemetry_history_is_for_the_owner_only(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.system_telemetry import ProcessLoad, SystemTelemetryHistory

    history = SystemTelemetryHistory(window_seconds=10, interval_seconds=5)
    history.record(
        SystemTelemetrySample(
            cpu_percent=16.3, accelerator_kind="npu", accelerator_label="NPU", accelerator_percent=0.0
        ),
        [ProcessLoad(pid=7, role="main", label="YA-WAMF", detail=None, cpu_percent=3.1, rss_bytes=1_000)],
        at=1_789_000_000.0,
    )
    monkeypatch.setattr(stats_router, "system_telemetry_history", history, raising=False)
    monkeypatch.setattr(
        stats_router,
        "collect_host_facts",
        lambda: {
            "cpu_count": 14,
            "cpu_quota": None,
            "memory_total_bytes": 24_000,
            "memory_limit_bytes": None,
            "effective_cpus": 14.0,
        },
        raising=False,
    )
    from app.config import settings

    monkeypatch.setattr(settings.auth, "enabled", True)
    monkeypatch.setattr(settings.auth, "initial_setup_complete", True)
    monkeypatch.setattr(settings.public_access, "enabled", True)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.get("/api/system-telemetry/history")
        assert denied.status_code in (401, 403)

        from app.auth import AuthContext, AuthLevel, require_owner

        app.dependency_overrides[require_owner] = lambda: AuthContext(AuthLevel.OWNER, "owner")
        try:
            response = await client.get("/api/system-telemetry/history")
        finally:
            app.dependency_overrides.pop(require_owner, None)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["window_seconds"] == 10
    assert body["interval_seconds"] == 5.0
    assert body["host"] == {
        "cpu_count": 14,
        "cpu_quota": None,
        "memory_total_bytes": 24_000,
        "memory_limit_bytes": None,
        "effective_cpus": 14.0,
    }
    assert body["accelerator"] == {"kind": "npu", "label": "NPU"}
    assert body["points"] == [
        {
            "at": 1_789_000_000.0,
            "cpu_percent": 16.3,
            "accelerator_percent": 0.0,
            "app_cpu_percent": 3.1,
            "other_cpu_percent": 13.2,
        }
    ]
    assert body["processes"] == [
        {"pid": 7, "role": "main", "label": "YA-WAMF", "detail": None, "cpu_percent": 3.1, "rss_bytes": 1_000}
    ]
    assert body["app_rss_bytes"] == 1_000


@pytest.mark.asyncio
async def test_history_service_records_a_sample_each_tick() -> None:
    from app.services.system_telemetry import (
        ProcessLoad,
        SystemTelemetryHistory,
        SystemTelemetryHistoryService,
    )

    class StubSampler:
        def sample(self) -> SystemTelemetrySample:
            return SystemTelemetrySample(
                cpu_percent=10.0, accelerator_kind=None, accelerator_label=None, accelerator_percent=None
            )

    class StubProcesses:
        def sample(self) -> list[ProcessLoad]:
            return [ProcessLoad(pid=1, role="main", label="YA-WAMF", detail=None, cpu_percent=2.0, rss_bytes=1)]

    history = SystemTelemetryHistory(window_seconds=100, interval_seconds=0.01)
    ticks = iter(range(1, 100))
    service = SystemTelemetryHistoryService(
        history=history, sampler=StubSampler(), process_sampler=StubProcesses(), wall_clock=lambda: float(next(ticks))
    )
    await service.start()
    await asyncio.sleep(0.08)
    await service.stop()

    points = history.snapshot().points
    assert len(points) >= 3
    assert points[0].other_cpu_percent == 8.0
