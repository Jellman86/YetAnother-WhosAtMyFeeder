"""Automatic Garden accelerator evidence must be current and fail closed to CPU."""

import hashlib
from unittest.mock import AsyncMock

import pytest


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    from app.services import garden_automatic_runtime as module
    from app.config import settings

    monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(module, "get_image_flavor", lambda: "intel")
    monkeypatch.setattr(module, "current_inference_runtime_signature", lambda: "runtime-1")
    monkeypatch.setattr(settings.classification, "inference_provider", "intel_npu")
    model = tmp_path / "model.onnx"
    model.write_bytes(b"model")
    payload = dict(
        mode="automatic",
        variant="4.0.3a",
        model=str(model),
        model_sha256=hashlib.sha256(b"model").hexdigest(),
        package_sha256="a" * 64,
        box=[0.0, 0.0, 1.0, 1.0],
    )

    def reply(provider):
        return dict(
            devices={
                "cpu": ["CPUExecutionProvider"],
                "intel_npu": ["NPU"],
                "intel_gpu": ["GPU.0"],
                "cuda": ["CUDAExecutionProvider", "CPUExecutionProvider"],
            }[provider],
            probabilities=[0.9, 0.1] + [0.0] * 2496,
            assessment={
                "mass": {"bird": 0.0, "animal": 0.9, "human": 0.0, "non_animal": 0.1, "other": 0.0},
                "human_winner": False,
            },
            package_sha256=payload["package_sha256"],
            predictions=[[0, 0.9], [1, 0.1]],
        )

    async def run(image, request, blocked):
        return reply(request["provider"])

    worker = AsyncMock(side_effect=run)
    return module.GardenAutomaticRuntime(), worker, payload, module, reply


@pytest.mark.asyncio
@pytest.mark.parametrize("provider,flavor", [("intel_npu", "intel"), ("intel_gpu", "intel"), ("cuda", "cuda")])
async def test_accelerator_requires_cpu_agreement_then_reuses_only_current_profile(
    runtime, monkeypatch, provider, flavor
):
    service, worker, payload, module, _ = runtime
    monkeypatch.setattr(module.settings.classification, "inference_provider", provider)
    monkeypatch.setattr(module, "get_image_flavor", lambda: flavor)
    result, actual = await service.run(b"image", payload, lambda: False, worker)
    assert actual == provider and result["devices"][0] != "CPUExecutionProvider"
    assert [c.args[1]["provider"] for c in worker.call_args_list] == ["cpu", provider]
    await service.run(b"next", payload, lambda: False, worker)
    assert [c.args[1]["provider"] for c in worker.call_args_list] == ["cpu", provider, provider]
    monkeypatch.setattr(module, "current_inference_runtime_signature", lambda: "runtime-2")
    await service.run(b"next", payload, lambda: False, worker)
    assert [c.args[1]["provider"] for c in worker.call_args_list][-2:] == ["cpu", provider]


@pytest.mark.asyncio
async def test_unpackaged_device_uses_cpu_without_native_discovery(runtime, monkeypatch):
    service, worker, payload, module, _ = runtime
    monkeypatch.setattr(module, "get_image_flavor", lambda: "cpu")
    _, provider = await service.run(b"image", payload, lambda: False, worker)
    assert provider == "cpu" and worker.call_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["parity", "device", "nonfinite", "exception"])
async def test_failed_accelerator_stays_on_cpu_across_restart_and_package_change(runtime, failure):
    service, worker, payload, module, reply = runtime

    async def run(image, request, blocked):
        result = reply(request["provider"])
        result["package_sha256"] = request["package_sha256"]
        if request["provider"] != "cpu":
            if failure == "parity":
                result["probabilities"] = [0.1, 0.9] + [0.0] * 2496
            if failure == "device":
                result["devices"] = ["CPUExecutionProvider"]
            if failure == "nonfinite":
                result["probabilities"] = [float("nan"), 0.1]
            if failure == "exception":
                raise ValueError("native compile failed")
        return result

    worker.side_effect = run
    result, provider = await service.run(b"image", payload, lambda: False, worker)
    assert provider == "cpu" and result["devices"] == ["CPUExecutionProvider"]
    worker.reset_mock()
    replacement = module.GardenAutomaticRuntime()
    await replacement.run(b"image", payload | {"package_sha256": "b" * 64}, lambda: False, worker)
    assert [c.args[1]["provider"] for c in worker.call_args_list] == ["cpu"]


