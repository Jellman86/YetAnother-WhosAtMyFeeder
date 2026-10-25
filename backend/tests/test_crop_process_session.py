"""A native detector must never share the API process or survive its owner."""

import os
import sys
from pathlib import Path

import numpy as np
import pytest

from app.services.native_crash_quarantine import NativeCrashQuarantine


@pytest.fixture(autouse=True)
def child_module_path(monkeypatch):
    # Disposable script fixtures need the same import root as `python -m app`.
    backend = str(Path(__file__).resolve().parents[1])
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(filter(None, (backend, os.environ.get("PYTHONPATH")))))


@pytest.fixture
def child(tmp_path):
    script = tmp_path / "detector.py"
    script.write_text("""import json, os, sys, time
from app.services.crop_process_protocol import encode_array, decode_array, read_message, write_message
try:
 import resource
 resource.setrlimit(resource.RLIMIT_CORE,(0,0))
except ImportError: pass
request=read_message(sys.stdin.buffer)
mode=request['model_path']
if mode.endswith('startup-abort'): os.abort()
write_message(sys.stdout.buffer,{'ready':True,'inputs':[{'name':'images','shape':[1,3,2,2],'type':'tensor(float)'}],'outputs':[{'name':'boxes','shape':[1,4],'type':'tensor(float)'}],'providers':['OpenVINO:GPU']})
while True:
 request=read_message(sys.stdin.buffer)
 if mode.endswith('abort'): os.abort()
 if mode.endswith('slow'): time.sleep(20)
 if mode.endswith('paced'): time.sleep(.2)
 if mode.endswith('transient'):
  from pathlib import Path
  marker=Path(mode+'.once')
  if not marker.exists():
   marker.touch()
   time.sleep(20)
 if mode.endswith('error'):
  write_message(sys.stdout.buffer,{'error':'inference_failed','device_error':'CL_EXEC_STATUS_ERROR_FOR_EVENTS_IN_WAIT_LIST'})
  os._exit(3)
 value=decode_array(request['feeds']['images'])
 write_message(sys.stdout.buffer,{'outputs':[encode_array(value+1)]})
""")
    return [sys.executable, str(script)]


def session(tmp_path, child, name, **kwargs):
    from app.services.crop_process_session import CropProcessSession

    path = tmp_path / name
    path.write_bytes(b"test-owned artifact")
    provider = kwargs.pop("provider", "intel_gpu")
    profile = {
        "operation": "crop_detector",
        "model_id": name,
        "provider": provider,
        "runtime_signature": "test-runtime",
        "model_sha256": "a" * 64,
    }
    quarantine = NativeCrashQuarantine(lambda: profile, root=tmp_path / "incidents")
    return CropProcessSession(
        path, provider=provider, model_id=name, command=child, quarantine=quarantine, profile=profile, **kwargs
    )


def test_arrays_and_metadata_cross_process_without_changing_values(tmp_path, child):
    detector = session(tmp_path, child, "good")
    try:
        assert detector.pid != os.getpid()
        assert detector.get_inputs()[0].shape == [1, 3, 2, 2]
        value = np.zeros((1, 3, 2, 2), dtype=np.float32)
        assert np.array_equal(detector.run(None, {"images": value})[0], value + 1)
        assert detector.run(None, {"images": value})[0].dtype == value.dtype
    finally:
        detector.close()
    assert detector.exit_code is not None


@pytest.mark.parametrize("name", ["abort", "startup-abort"])
def test_native_abort_is_reaped_and_blocks_same_profile_relaunch(tmp_path, child, name):
    from app.services.crop_process_session import CropProcessError

    detector = None
    try:
        with pytest.raises(CropProcessError):
            detector = session(tmp_path, child, name)
            detector.run(None, {"images": np.zeros((1, 3, 2, 2), dtype=np.float32)})
        if detector:
            assert detector.exit_code is not None
        assert list((tmp_path / "incidents").glob("*.json"))
        with pytest.raises(Exception, match="quarantin"):
            session(tmp_path, child, name)
    finally:
        if detector:
            detector.close()


