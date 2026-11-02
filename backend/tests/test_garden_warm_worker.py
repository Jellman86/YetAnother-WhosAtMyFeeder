"""Warm Garden workers: real child processes, with fake models at the worker's inference boundary."""

import asyncio
import hashlib
import json
import os
from pathlib import Path
import textwrap

import numpy as np
from PIL import Image
import pytest

from app.repositories.garden_catalog import read_shipped_package
from app.services.garden_worker_supervisor import (
    GardenBusy,
    GardenCleanupFailed,
    GardenNativeWorkerFailed,
    GardenWarmWorker,
)

BACKEND = Path(__file__).resolve().parents[1]

SPECIESNET_CHILD = """
import os, signal, sys, time
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, {backend!r})
import numpy as np
from app.services import garden_worker

LOADS = Path(sys.argv[1])
if sys.argv[2:] == ["ignore-term"]:
    # A native runtime that does not honour SIGTERM; only SIGKILL stops it.
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
DEVICES = {{"cpu": "CPUExecutionProvider", "cuda": "CUDAExecutionProvider",
           "intel_cpu": "CPU", "intel_gpu": "GPU", "intel_npu": "NPU"}}


class Native:
    def __init__(self, model, provider):
        with LOADS.open("a") as loads:
            loads.write(f"{{os.getpid()}} {{provider}} {{model.name}}\\n")
        self.actual = [DEVICES[provider]]
        shape = [1, 480, 480, 3]
        if provider.startswith("intel_"):
            self.compiled = SimpleNamespace(input=lambda index: SimpleNamespace(shape=shape))
        else:
            self.session = SimpleNamespace(get_inputs=lambda: [SimpleNamespace(shape=shape, type="tensor(float)")])
        self.weights = np.random.default_rng(7).standard_normal((12, 2498)).astype(np.float32)

    def infer(self, value):
        pixels = value[0]
        red, green, blue = (float(pixels[:, :, c].mean()) for c in range(3))
        if red > 0.9 and green < 0.1:
            os.kill(os.getpid(), signal.SIGSEGV)
        if green > 0.9 and red < 0.1:
            LOADS.with_suffix(".running").touch()
            time.sleep(60)
        grey = pixels.mean(axis=2)
        features = np.array(
            [red, green, blue, *pixels.std(axis=(0, 1)), grey[:240, :240].mean(), grey[:240, 240:].mean(),
             grey[240:, :240].mean(), grey[240:, 240:].mean(), grey[120:360, 120:360].mean(), 1.0],
            dtype=np.float32,
        )
        return (features @ self.weights * np.float32(4))[None]


garden_worker.Runtime = Native
garden_worker.digest = lambda path: path.read_text().strip()
garden_worker.main()
"""

MOTION_CHILD = """
import hashlib, os, sys
from pathlib import Path
sys.path.insert(0, {backend!r})
import numpy as np
from app.services import garden_motion_worker as worker

LOADS = Path(sys.argv[1])
cv2 = worker.cv2


class Reader:
    def __init__(self, path, *args):
        data = Path(path).read_bytes()
        self.seed = int(hashlib.sha256(data).hexdigest()[:8], 16)
        self.scale = 0.1 if data.startswith(b"dark") else 1.0
        self.width, self.height = (5000, 4000) if data.startswith(b"huge") else (64, 48)
        self.index = 0

    def get(self, prop):
        return {{cv2.CAP_PROP_FRAME_WIDTH: self.width, cv2.CAP_PROP_FRAME_HEIGHT: self.height, cv2.CAP_PROP_FPS: 10,
                cv2.CAP_PROP_FRAME_COUNT: 50, cv2.CAP_PROP_POS_FRAMES: self.index + 1}}[prop]

    def set(self, prop, value):
        self.index = int(value / 100)

    def read(self):
        # A still scene with a visitor moving in its middle.
        pixels = np.random.default_rng(self.seed).integers(0, 255, (48, 64, 3), dtype=np.uint8)
        visitor = np.random.default_rng(self.seed + self.index).integers(0, 255, (16, 20, 3), dtype=np.uint8)
        pixels[16:32, 22:42] = visitor
        return True, (pixels * self.scale).astype(np.uint8)

    def release(self):
        pass


class Detector:
    actual = ["CPUExecutionProvider"]

    def __init__(self, model, provider):
        with LOADS.open("a") as loads:
            loads.write(f"{{os.getpid()}} {{provider}} {{model.name}}\\n")

    def infer(self, tensor):
        mean = float(tensor.mean())
        output = np.zeros((1, 7, 1), dtype=np.float32)
        output[0, :, 0] = [320, 320, 200 * mean + 50, 150 * mean + 40, min(0.99, 0.3 + mean), 0.0, 0.0]
        return output


real_digest = worker.digest
worker.digest = lambda path: path.read_text().strip() if path.suffix == ".onnx" else real_digest(path)
worker.Runtime = Detector
cv2.VideoCapture = Reader
worker.main()
"""


