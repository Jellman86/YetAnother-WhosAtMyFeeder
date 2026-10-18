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


def _xe_client(client_id: int, *, cycles: int, total_cycles: int, capacity: int = 1) -> str:
    return (
        "pos:\t0\n"
        "drm-driver:\txe\n"
        f"drm-client-id:\t{client_id}\n"
        "drm-pdev:\t0000:00:02.0\n"
        f"drm-cycles-render:\t{cycles}\n"
        f"drm-total-cycles-render:\t{total_cycles}\n"
        f"drm-engine-capacity-render:\t{capacity}\n"
    )


def test_gpu_probe_reads_xe_cycle_counters_as_a_busy_fraction(tmp_path: Path) -> None:
    proc = tmp_path / "proc"
    _write_fdinfo(proc, 100, 9, _xe_client(1, cycles=0, total_cycles=1_000))
    probe = DrmEngineTimeProbe(proc_root=proc, drm_root=tmp_path / "drm")

    assert probe.read(now=10.0, pids=[100])[0].utilization_percent is None, "first cycle reading is a baseline"

    _write_fdinfo(proc, 100, 9, _xe_client(1, cycles=500, total_cycles=3_000))
    reading = probe.read(now=12.0, pids=[100])[0]
    # 500 busy cycles of 2000 total. Read as nanoseconds over two seconds this
    # would claim roughly 0%, which is why cycles must not take the ns path.
    assert reading.utilization_percent == 25.0
    assert reading.label == "Intel GPU"


def test_gpu_probe_xe_cycles_respect_engine_capacity(tmp_path: Path) -> None:
    proc = tmp_path / "proc"
    _write_fdinfo(proc, 100, 9, _xe_client(1, cycles=0, total_cycles=0, capacity=2))
    probe = DrmEngineTimeProbe(proc_root=proc, drm_root=tmp_path / "drm")
    probe.read(now=10.0, pids=[100])

    _write_fdinfo(proc, 100, 9, _xe_client(1, cycles=1_000, total_cycles=2_000, capacity=2))
    assert probe.read(now=12.0, pids=[100])[0].utilization_percent == 25.0


def test_gpu_probe_does_not_sum_shared_xe_total_cycle_denominators(tmp_path: Path) -> None:
    proc = tmp_path / "proc"
    _write_fdinfo(proc, 100, 9, _xe_client(1, cycles=0, total_cycles=0))
    _write_fdinfo(proc, 200, 9, _xe_client(2, cycles=0, total_cycles=0))
    probe = DrmEngineTimeProbe(proc_root=proc, drm_root=tmp_path / "drm")
    probe.read(now=10.0, pids=[100, 200])

    _write_fdinfo(proc, 100, 9, _xe_client(1, cycles=500, total_cycles=2_000))
    _write_fdinfo(proc, 200, 9, _xe_client(2, cycles=500, total_cycles=2_000))
    # Both clients share the same engine clock: 1000 busy of one 2000 total,
    # not of two summed totals.
    assert probe.read(now=12.0, pids=[100, 200])[0].utilization_percent == 50.0


def test_gpu_probe_reports_unknown_when_xe_total_cycles_do_not_advance(tmp_path: Path) -> None:
    proc = tmp_path / "proc"
    _write_fdinfo(proc, 100, 9, _xe_client(1, cycles=10, total_cycles=1_000))
    probe = DrmEngineTimeProbe(proc_root=proc, drm_root=tmp_path / "drm")
    probe.read(now=10.0, pids=[100])

    _write_fdinfo(proc, 100, 9, _xe_client(1, cycles=10, total_cycles=1_000))
    assert probe.read(now=12.0, pids=[100])[0].utilization_percent is None


def test_gpu_probe_ignores_malformed_cycle_values(tmp_path: Path) -> None:
    proc = tmp_path / "proc"
    body = (
        "drm-driver:\txe\n"
        "drm-client-id:\t1\n"
        "drm-pdev:\t0000:00:02.0\n"
        "drm-cycles-render:\tnotanumber\n"
        "drm-total-cycles-render:\t1000\n"
    )
    _write_fdinfo(proc, 100, 9, body)
    probe = DrmEngineTimeProbe(proc_root=proc, drm_root=tmp_path / "drm")

    assert probe.read(now=10.0, pids=[100]) == []