@pytest.mark.asyncio
async def test_unreaped_worker_never_starts_cpu_fallback(runtime):
    from app.services.garden_identification import GardenCleanupFailed

    service, worker, payload, _, reply = runtime

    async def run(image, request, blocked):
        if request["provider"] != "cpu":
            raise GardenCleanupFailed("unreaped")
        return reply("cpu")

    worker.side_effect = run
    with pytest.raises(GardenCleanupFailed):
        await service.run(b"image", payload, lambda: False, worker)
    assert worker.call_count == 2


@pytest.mark.asyncio
async def test_device_preference_change_during_check_cannot_authorize_old_profile(runtime, monkeypatch):
    from app.services.garden_identification import GardenBusy

    service, worker, payload, module, reply = runtime

    async def run(image, request, blocked):
        if request["provider"] != "cpu":
            monkeypatch.setattr(module.settings.classification, "inference_provider", "cpu")
        return reply(request["provider"])

    worker.side_effect = run
    with pytest.raises(GardenBusy):
        await service.run(b"image", payload, lambda: False, worker)


@pytest.mark.asyncio
async def test_auto_skips_a_failed_npu_profile_before_checking_igpu(runtime, monkeypatch):
    service, worker, payload, module, reply = runtime
    monkeypatch.setattr(module.settings.classification, "inference_provider", "auto")

    async def run(image, request, blocked):
        if request["provider"] == "intel_npu":
            raise ValueError("unsupported model")
        return reply(request["provider"])

    worker.side_effect = run
    _, provider = await service.run(b"image", payload, lambda: False, worker)
    assert provider == "cpu"
    _, provider = await service.run(b"image", payload, lambda: False, worker)
    assert provider == "intel_gpu"
    assert [c.args[1]["provider"] for c in worker.call_args_list] == ["cpu", "intel_npu", "cpu", "intel_gpu"]


@pytest.mark.asyncio
async def test_cpu_native_fault_is_quarantined_before_any_accelerator_is_started(runtime):
    from app.services.garden_identification import GardenNativeWorkerFailed
    from app.services.native_crash_quarantine import NativeCrashQuarantinedError

    service, worker, payload, module, _ = runtime
    worker.side_effect = GardenNativeWorkerFailed(-11)
    with pytest.raises(GardenNativeWorkerFailed):
        await service.run(b"image", payload, lambda: False, worker)
    worker.reset_mock()
    with pytest.raises(NativeCrashQuarantinedError):
        await module.GardenAutomaticRuntime().run(b"image", payload, lambda: False, worker)
    worker.assert_not_awaited()


@pytest.mark.asyncio
async def test_accelerator_native_fault_falls_back_after_cleanup_and_is_not_retried(runtime):
    from app.services.garden_identification import GardenNativeWorkerFailed

    service, worker, payload, module, reply = runtime

    async def run(image, request, blocked):
        if request["provider"] != "cpu":
            raise GardenNativeWorkerFailed(-11)
        return reply("cpu")

    worker.side_effect = run
    _, provider = await service.run(b"image", payload, lambda: False, worker)
    assert provider == "cpu"
    worker.reset_mock()
    await module.GardenAutomaticRuntime().run(b"image", payload, lambda: False, worker)
    assert [c.args[1]["provider"] for c in worker.call_args_list] == ["cpu"]


@pytest.mark.asyncio
async def test_reference_runtime_update_cannot_release_negative_accelerator_evidence(runtime, monkeypatch):
    service, worker, payload, module, reply = runtime

    async def run(image, request, blocked):
        if request["provider"] != "cpu":
            raise ValueError("unsupported accelerator")
        return reply("cpu")

    worker.side_effect = run
    await service.run(b"image", payload, lambda: False, worker)
    monkeypatch.setattr(module, "current_inference_runtime_signature", lambda: "changed-unrelated-runtime")
    worker.reset_mock()
    await module.GardenAutomaticRuntime().run(b"image", payload, lambda: False, worker)
    assert [c.args[1]["provider"] for c in worker.call_args_list] == ["cpu"]