def child(tmp_path: Path, source: str, name: str) -> tuple[tuple[str, ...], Path]:
    script = tmp_path / f"{name}.py"
    script.write_text(textwrap.dedent(source.format(backend=str(BACKEND))))
    loads = tmp_path / f"{name}.loads"
    loads.touch()
    return (str(script), str(loads)), loads


def load_lines(loads: Path) -> list[str]:
    return loads.read_text().splitlines()


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # A zombie still answers signal 0; it is no longer running.
    status = Path(f"/proc/{pid}/stat")
    return not status.exists() or status.read_text().split(")")[-1].split()[0] != "Z"


@pytest.fixture
def speciesnet(tmp_path):
    _, package_sha = read_shipped_package()
    package = json.loads(read_shipped_package()[0])
    model_sha = package["model_sha256"]["4.0.3a"]
    model = tmp_path / "speciesnet-4.0.3a.onnx"
    model.write_text(model_sha)
    launch_args, loads = child(tmp_path, SPECIESNET_CHILD, "speciesnet")
    workers: list[GardenWarmWorker] = []

    def make(*, resistant: bool = False, **options) -> GardenWarmWorker:
        options = {"release": lambda: False, "on_stuck": lambda: None, **options}
        arguments = launch_args + (("ignore-term",) if resistant else ())
        worker = GardenWarmWorker("garden_worker", b"GARDEN_RESULT:", launch_args=arguments, **options)
        workers.append(worker)
        return worker

    def image(name: str, colour=None, seed: int = 0) -> str:
        path = tmp_path / f"{name}.png"
        if colour is None:
            pixels = np.random.default_rng(seed).integers(0, 255, (96, 128, 3), dtype=np.uint8)
            Image.fromarray(pixels).save(path)
        else:
            Image.new("RGB", (96, 64), colour).save(path)
        return str(path)

    def request(path: str, mode: str = "automatic", provider: str = "cpu", box=(0.1, 0.2, 0.5, 0.6), **extra):
        return {
            "mode": mode,
            "variant": "4.0.3a",
            "model": str(model),
            "model_sha256": model_sha,
            "package_sha256": package_sha,
            "provider": provider,
            "box": list(box),
            "image": path,
            **extra,
        }

    yield type("SpeciesNet", (), {"make": make, "image": image, "request": request, "loads": loads, "tmp": tmp_path})
    for worker in workers:
        await_stop(worker)


def await_stop(worker: GardenWarmWorker) -> None:
    process = worker._process
    if process is not None and process.returncode is None:
        process.kill()


async def reap(*processes) -> None:
    for process in processes:
        process.kill()
        await process.wait()
        process.stdin.close()


def key(request: dict) -> tuple:
    return (request["model"], request["model_sha256"], request["variant"], request["provider"])


async def run(worker: GardenWarmWorker, request: dict, blocked=lambda: False, timeout_seconds: float = 30) -> dict:
    return await worker.request(key(request), request, blocked, timeout_seconds=timeout_seconds, poll_seconds=0.01)


@pytest.mark.asyncio
async def test_a_warm_worker_loads_its_model_once_then_serves_every_request(speciesnet):
    worker = speciesnet.make()
    requests = [speciesnet.request(speciesnet.image(f"photo-{i}", seed=i)) for i in range(5)]
    results = [await run(worker, request) for request in requests]
    loads = load_lines(speciesnet.loads)
    assert len(loads) == 1 and loads[0].split()[1] == "cpu"
    assert int(loads[0].split()[0]) == worker.pid
    assert all(result["devices"] == ["CPUExecutionProvider"] for result in results)
    # Each request carries its own photo, so the warm model answers each one separately.
    assert len({json.dumps(result["assessment"], sort_keys=True) for result in results}) == 5
    await worker.stop()
    assert worker.pid is None