def test_gpu_probe_joining_client_only_establishes_a_baseline(tmp_path: Path) -> None:
    proc = tmp_path / "proc"
    _write_fdinfo(proc, 100, 9, _drm_client(1, render_ns=0, video_ns=0))
    probe = DrmEngineTimeProbe(proc_root=proc, drm_root=tmp_path / "drm")
    probe.read(now=10.0, pids=[100])

    # The retained client did 0.2 s of render in two seconds (10%). A second
    # client joins carrying 100 s of lifetime work; summing cumulative
    # counters first would report its whole history as this interval.
    _write_fdinfo(proc, 100, 9, _drm_client(1, render_ns=200_000_000, video_ns=0))
    _write_fdinfo(proc, 200, 9, _drm_client(2, render_ns=100_000_000_000, video_ns=0))
    assert probe.read(now=12.0, pids=[100, 200])[0].utilization_percent == 10.0


def test_gpu_probe_departing_client_does_not_subtract_from_the_rest(tmp_path: Path) -> None:
    proc = tmp_path / "proc"
    _write_fdinfo(proc, 100, 9, _drm_client(1, render_ns=0, video_ns=0))
    _write_fdinfo(proc, 200, 9, _drm_client(2, render_ns=100_000_000_000, video_ns=0))
    probe = DrmEngineTimeProbe(proc_root=proc, drm_root=tmp_path / "drm")
    probe.read(now=10.0, pids=[100, 200])

    _write_fdinfo(proc, 100, 9, _drm_client(1, render_ns=200_000_000, video_ns=0))
    assert probe.read(now=12.0, pids=[100])[0].utilization_percent == 10.0


def test_gpu_probe_rolled_back_xe_counters_do_not_recount_recovered_work(tmp_path: Path) -> None:
    # The DRM usage-stats spec permits counters to temporarily regress and
    # requires keeping the previous larger value until they catch up.
    proc = tmp_path / "proc"
    _write_fdinfo(proc, 100, 9, _xe_client(1, cycles=1_000, total_cycles=2_000))
    probe = DrmEngineTimeProbe(proc_root=proc, drm_root=tmp_path / "drm")
    probe.read(now=10.0, pids=[100])

    _write_fdinfo(proc, 100, 9, _xe_client(1, cycles=500, total_cycles=3_000))
    assert probe.read(now=12.0, pids=[100])[0].utilization_percent is None

    # Busy cycles recover to 1100: only 100 are new work above the retained
    # high-water mark, over a further 1000 total cycles.
    _write_fdinfo(proc, 100, 9, _xe_client(1, cycles=1_100, total_cycles=4_000))
    assert probe.read(now=14.0, pids=[100])[0].utilization_percent == 10.0


def test_gpu_probe_rolled_back_ns_counters_do_not_recount_recovered_work(tmp_path: Path) -> None:
    proc = tmp_path / "proc"
    _write_fdinfo(proc, 100, 9, _drm_client(1, render_ns=5_000_000_000, video_ns=0))
    probe = DrmEngineTimeProbe(proc_root=proc, drm_root=tmp_path / "drm")
    probe.read(now=10.0, pids=[100])

    _write_fdinfo(proc, 100, 9, _drm_client(1, render_ns=0, video_ns=0))
    assert probe.read(now=12.0, pids=[100])[0].utilization_percent == 0.0

    # 0.2 s of genuinely new work above the high-water mark, over the four
    # seconds since that mark was set.
    _write_fdinfo(proc, 100, 9, _drm_client(1, render_ns=5_200_000_000, video_ns=0))
    assert probe.read(now=14.0, pids=[100])[0].utilization_percent == 5.0


def test_gpu_probe_idle_samples_refresh_the_time_baseline(tmp_path: Path) -> None:
    # A counter sitting exactly at its high-water mark is caught up, so the
    # next busy interval is measured from the last idle sample, not from
    # whenever the mark was first set.
    proc = tmp_path / "proc"
    _write_fdinfo(proc, 100, 9, _drm_client(1, render_ns=0, video_ns=0))
    probe = DrmEngineTimeProbe(proc_root=proc, drm_root=tmp_path / "drm")
    probe.read(now=10.0, pids=[100])
    probe.read(now=12.0, pids=[100])

    _write_fdinfo(proc, 100, 9, _drm_client(1, render_ns=2_000_000_000, video_ns=0))
    assert probe.read(now=14.0, pids=[100])[0].utilization_percent == 100.0


def test_nvidia_gpu_is_named_and_declared_unreadable(tmp_path: Path) -> None:
    (tmp_path / "gpu0").mkdir(parents=True)
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
