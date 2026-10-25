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


def test_drm_diagnostics_explain_frozen_cycles_and_keep_only_safe_fields(tmp_path: Path) -> None:
    from dataclasses import asdict
    import json

    _write_fdinfo(tmp_path, 100, 9, _xe_client(1, cycles=10, total_cycles=1000) + "secret: PRIVATE_TOKEN\n")
    probe = DrmEngineTimeProbe(proc_root=tmp_path)
    probe.read(now=10.0, pids=[100])
    assert probe.diagnostics.new_clients == 1
    assert probe.diagnostics.counters[0].state == "baseline"
    probe.read(now=12.0, pids=[100])
    diagnostic = probe.diagnostics
    assert diagnostic.parsed_clients == 1
    assert diagnostic.fdinfo_reads == 1
    assert diagnostic.counters[0].state == "total_not_advancing"
    assert diagnostic.counters[0].value == 10
    assert diagnostic.counters[0].previous == 10
    assert diagnostic.counters[0].total == 1000
    assert diagnostic.counters[0].previous_total == 1000
    assert "PRIVATE_TOKEN" not in json.dumps(asdict(diagnostic))


def test_drm_diagnostics_report_missing_process_and_client_turnover(tmp_path: Path) -> None:
    _write_fdinfo(tmp_path, 100, 9, _drm_client(1, render_ns=0, video_ns=0))
    probe = DrmEngineTimeProbe(proc_root=tmp_path)
    probe.read(now=10.0, pids=[100])
    _write_fdinfo(tmp_path, 100, 9, _drm_client(2, render_ns=0, video_ns=0))
    probe.read(now=12.0, pids=[100, 200])
    assert probe.diagnostics.new_clients == 1
    assert probe.diagnostics.departed_clients == 1
    assert probe.diagnostics.missing_processes == 1
    assert all(counter.state == "baseline" for counter in probe.diagnostics.counters)


def test_drm_diagnostics_are_bounded_and_allowlist_counter_identity(tmp_path: Path) -> None:
    from dataclasses import asdict
    import json

    for fd in range(40):
        body = (
            _drm_client(fd, render_ns=0, video_ns=0)
            .replace("i915", "PRIVATE_DRIVER")
            .replace("0000:00:02.0", "PRIVATE_DEVICE")
            .replace("render", "PRIVATE_ENGINE")
        )
        _write_fdinfo(tmp_path, 100, fd, body)
    probe = DrmEngineTimeProbe(proc_root=tmp_path)
    probe.read(now=10.0, pids=[100])
    assert len(probe.diagnostics.counters) == 64
    assert probe.diagnostics.omitted_counters == 16
    assert "PRIVATE" not in json.dumps(asdict(probe.diagnostics))


def test_drm_diagnostics_count_denied_reads_without_exception_text(tmp_path: Path, monkeypatch) -> None:
    _write_fdinfo(tmp_path, 100, 9, _drm_client(1, render_ns=0, video_ns=0))

    def denied(*args, **kwargs):
        raise PermissionError("PRIVATE_PATH")

    monkeypatch.setattr(Path, "read_text", denied)
    probe = DrmEngineTimeProbe(proc_root=tmp_path)
    assert probe.read(now=10.0, pids=[100]) == []
    assert probe.diagnostics.permission_denied == 1
    assert probe.diagnostics.fdinfo_reads == 0


def test_drm_diagnostics_identify_driver_without_supported_counters(tmp_path: Path) -> None:
    _write_fdinfo(tmp_path, 100, 9, "drm-driver: xe\ndrm-client-id: 1\n")
    probe = DrmEngineTimeProbe(proc_root=tmp_path)
    assert probe.read(now=1.0, pids=[100]) == []
    assert probe.diagnostics.drivers == ("xe",)
    assert probe.diagnostics.unsupported_fdinfo == 1
    probe.read(now=2.0, pids=[])
    assert probe.diagnostics.drivers == ()
    assert probe.diagnostics.process_count == 0


def test_drm_diagnostics_distinguish_missing_total_regression_and_measurement(tmp_path: Path) -> None:
    probe = DrmEngineTimeProbe(proc_root=tmp_path)
    _write_fdinfo(
        tmp_path, 100, 9, _xe_client(1, cycles=10, total_cycles=100).replace("drm-total-cycles-render:\t100\n", "")
    )
    probe.read(now=1.0, pids=[100])
    assert probe.diagnostics.counters[0].state == "missing_total"
    _write_fdinfo(tmp_path, 100, 9, _xe_client(1, cycles=10, total_cycles=100))
    probe.read(now=2.0, pids=[100])
    assert probe.diagnostics.counters[0].state == "baseline"
    _write_fdinfo(tmp_path, 100, 9, _xe_client(1, cycles=20, total_cycles=200))
    assert probe.read(now=3.0, pids=[100])[0].utilization_percent == 10.0
    assert probe.diagnostics.counters[0].state == "measured"
    assert probe.diagnostics.counters[0].elapsed_seconds == 1.0
    _write_fdinfo(tmp_path, 100, 9, _xe_client(1, cycles=5, total_cycles=50))
    probe.read(now=4.0, pids=[100])
    assert probe.diagnostics.counters[0].state == "counter_regressed"