@pytest.mark.asyncio
async def test_warm_results_are_identical_to_one_fresh_process_per_request(speciesnet):
    photos = [speciesnet.image(f"photo-{i}", seed=i) for i in range(3)]
    requests = [
        speciesnet.request(photos[0], mode="preview"),
        speciesnet.request(photos[1], validation_probe=True),
        speciesnet.request(photos[0], box=(0.0, 0.0, 1.0, 1.0)),
        speciesnet.request(photos[2], mode="identify", box=(0.25, 0.25, 0.5, 0.5)),
        speciesnet.request(photos[1], mode="preview", box=(0.3, 0.1, 0.4, 0.8)),
    ]
    warm = speciesnet.make()
    warm_results = [await run(warm, request) for request in requests]
    await warm.stop()
    assert len(load_lines(speciesnet.loads)) == 1
    cold_results = []
    for request in requests:
        cold = speciesnet.make()
        cold_results.append(await run(cold, request))
        await cold.stop()
    assert len(load_lines(speciesnet.loads)) == 1 + len(requests)
    assert warm_results == cold_results
    # The comparison is not vacuous: validation probes carry every probability, within the bound.
    assert len(warm_results[1]["probabilities"]) == 2498
    assert "preview" in warm_results[0] and "predictions" in warm_results[3]


@pytest.mark.asyncio
async def test_a_different_provider_or_model_never_shares_the_loaded_worker(speciesnet):
    worker = speciesnet.make()
    photo = speciesnet.image("photo", seed=1)
    cpu = await run(worker, speciesnet.request(photo))
    first = worker.pid
    npu = await run(worker, speciesnet.request(photo, provider="intel_npu"))
    second = worker.pid
    again = await run(worker, speciesnet.request(photo))
    assert cpu["devices"] == ["CPUExecutionProvider"] and npu["devices"] == ["NPU"]
    assert again == cpu
    assert len({first, second, worker.pid}) == 3 and not alive(first) and not alive(second)
    assert [line.split()[1] for line in load_lines(speciesnet.loads)] == ["cpu", "intel_npu", "cpu"]
    other = speciesnet.tmp / "speciesnet-4.0.3a-other.onnx"
    other.write_text((speciesnet.tmp / "speciesnet-4.0.3a.onnx").read_text())
    await run(worker, speciesnet.request(photo) | {"model": str(other)})
    assert len(load_lines(speciesnet.loads)) == 4
    await worker.stop()


@pytest.mark.asyncio
async def test_a_native_crash_surfaces_and_the_next_request_starts_a_fresh_worker(speciesnet):
    worker = speciesnet.make()
    await run(worker, speciesnet.request(speciesnet.image("photo", seed=1)))
    crashed = worker.pid
    with pytest.raises(GardenNativeWorkerFailed) as failure:
        await run(worker, speciesnet.request(speciesnet.image("red", colour="red")))
    assert failure.value.signal_name == "SIGSEGV" and worker.pid is None and not alive(crashed)
    await run(worker, speciesnet.request(speciesnet.image("photo", seed=1)))
    assert worker.pid != crashed and len(load_lines(speciesnet.loads)) == 2
    await worker.stop()


@pytest.mark.asyncio
async def test_a_python_error_is_named_and_replaces_the_worker(speciesnet):
    worker = speciesnet.make()
    with pytest.raises(GardenNativeWorkerFailed) as failure:
        await run(worker, speciesnet.request(speciesnet.image("photo", seed=1), box=(0.5, 0.5, 0.9, 0.9)))
    assert failure.value.exit_code == 1 and failure.value.error_type == "ValueError"
    assert worker.pid is None


@pytest.mark.asyncio
async def test_an_oversized_request_is_refused_by_the_worker(speciesnet):
    worker = speciesnet.make()
    request = speciesnet.request(speciesnet.image("photo", seed=1), padding="x" * 9000)
    with pytest.raises(GardenNativeWorkerFailed) as failure:
        await run(worker, request)
    assert failure.value.error_type == "ValueError" and worker.pid is None