def test_device_error_retires_before_parent_can_fall_back(tmp_path, child):
    from app.services.crop_process_session import CropProcessError

    detector = session(tmp_path, child, "error")
    try:
        with pytest.raises(CropProcessError):
            detector.run(None, {"images": np.zeros((1, 3, 2, 2), dtype=np.float32)})
        assert detector.exit_code is not None
        assert list((tmp_path / "incidents").glob("*.json"))
    finally:
        detector.close()


def test_deadline_reaps_child_without_recording_native_crash(tmp_path, child):
    from app.services.crop_process_session import CropProcessError

    detector = session(tmp_path, child, "slow", inference_timeout=0.1)
    try:
        with pytest.raises(CropProcessError):
            detector.run(None, {"images": np.zeros((1, 3, 2, 2), dtype=np.float32)})
        assert detector.exit_code is not None
        assert not list((tmp_path / "incidents").glob("*.json"))
    finally:
        detector.close()


def test_protocol_rejects_object_arrays_and_oversized_headers_before_allocation():
    import base64
    from io import BytesIO
    from app.services.crop_process_protocol import decode_array, encode_array

    with pytest.raises(ValueError):
        encode_array(np.array([object()], dtype=object))
    stream = BytesIO()
    np.lib.format.write_array_header_1_0(stream, {"descr": "<f4", "fortran_order": False, "shape": (2**40,)})
    with pytest.raises(ValueError):
        decode_array(base64.b64encode(stream.getvalue()).decode())


def test_protocol_preserves_fortran_layout_values_and_rejects_trailing_data():
    import base64
    from app.services.crop_process_protocol import decode_array, encode_array

    value = np.asfortranarray(np.arange(12, dtype=np.float32).reshape(3, 4))
    encoded = encode_array(value)
    assert np.array_equal(decode_array(encoded), value)
    with pytest.raises(ValueError):
        decode_array(base64.b64encode(base64.b64decode(encoded) + b"extra").decode())


