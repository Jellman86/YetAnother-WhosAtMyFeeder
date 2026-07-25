from pathlib import Path

import httpx
import pytest

from app.main import app
from app.routers import stats as stats_router
from app.services.system_telemetry import SystemTelemetrySample, SystemTelemetrySampler


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