@pytest.mark.asyncio
async def test_bird_preemption_kills_the_warm_worker_mid_request(speciesnet):
    worker = speciesnet.make()
    await run(worker, speciesnet.request(speciesnet.image("photo", seed=1)))
    busy = worker.pid
    running = speciesnet.loads.with_suffix(".running")
    with pytest.raises(GardenBusy):
        await run(worker, speciesnet.request(speciesnet.image("green", colour="lime")), blocked=running.exists)
    assert worker.pid is None and not alive(busy)
    await run(worker, speciesnet.request(speciesnet.image("photo", seed=1)))
    assert worker.pid != busy
    await worker.stop()


@pytest.mark.asyncio
async def test_a_deadline_kills_the_warm_worker(speciesnet):
    worker = speciesnet.make()
    request = speciesnet.request(speciesnet.image("green", colour="lime"))
    with pytest.raises(TimeoutError):
        await worker.request(key(request), request, lambda: False, timeout_seconds=3, poll_seconds=0.01)
    assert worker.pid is None
    assert len(load_lines(speciesnet.loads)) == 1


@pytest.mark.asyncio
async def test_cancellation_leaves_no_child_process_running(speciesnet):
    worker = speciesnet.make()
    await run(worker, speciesnet.request(speciesnet.image("photo", seed=1)))
    pid = worker.pid
    running = speciesnet.loads.with_suffix(".running")
    task = asyncio.create_task(run(worker, speciesnet.request(speciesnet.image("green", colour="lime"))))
    while not running.exists():
        await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert worker.pid is None and not alive(pid)


@pytest.mark.asyncio
async def test_an_idle_worker_is_released_after_its_timeout(speciesnet):
    worker = speciesnet.make(idle_seconds=0.3, poll_seconds=0.05)
    await run(worker, speciesnet.request(speciesnet.image("photo", seed=1)))
    pid = worker.pid
    await asyncio.sleep(0.1)
    assert alive(pid)
    for _ in range(100):
        if worker.pid is None:
            break
        await asyncio.sleep(0.05)
    assert worker.pid is None and not alive(pid)
    await run(worker, speciesnet.request(speciesnet.image("photo", seed=1)))
    assert len(load_lines(speciesnet.loads)) == 2
    await worker.stop()


@pytest.mark.asyncio
async def test_pending_bird_work_releases_an_idle_worker_at_once(speciesnet):
    birds = {"pending": False}
    worker = speciesnet.make(release=lambda: birds["pending"], idle_seconds=600, poll_seconds=0.05)
    await run(worker, speciesnet.request(speciesnet.image("photo", seed=1)))
    pid = worker.pid
    await asyncio.sleep(0.2)
    assert worker.pid == pid
    birds["pending"] = True
    for _ in range(100):
        if worker.pid is None:
            break
        await asyncio.sleep(0.05)
    assert worker.pid is None and not alive(pid)


@pytest.mark.asyncio
async def test_shutdown_during_idle_release_still_kills_a_child_that_ignores_sigterm(speciesnet):
    worker = speciesnet.make(resistant=True, idle_seconds=0.1, poll_seconds=0.02)
    await run(worker, speciesnet.request(speciesnet.image("photo", seed=1)))
    pid = worker.pid
    # The idle release has sent SIGTERM and is waiting out its grace period.
    await asyncio.sleep(0.5)
    assert alive(pid)
    await worker.stop()
    assert not alive(pid) and worker.pid is None


@pytest.mark.asyncio
async def test_cancelling_a_binding_change_still_reaps_the_old_child(speciesnet):
    worker = speciesnet.make(resistant=True)
    photo = speciesnet.image("photo", seed=1)
    await run(worker, speciesnet.request(photo))
    cpu = worker.pid
    task = asyncio.create_task(run(worker, speciesnet.request(photo, provider="intel_npu")))
    # The CPU worker is being retired for the accelerator binding and ignores SIGTERM.
    await asyncio.sleep(0.5)
    assert alive(cpu)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not alive(cpu) and worker.pid is None
    assert len(load_lines(speciesnet.loads)) == 1