def test_gpu_probe_recovers_after_reported_xe_total_clock_rollover(tmp_path: Path) -> None:
    # Sanitized counters from #778: busy cycles remain cumulative while the
    # hardware timestamp wraps near 2**36. Its old high-water never catches up.
    proc = tmp_path / "proc"
    probe = DrmEngineTimeProbe(proc_root=proc, drm_root=tmp_path / "drm")
    _write_fdinfo(proc, 100, 9, _xe_client(1, cycles=116_100_017, total_cycles=68_706_428_536))
    probe.read(now=10.0, pids=[100])
    _write_fdinfo(proc, 100, 9, _xe_client(1, cycles=117_290_788, total_cycles=9_711_283_593))
    assert probe.read(now=15.0, pids=[100])[0].utilization_percent is None
    assert probe.diagnostics.counters[0].state == "counter_regressed"

    _write_fdinfo(proc, 100, 9, _xe_client(1, cycles=117_290_788, total_cycles=9_807_446_444))
    assert probe.read(now=20.0, pids=[100])[0].utilization_percent == 0.0
    assert probe.diagnostics.counters[0].state == "measured"
    assert probe.diagnostics.counters[0].previous_total == 9_711_283_593

    _write_fdinfo(proc, 100, 9, _xe_client(1, cycles=127_290_788, total_cycles=9_907_446_444))
    assert probe.read(now=25.0, pids=[100])[0].utilization_percent == 10.0


def test_gpu_probe_rebaselines_total_clock_without_resetting_busy_high_water(tmp_path: Path) -> None:
    proc = tmp_path / "proc"
    probe = DrmEngineTimeProbe(proc_root=proc, drm_root=tmp_path / "drm")
    _write_fdinfo(proc, 100, 9, _xe_client(1, cycles=100, total_cycles=1000))
    probe.read(now=10.0, pids=[100])
    _write_fdinfo(proc, 100, 9, _xe_client(1, cycles=50, total_cycles=10))
    assert probe.read(now=15.0, pids=[100])[0].utilization_percent is None
    _write_fdinfo(proc, 100, 9, _xe_client(1, cycles=100, total_cycles=110))
    assert probe.read(now=20.0, pids=[100])[0].utilization_percent == 0.0
    _write_fdinfo(proc, 100, 9, _xe_client(1, cycles=125, total_cycles=210))
    assert probe.read(now=25.0, pids=[100])[0].utilization_percent == 25.0


def test_gpu_probe_clock_rollover_keeps_other_clients_measured(tmp_path: Path) -> None:
    probe = DrmEngineTimeProbe(proc_root=tmp_path, drm_root=tmp_path / "drm")
    _write_fdinfo(tmp_path, 100, 9, _xe_client(1, cycles=1000, total_cycles=10000))
    _write_fdinfo(tmp_path, 200, 9, _xe_client(2, cycles=1000, total_cycles=100))
    probe.read(now=10.0, pids=[100, 200])
    _write_fdinfo(tmp_path, 100, 9, _xe_client(1, cycles=1100, total_cycles=10))
    _write_fdinfo(tmp_path, 200, 9, _xe_client(2, cycles=1020, total_cycles=200))
    assert probe.read(now=15.0, pids=[100, 200])[0].utilization_percent == 20.0
    _write_fdinfo(tmp_path, 100, 9, _xe_client(1, cycles=1110, total_cycles=1))
    _write_fdinfo(tmp_path, 200, 9, _xe_client(2, cycles=1030, total_cycles=1))
    assert probe.read(now=20.0, pids=[100, 200])[0].utilization_percent is None
    _write_fdinfo(tmp_path, 100, 9, _xe_client(1, cycles=1130, total_cycles=101))
    _write_fdinfo(tmp_path, 200, 9, _xe_client(2, cycles=1060, total_cycles=101))
    assert probe.read(now=25.0, pids=[100, 200])[0].utilization_percent == 50.0


def test_gpu_probe_recovers_after_each_total_clock_rollover(tmp_path: Path) -> None:
    probe = DrmEngineTimeProbe(proc_root=tmp_path, drm_root=tmp_path / "drm")
    cycles = 1000
    now = 10.0
    _write_fdinfo(tmp_path, 100, 9, _xe_client(1, cycles=cycles, total_cycles=2**36 - 10))
    probe.read(now=now, pids=[100])
    for _ in range(2):
        now += 5
        cycles += 30
        _write_fdinfo(tmp_path, 100, 9, _xe_client(1, cycles=cycles, total_cycles=5))
        assert probe.read(now=now, pids=[100])[0].utilization_percent is None
        now += 5
        cycles += 10
        _write_fdinfo(tmp_path, 100, 9, _xe_client(1, cycles=cycles, total_cycles=105))
        assert probe.read(now=now, pids=[100])[0].utilization_percent == 10.0
        now += 3500
        _write_fdinfo(tmp_path, 100, 9, _xe_client(1, cycles=cycles, total_cycles=2**36 - 10))
        probe.read(now=now, pids=[100])


def test_gpu_probe_xe_engine_names_and_busiest_engine_survive_clock_rollover(tmp_path: Path) -> None:
    probe = DrmEngineTimeProbe(proc_root=tmp_path, drm_root=tmp_path / "drm")
    engines = ["rcs", "bcs", "vcs", "vecs", "ccs"]

    def write(total: int, busy: list[int]) -> None:
        body = "drm-driver: xe\ndrm-client-id: 1\ndrm-pdev: 0000:00:02.0\n"
        for engine, value in zip(engines, busy, strict=True):
            body += f"drm-cycles-{engine}: {value}\ndrm-total-cycles-{engine}: {total}\n"
        body += f"drm-cycles-private-engine: 0\ndrm-total-cycles-private-engine: {total}\n"
        _write_fdinfo(tmp_path, 100, 9, body)

    write(2**36 - 10, [1000] * 5)
    probe.read(now=10.0, pids=[100])
    write(5, [1050] * 5)
    assert probe.read(now=15.0, pids=[100])[0].utilization_percent is None
    write(105, [1060, 1070, 1080, 1090, 1100])
    assert probe.read(now=20.0, pids=[100])[0].utilization_percent == 50.0
    assert {counter.engine for counter in probe.diagnostics.counters} == {*engines, "other"}