def test_native_model_loading_is_not_performed_by_the_api_service(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from app.services.bird_crop_service import BirdCropService

    calls = []

    class Proxy:
        def __init__(self, path, **options):
            calls.append((path, options))

        def get_inputs(self):
            return [SimpleNamespace(name="images", shape=[1, 3, 384, 384])]

        def get_outputs(self):
            return []

    service = BirdCropService(session_factory=Proxy)
    monkeypatch.setattr(service, "_import_onnxruntime", lambda: pytest.fail("API imported native detector runtime"))
    model = service._load_model_on_provider(
        tier="accurate", model_path=tmp_path / "model.onnx", model_config={}, provider="intel_gpu"
    )
    assert isinstance(model["session"], Proxy)
    assert calls[0][1]["provider"] == "intel_gpu"


def test_real_cpu_child_loads_and_runs_a_tiny_identity_model(tmp_path):
    import base64
    from app.services.crop_process_session import CropProcessSession

    # Generated Identity graph: float32 images -> boxes, static 1x3x2x2, opset 13.
    path = tmp_path / "identity.onnx"
    path.write_bytes(
        base64.b64decode(
            "CAg6bQoZCgZpbWFnZXMSBWJveGVzIghJZGVudGl0eRINY3JvcC1pZGVudGl0eVogCgZpbWFnZXMSFgoUCAESEAoCCAEKAggDCgIIAgoCCAJiHwoFYm94ZXMSFgoUCAESEAoCCAEKAggDCgIIAgoCCAJCBAoAEA0="
        )
    )
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("OMP_NUM_THREADS", "1")
        detector = CropProcessSession(path, provider="cpu", model_id="test-identity")
        try:
            value = np.arange(12, dtype=np.float32).reshape(1, 3, 2, 2)
            assert detector.get_providers()[0] == "CPUExecutionProvider"
            assert np.array_equal(detector.run(None, {"images": value})[0], value)
        finally:
            detector.close()


@pytest.mark.asyncio
async def test_unconfirmed_cleanup_blocks_every_new_detector_launch(tmp_path, child, monkeypatch):
    from types import SimpleNamespace
    from app.services import crop_process_session as module

    owner = SimpleNamespace(cleanup_failed=False, sessions=set(), accepting=True, unreaped=set())
    monkeypatch.setattr(module, "_runtime", lambda: owner)
    guard = NativeCrashQuarantine(lambda: {"provider": "intel_gpu"}, root=tmp_path / "guard")
    native = module._Session(tmp_path / "model", "cpu", child, {}, guard, 5, 1)

    import asyncio

    reaped = asyncio.Event()

    class Stuck:
        returncode = None
        waits = 0

        def terminate(self):
            pass

        def kill(self):
            pass

        async def wait(self):
            self.waits += 1
            if self.waits <= 3:
                raise TimeoutError()
            await reaped.wait()
            self.returncode = -9
            return self.returncode

    native.process = Stuck()
    with pytest.raises(module.CropProcessError, match="cleanup"):
        await native.close()
    assert owner.cleanup_failed
    next_session = module._Session(tmp_path / "model", "cpu", [], {}, guard, 1, 1)
    with pytest.raises(module.CropProcessError, match="cleanup"):
        await next_session.start()
    assert next_session.process is None
    reaped.set()
    await native.reap_task
    assert not owner.cleanup_failed
    assert native not in owner.sessions
    assert native not in owner.unreaped
    try:
        outputs = await native.infer({"images": np.zeros((1,), dtype=np.float32)})
        assert np.array_equal(outputs[0], [1])
        assert native.process.returncode is None
    finally:
        await native.dispose()


def test_startup_device_error_is_quarantined_before_cpu_can_start(tmp_path, child):
    from app.services.crop_process_session import CropProcessError

    script = tmp_path / "load_error.py"
    script.write_text("""import os, sys
from app.services.crop_process_protocol import read_message, write_message
read_message(sys.stdin.buffer)
write_message(sys.stdout.buffer, {'error':'inference_failed','device_error':'CL_DEVICE_NOT_AVAILABLE'})
os._exit(3)
""")
    with pytest.raises(CropProcessError):
        session(tmp_path, [sys.executable, str(script)], "load-error")
    assert list((tmp_path / "incidents").glob("*.json"))


def test_worker_retains_native_exception_until_immediate_exit(tmp_path, monkeypatch):
    from app.services.crop_process_session import CropProcessError

    script = tmp_path / "native_teardown.py"
    script.write_text("""import os
import resource
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
import sys
from contextlib import redirect_stdout
with redirect_stdout(sys.stderr):
 from app.services.bird_crop_service import BirdCropService
class NativeError(Exception):
 def __del__(self): os.abort()
def load(*args, **kwargs):
 try: raise NativeError('CL_DEVICE_NOT_AVAILABLE')
 except NativeError as error: raise RuntimeError('load failed') from error
BirdCropService._create_native_session=load
from app.services.crop_process_worker import main
main()
""")
    from app.services.crop_process_session import _Session

    exits = []
    original_close = _Session._close

    async def capture_close(self):
        await original_close(self)
        exits.append(self.process.returncode)

    monkeypatch.setattr(_Session, "_close", capture_close)
    with pytest.raises(CropProcessError):
        session(tmp_path, [sys.executable, str(script)], "destructor-error")
    import json

    incident = json.loads(next((tmp_path / "incidents").glob("*.json")).read_text())
    assert incident["retirement"]["error_code"] == "CL_DEVICE_NOT_AVAILABLE"
    assert exits == [3]


@pytest.mark.asyncio
async def test_owner_pipe_eof_terminates_worker_even_while_native_inference_is_hung(tmp_path):
    import asyncio
    from app.services.crop_process_protocol import message_bytes, parse_message

    script = tmp_path / "hung_native.py"
    script.write_text("""from types import SimpleNamespace
from pathlib import Path
import threading
import sys
from contextlib import redirect_stdout
with redirect_stdout(sys.stderr):
 from app.services.bird_crop_service import BirdCropService
class Native:
 def get_inputs(self): return [SimpleNamespace(name='images',shape=[1],type='tensor(float)')]
 def get_outputs(self): return [SimpleNamespace(name='boxes',shape=[1],type='tensor(float)')]
 def get_providers(self): return ['CPUExecutionProvider']
 def run(self,*args):
  Path(__file__).with_suffix('.running').touch()
  threading.Event().wait()
BirdCropService._create_native_session=lambda *args,**kwargs: Native()
from app.services.crop_process_worker import main
main()
""")
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        str(script),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        process.stdin.write(message_bytes({"model_path": "unused", "provider": "cpu"}))
        await process.stdin.drain()
        ready = parse_message(await asyncio.wait_for(process.stdout.readline(), 10))
        assert ready["ready"]
        process.stdin.write(message_bytes({"feeds": {}}))
        await process.stdin.drain()
        async with asyncio.timeout(5):
            while not script.with_suffix(".running").exists():
                await asyncio.sleep(0.01)
        process.stdin.close()
        assert await asyncio.wait_for(process.wait(), 3) == 0
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


@pytest.mark.asyncio
async def test_repeated_cancellation_reaps_child_before_returning(tmp_path, child):
    import asyncio
    from app.services.crop_process_session import _Session

    guard = NativeCrashQuarantine(lambda: {}, root=tmp_path / "incidents")
    detector = _Session(tmp_path / "slow", "intel_gpu", child, {}, guard, 5, 10)
    await detector.start()
    task = asyncio.create_task(detector.infer({"images": np.zeros((1, 3, 2, 2), dtype=np.float32)}))
    await asyncio.sleep(0.05)
    task.cancel()
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert detector.process.returncode is not None
    assert not list((tmp_path / "incidents").glob("*.json"))


@pytest.mark.asyncio
async def test_detector_facade_refuses_to_block_the_api_event_loop(tmp_path):
    from app.services.crop_process_session import CropProcessError, CropProcessSession

    with pytest.raises(CropProcessError, match="event loop"):
        CropProcessSession(tmp_path / "not-loaded", provider="cpu", model_id="unused")


def test_crop_fallback_uses_cpu_only_after_aborted_gpu_child_is_reaped(tmp_path, child, monkeypatch):
    from PIL import Image
    from app.services.bird_crop_service import BirdCropService

    gpu = session(tmp_path, child, "abort")
    cpu = None
    service = BirdCropService(model_loader=lambda: {"session": gpu, "provider": "intel_gpu"})
    monkeypatch.setattr(service, "_provider_for_tier", lambda tier: "intel_gpu")

    def replace(tier, *, failed_provider):
        nonlocal cpu
        assert gpu.exit_code is not None
        assert list((tmp_path / "incidents").glob("*.json"))
        cpu = session(tmp_path, child, "good")
        return {"session": cpu, "provider": "cpu"}

    def infer(model, image):
        model["session"].run(None, {"images": np.zeros((1, 3, 2, 2), dtype=np.float32)})
        return []

    monkeypatch.setattr(service, "_replace_tier_with_cpu", replace)
    monkeypatch.setattr(service, "_infer_candidates", infer)
    try:
        result, available = service._generate_crop_for_tier(Image.new("RGB", (64, 64)), "fast")
        assert available
        assert result["reason"] == "no_candidate"
    finally:
        gpu.close()
        if cpu is not None:
            cpu.close()


def test_reset_reaps_unused_child_but_keeps_a_live_model_reference(tmp_path, child):
    import gc
    from app.services.bird_crop_service import BirdCropService

    detector = session(tmp_path, child, "good")
    native = detector._session
    service = BirdCropService()
    model = {"session": detector}
    service._models["fast"] = model
    del detector
    service.reset_models()
    assert native.process.returncode is None  # An active crop caller still owns model.
    del model
    gc.collect()
    assert native.process.returncode is not None


@pytest.mark.parametrize(
    "metadata",
    [
        {"ready": True},
        {"ready": True, "inputs": [{"name": "x", "shape": [object()], "type": "tensor(float)"}]},
    ],
)
def test_protocol_rejects_unusable_worker_metadata(metadata):
    from app.services.crop_process_protocol import validate_metadata

    with pytest.raises(ValueError):
        validate_metadata(metadata)


def test_transient_timeout_reloads_cached_cpu_session_on_next_call(tmp_path, child):
    from app.services.crop_process_session import CropProcessError

    detector = session(tmp_path, child, "transient", provider="cpu", inference_timeout=0.1)
    try:
        original_pid = detector.pid
        with pytest.raises(CropProcessError):
            detector.run(None, {"images": np.zeros((1,), dtype=np.float32)})
        assert detector.exit_code is not None
        assert np.array_equal(detector.run(None, {"images": np.zeros((1,), dtype=np.float32)})[0], [1])
        assert detector.pid != original_pid
        assert not list((tmp_path / "incidents").glob("*.json"))
    finally:
        detector.close()


def test_queued_callers_receive_full_inference_deadline(tmp_path, child):
    from concurrent.futures import ThreadPoolExecutor

    detector = session(tmp_path, child, "paced", inference_timeout=0.5)
    try:
        with ThreadPoolExecutor(max_workers=4) as callers:
            values = list(
                callers.map(lambda _: detector.run(None, {"images": np.zeros((1,), dtype=np.float32)}), range(4))
            )
        assert len(values) == 4
        assert detector.exit_code is None
    finally:
        detector.close()


@pytest.mark.asyncio
async def test_expired_queue_wait_does_not_kill_active_inference(tmp_path, child):
    import asyncio
    from app.services.crop_process_session import _Session, CropProcessBusyError

    guard = NativeCrashQuarantine(lambda: {}, root=tmp_path / "incidents")
    detector = _Session(tmp_path / "paced", "cpu", child, {}, guard, 5, 1, queue_timeout=0.05)
    await detector.start()
    active = asyncio.create_task(detector.infer({"images": np.zeros((1,), dtype=np.float32)}))
    await asyncio.sleep(0.01)
    try:
        with pytest.raises(CropProcessBusyError):
            await detector.infer({"images": np.zeros((1,), dtype=np.float32)})
        assert np.array_equal((await active)[0], [1])
        assert detector.process.returncode is None
    finally:
        await detector.close()


@pytest.mark.asyncio
async def test_finalizer_on_api_loop_schedules_cleanup_without_blocking(tmp_path, child, monkeypatch):
    import asyncio
    import time
    from app.services.crop_process_session import _Session

    detector = await asyncio.to_thread(session, tmp_path, child, "good")
    native = detector._session
    original_close = _Session._close

    async def slow_close(self):
        await asyncio.sleep(0.2)
        await original_close(self)

    monkeypatch.setattr(_Session, "_close", slow_close)
    started = time.monotonic()
    detector.close()
    assert time.monotonic() - started < 0.1
    async with asyncio.timeout(3):
        while native.process.returncode is None:
            await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_shutdown_joins_a_child_whose_launch_is_still_pending(tmp_path, child, monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from app.services import crop_process_session as module

    owner = SimpleNamespace(cleanup_failed=False, sessions=set(), accepting=True, unreaped=set())
    monkeypatch.setattr(module, "_runtime", lambda: owner)
    original_launch = asyncio.create_subprocess_exec
    spawned = asyncio.Event()
    release = asyncio.Event()
    children = []

    async def delayed_launch(*args, **kwargs):
        process = await original_launch(*args, **kwargs)
        children.append(process)
        spawned.set()
        await release.wait()
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", delayed_launch)
    guard = NativeCrashQuarantine(lambda: {}, root=tmp_path / "incidents")
    detector = module._Session(tmp_path / "good", "cpu", child, {}, guard, 5, 1)
    starting = asyncio.create_task(detector.start())
    await spawned.wait()
    owner.accepting = False
    closing = asyncio.create_task(detector.dispose())
    await asyncio.sleep(0.01)
    assert not closing.done()
    release.set()
    await closing
    with pytest.raises(module.CropProcessError):
        await starting
    assert children[0].returncode is not None
    assert not owner.sessions


def test_failed_crop_child_exposes_cleanup_block_in_status(monkeypatch):
    from app.services.bird_crop_service import BirdCropService
    from app.services import crop_process_session as module

    monkeypatch.setattr(module, "crop_cleanup_pending", lambda: True)
    status = BirdCropService().get_status()
    assert not status["healthy"]
    assert status["reason"] == "runtime_cleanup_unconfirmed"
    assert "blocked until it exits" in status["load_error"]


@pytest.mark.skipif(sys.platform != "linux", reason="Linux kernel parent-death ownership")
@pytest.mark.asyncio
async def test_kernel_ownership_reaps_child_after_owner_dies_with_gil_held(tmp_path):
    import asyncio

    worker = tmp_path / "gil_native.py"
    worker.write_text("""import ctypes, sys
from contextlib import redirect_stdout
from types import SimpleNamespace
from pathlib import Path
with redirect_stdout(sys.stderr):
 from app.services.bird_crop_service import BirdCropService
class Native:
 def get_inputs(self): return [SimpleNamespace(name='images',shape=[1],type='tensor(float)')]
 def get_outputs(self): return [SimpleNamespace(name='boxes',shape=[1],type='tensor(float)')]
 def get_providers(self): return ['CPUExecutionProvider']
 def run(self,*args):
  Path(__file__).with_suffix('.running').touch()
  ctypes.PyDLL(None).sleep(30)
BirdCropService._create_native_session=lambda *args,**kwargs: Native()
from app.services.crop_process_worker import main
main()
""")
    owner = tmp_path / "owner.py"
    owner.write_text("""import os, subprocess, sys, time
from pathlib import Path
from app.services.crop_process_protocol import message_bytes, read_message
os.environ['YAWAMF_CROP_OWNER_PID']=str(os.getpid())
worker=Path(sys.argv[1])
p=subprocess.Popen([sys.executable,str(worker)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
p.stdin.write(message_bytes({'model_path':'unused','provider':'cpu'}));p.stdin.flush()
assert read_message(p.stdout)['ready']
p.stdin.write(message_bytes({'feeds':{}}));p.stdin.flush()
while not worker.with_suffix('.running').exists(): time.sleep(.01)
os._exit(0)
""")
    supervisor = tmp_path / "subreaper.py"
    supervisor.write_text("""import ctypes, os, signal, subprocess, sys, time
assert ctypes.CDLL(None).prctl(36,1,0,0,0)==0
p=subprocess.Popen([sys.executable,sys.argv[1],sys.argv[2]])
try:
 assert p.wait(timeout=10)==0
 deadline=time.monotonic()+3
 while time.monotonic()<deadline:
  pid,status=os.waitpid(-1,os.WNOHANG)
  if pid:
   assert os.waitstatus_to_exitcode(status)==-signal.SIGKILL
   break
  time.sleep(.01)
 else: raise AssertionError('native crop outlived its owner')
finally:
 if p.poll() is None: p.kill();p.wait()
 # This supervisor owns every descendant, even if the assertion failed.
 from pathlib import Path
 children=Path('/proc/self/task/'+str(os.getpid())+'/children').read_text().split()
 for child in children:
  try: os.kill(int(child),signal.SIGKILL)
  except ProcessLookupError: pass
 while True:
  try: os.waitpid(-1,0)
  except ChildProcessError: break
""")
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        str(supervisor),
        str(owner),
        str(worker),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, error = await asyncio.wait_for(process.communicate(), 16)
        assert process.returncode == 0, error.decode()
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