@pytest.mark.asyncio
async def test_a_failed_reap_keeps_ownership_so_shutdown_tries_again(speciesnet, monkeypatch):
    from app.services import garden_worker_supervisor as supervisor

    worker = speciesnet.make()
    await run(worker, speciesnet.request(speciesnet.image("photo", seed=1)))
    pid = worker.pid
    real_stop = supervisor.stop_worker
    attempts = []

    async def fails_once(process):
        attempts.append(process.pid)
        if len(attempts) == 1:
            raise GardenCleanupFailed("Garden worker did not stop")
        await real_stop(process)

    monkeypatch.setattr(supervisor, "stop_worker", fails_once)
    with pytest.raises(GardenCleanupFailed):
        await worker.retire("test")
    assert worker.stuck and worker.pid == pid
    await worker.stop()
    assert attempts == [pid, pid] and not alive(pid) and worker.pid is None


@pytest.mark.asyncio
async def test_a_worker_is_recycled_after_its_request_limit(speciesnet):
    worker = speciesnet.make(max_requests=2)
    photo = speciesnet.image("photo", seed=1)
    first = [await run(worker, speciesnet.request(photo)) for _ in range(2)]
    assert worker.pid is None
    third = await run(worker, speciesnet.request(photo))
    assert first[0] == first[1] == third
    assert len(load_lines(speciesnet.loads)) == 2
    await worker.stop()


@pytest.mark.asyncio
async def test_unreadable_bird_state_releases_the_worker(speciesnet):
    def unreadable() -> bool:
        raise RuntimeError("admission status unavailable")

    worker = speciesnet.make(release=unreadable, idle_seconds=600, poll_seconds=0.05)
    await run(worker, speciesnet.request(speciesnet.image("photo", seed=1)))
    for _ in range(100):
        if worker.pid is None:
            break
        await asyncio.sleep(0.05)
    assert worker.pid is None


@pytest.mark.asyncio
async def test_an_idle_worker_that_will_not_stop_reports_through_on_stuck(speciesnet, monkeypatch):
    from app.services import garden_worker_supervisor as supervisor

    stuck = []
    worker = speciesnet.make(idle_seconds=0.1, poll_seconds=0.02, on_stuck=lambda: stuck.append(True))
    await run(worker, speciesnet.request(speciesnet.image("photo", seed=1)))
    process = worker._process

    async def will_not_stop(_process):
        raise GardenCleanupFailed("Garden worker did not stop")

    monkeypatch.setattr(supervisor, "stop_worker", will_not_stop)
    for _ in range(100):
        if stuck:
            break
        await asyncio.sleep(0.02)
    assert stuck == [True] and worker.stuck
    with pytest.raises(GardenCleanupFailed):
        await run(worker, speciesnet.request(speciesnet.image("photo", seed=1)))
    await reap(process)


@pytest.mark.asyncio
async def test_a_failed_stop_after_a_request_raises_cleanup_failed(speciesnet, monkeypatch):
    from app.services import garden_worker_supervisor as supervisor

    left_running = []

    async def will_not_stop(process):
        left_running.append(process)
        raise GardenCleanupFailed("Garden worker did not stop")

    monkeypatch.setattr(supervisor, "stop_worker", will_not_stop)
    worker = speciesnet.make()
    request = speciesnet.request(speciesnet.image("green", colour="lime"))
    with pytest.raises(GardenCleanupFailed):
        await worker.request(key(request), request, lambda: True, timeout_seconds=30, poll_seconds=0.01)
    assert worker.stuck
    await reap(*left_running)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("reply", "error"),
    [
        ("sys.stdout.write('GARDEN_RESULT:' + json.dumps({'pad': 'x' * 70000}) + '\\n')", "exceeded its bound"),
        ("sys.stdout.write('GARDEN_RESULT:[1, 2]\\n')", "Invalid garden worker result"),
        ("sys.stdout.write('SOMETHING_ELSE:{}\\n')", "no valid result"),
        ("sys.stdout.write('GARDEN_RESULT:{not json\\n')", None),
        ("sys.exit(0)", "no valid result"),
    ],
)
async def test_malformed_or_oversized_output_is_rejected_and_the_worker_replaced(tmp_path, reply, error):
    script = tmp_path / "echo.py"
    script.write_text(
        f"import json, sys, time\nfor line in sys.stdin:\n    {reply}\n    sys.stdout.flush()\n    time.sleep(60)\n"
    )
    worker = GardenWarmWorker(
        "echo", b"GARDEN_RESULT:", release=lambda: False, on_stuck=lambda: None, launch_args=(str(script),)
    )
    with pytest.raises(ValueError, match=error):
        await worker.request("key", {}, lambda: False, timeout_seconds=10, poll_seconds=0.01)
    assert worker.pid is None


