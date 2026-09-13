"""What the accelerator probes report, and what they refuse to invent."""

from pathlib import Path

from app.services.accelerator_telemetry import (
    AcceleratorSampler,
    DrmEngineTimeProbe,
    NpuBusyTimeProbe,
    NvidiaPresenceProbe,
)


def _write_npu(root: Path, node: str, busy_us: int) -> None:
    path = root / node / "device" / "npu_busy_time_us"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{busy_us}\n", encoding="utf-8")


def _write_fdinfo(proc_root: Path, pid: int, fd: int, body: str) -> None:
    path = proc_root / str(pid) / "fdinfo" / str(fd)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _drm_client(client_id: int, *, render_ns: int, video_ns: int, video_capacity: int = 2) -> str:
    return (
        "pos:\t0\n"
        "drm-driver:\ti915\n"
        f"drm-client-id:\t{client_id}\n"
        "drm-pdev:\t0000:00:02.0\n"
        "drm-total-system0:\t608 KiB\n"
        f"drm-engine-render:\t{render_ns} ns\n"
        f"drm-engine-video:\t{video_ns} ns\n"
        f"drm-engine-capacity-video:\t{video_capacity}\n"
    )


def test_npu_probe_scans_every_accel_node_rather_than_only_the_first(tmp_path: Path) -> None:
    # Probe order decides the number, so a host can present its NPU as accel1.
    _write_npu(tmp_path, "accel1", 1_000_000)
    probe = NpuBusyTimeProbe(accel_root=tmp_path)

    first = probe.read(now=10.0)
    assert [reading.id for reading in first] == ["accel1"]
    assert first[0].scope == "device", "the counter covers every user of the NPU, not just this app"
    assert first[0].utilization_percent is None, "nothing to diff against yet"

    _write_npu(tmp_path, "accel1", 1_500_000)
    second = probe.read(now=12.0)
    assert second[0].utilization_percent == 25.0


def test_npu_probe_reports_nothing_when_the_host_has_no_accelerator(tmp_path: Path) -> None:
    assert NpuBusyTimeProbe(accel_root=tmp_path / "absent").read(now=1.0) == []


def test_gpu_probe_reports_the_busiest_engine_this_app_used(tmp_path: Path) -> None:
    proc = tmp_path / "proc"
    _write_fdinfo(proc, 100, 9, _drm_client(1, render_ns=0, video_ns=0))
    probe = DrmEngineTimeProbe(proc_root=proc, drm_root=tmp_path / "drm")

    assert probe.read(now=10.0, pids=[100])[0].utilization_percent is None

    # Over two seconds: render ran 0.5s of one engine (25%), video 3.0s across two
    # engines (75%). Summing them would claim 100% of a GPU that was three quarters idle.
    _write_fdinfo(proc, 100, 9, _drm_client(1, render_ns=500_000_000, video_ns=3_000_000_000))
    reading = probe.read(now=12.0, pids=[100])[0]

    assert reading.utilization_percent == 75.0
    assert reading.kind == "gpu"
    assert reading.label == "Intel GPU"
    assert reading.scope == "app", "a container sees its own DRM clients and no others"


def test_gpu_probe_counts_one_client_once_however_many_descriptors_hold_it(tmp_path: Path) -> None:
    proc = tmp_path / "proc"
    # The same client on two descriptors (a dup), and a second client in another process.
    _write_fdinfo(proc, 100, 9, _drm_client(1, render_ns=0, video_ns=0))
    _write_fdinfo(proc, 100, 10, _drm_client(1, render_ns=0, video_ns=0))
    _write_fdinfo(proc, 200, 9, _drm_client(2, render_ns=0, video_ns=0))
    probe = DrmEngineTimeProbe(proc_root=proc, drm_root=tmp_path / "drm")
    probe.read(now=10.0, pids=[100, 200])

    _write_fdinfo(proc, 100, 9, _drm_client(1, render_ns=1_000_000_000, video_ns=0))
    _write_fdinfo(proc, 100, 10, _drm_client(1, render_ns=1_000_000_000, video_ns=0))
    _write_fdinfo(proc, 200, 9, _drm_client(2, render_ns=1_000_000_000, video_ns=0))
    reading = probe.read(now=12.0, pids=[100, 200])[0]

    # Two distinct clients ran one second each over two seconds: 100%, not 150%.
    assert reading.utilization_percent == 100.0


def test_gpu_probe_keeps_its_counters_when_it_is_given_no_processes(tmp_path: Path) -> None:
    proc = tmp_path / "proc"
    _write_fdinfo(proc, 100, 9, _drm_client(1, render_ns=0, video_ns=0))
    probe = DrmEngineTimeProbe(proc_root=proc, drm_root=tmp_path / "drm")
    probe.read(now=10.0, pids=[100])

    assert probe.read(now=11.0, pids=[]) == [], "nothing was measured, so nothing is claimed"

    _write_fdinfo(proc, 100, 9, _drm_client(1, render_ns=1_000_000_000, video_ns=0))
    reading = probe.read(now=12.0, pids=[100])[0]
    # The baseline survived the empty read, so this is one second of engine time in two.
    assert reading.utilization_percent == 50.0


def test_gpu_probe_ignores_a_counter_that_went_backwards(tmp_path: Path) -> None:
    proc = tmp_path / "proc"
    _write_fdinfo(proc, 100, 9, _drm_client(1, render_ns=5_000_000_000, video_ns=0))
    probe = DrmEngineTimeProbe(proc_root=proc, drm_root=tmp_path / "drm")
    probe.read(now=10.0, pids=[100])

    # A client that closed and reopened restarts its totals from zero.
    _write_fdinfo(proc, 100, 9, _drm_client(1, render_ns=0, video_ns=0))
    assert probe.read(now=12.0, pids=[100])[0].utilization_percent == 0.0


def test_nvidia_gpu_is_named_and_declared_unreadable(tmp_path: Path) -> None:
    (tmp_path / "0000:01:00.0").mkdir(parents=True)
    reading = NvidiaPresenceProbe(gpu_root=tmp_path).read()[0]

    assert reading.label == "NVIDIA GPU"
    assert reading.utilization_percent is None
    assert reading.unreadable == "nvidia_no_counter", "a present card says why it has no number"


def test_a_failing_probe_never_hides_the_accelerators_that_did_answer(tmp_path: Path) -> None:
    _write_npu(tmp_path, "accel0", 0)

    class Exploding:
        def read(self, *args: object, **kwargs: object) -> list[object]:
            raise OSError("device disappeared mid-read")

    sampler = AcceleratorSampler(
        npu_probe=NpuBusyTimeProbe(accel_root=tmp_path),
        drm_probe=Exploding(),
        nvidia_probe=Exploding(),
        clock=lambda: 1.0,
    )

    assert [reading.kind for reading in sampler.sample(pids=[1])] == ["npu"]