@pytest.mark.asyncio
async def test_a_result_just_under_the_bound_is_accepted(tmp_path):
    script = tmp_path / "echo.py"
    script.write_text(
        "import json, sys\n"
        "for line in sys.stdin:\n"
        "    sys.stdout.write('GARDEN_RESULT:' + json.dumps({'pad': 'x' * 65000}) + '\\n')\n"
        "    sys.stdout.flush()\n"
    )
    worker = GardenWarmWorker(
        "echo", b"GARDEN_RESULT:", release=lambda: False, on_stuck=lambda: None, launch_args=(str(script),)
    )
    assert len((await worker.request("key", {}, lambda: False, timeout_seconds=10))["pad"]) == 65000
    await worker.stop()


@pytest.fixture
def motion(tmp_path):
    launch_args, loads = child(tmp_path, MOTION_CHILD, "motion")
    model = tmp_path / "cedar.onnx"
    model.write_text("e" * 64)
    workers: list[GardenWarmWorker] = []

    def make() -> GardenWarmWorker:
        worker = GardenWarmWorker(
            "garden_motion_worker",
            b"MOTION_RESULT:",
            release=lambda: False,
            on_stuck=lambda: None,
            launch_args=launch_args,
        )
        workers.append(worker)
        return worker

    def request(name: str, content: bytes) -> dict:
        folder = tmp_path / name
        folder.mkdir(exist_ok=True)
        clip = folder / "clip.mp4"
        clip.write_bytes(content)
        (folder / "photo.jpg").unlink(missing_ok=True)
        return {
            "model": str(model),
            "clip": str(clip),
            "photo": str(folder / "photo.jpg"),
            "duration": 5.0,
            "clip_sha256": hashlib.sha256(content).hexdigest(),
            "model_sha256": "e" * 64,
            "names": ["animal", "person", "vehicle"],
            "animal_confidence": 0.5,
        }

    yield type("Motion", (), {"make": make, "request": request, "loads": loads})
    for worker in workers:
        await_stop(worker)


@pytest.mark.asyncio
async def test_warm_motion_scans_match_one_fresh_process_per_scan(motion):
    clips = [(f"clip-{i}", f"recording {i}".encode()) for i in range(3)] + [("dark", b"dark recording")]
    warm = motion.make()
    warm_results = []
    for name, content in clips:
        request = motion.request(name, content)
        warm_results.append(await warm.request(("cedar",), request, lambda: False, timeout_seconds=30))
    assert len(load_lines(motion.loads)) == 1
    await warm.stop()
    cold_results = []
    for name, content in clips:
        cold = motion.make()
        request = motion.request(name, content)
        cold_results.append(await cold.request(("cedar",), request, lambda: False, timeout_seconds=30))
        await cold.stop()
    assert len(load_lines(motion.loads)) == 1 + len(clips)
    assert warm_results == cold_results
    assert [result["outcome"] for result in warm_results] == ["candidate"] * 3 + ["no_candidate"]
    assert len({result["image_sha256"] for result in warm_results[:3]}) == 3


@pytest.mark.asyncio
async def test_an_unusable_recording_is_a_result_and_keeps_the_motion_worker(motion):
    worker = motion.make()
    good = motion.request("clip", b"recording")
    await worker.request(("cedar",), good, lambda: False, timeout_seconds=30)
    pid = worker.pid
    huge = motion.request("huge", b"huge recording")
    result = await worker.request(("cedar",), huge, lambda: False, timeout_seconds=30)
    assert result == {"outcome": "unusable_recording", "reason": "pixel_limit"}
    assert worker.pid == pid
    await worker.stop()
