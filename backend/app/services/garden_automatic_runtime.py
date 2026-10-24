"""CPU-agreeing automatic Garden devices, bound to this host and exact artifacts."""

import asyncio
from collections import OrderedDict
from collections.abc import Awaitable, Callable
import hashlib
import json
import math
from typing import Any

from app.config import settings
from app.services.garden_identification import GardenBusy, GardenCleanupFailed, GardenNativeWorkerFailed
from app.services.garden_visitors import presence_outcome
from app.services.model_validation import current_inference_runtime_signature, current_provider_runtime_signature
from app.services.native_crash_quarantine import (
    NativeCrashQuarantine,
    NativeCrashQuarantinedError,
    artifact_digest,
)
from app.utils.runtime_flavor import get_image_flavor, packaged_inference_providers

Worker = Callable[[bytes, dict[str, Any], Callable[[], bool]], Awaitable[dict[str, Any]]]


def candidate_providers() -> tuple[str, ...]:
    packaged = packaged_inference_providers(get_image_flavor())
    selected = str(settings.classification.inference_provider).lower()
    if selected == "auto":
        return tuple(p for p in ("intel_npu", "intel_gpu", "cuda") if p in packaged) + ("cpu",)
    return (selected, "cpu") if selected in packaged and selected != "cpu" else ("cpu",)


def checked_result(native: dict[str, Any], payload: dict[str, Any], provider: str, *, probe: bool) -> None:
    expected = {
        "cpu": "CPUExecutionProvider",
        "intel_cpu": "CPU",
        "intel_gpu": "GPU",
        "intel_npu": "NPU",
        "cuda": "CUDAExecutionProvider",
    }[provider]
    devices = native.get("devices")
    if not isinstance(devices, list) or not devices or any(not isinstance(d, str) for d in devices):
        raise ValueError("Garden worker did not identify its execution device")
    if provider.startswith("intel_"):
        valid = all(d.split(".")[0] == expected for d in devices)
    else:
        valid = devices[0] == expected and all(d in {expected, "CPUExecutionProvider"} for d in devices)
    if not valid or native.get("package_sha256") != payload["package_sha256"]:
        raise ValueError("Garden worker runtime or mapping changed")
    assessment = native["assessment"]
    mass = assessment["mass"]
    values = [mass[k] for k in ("bird", "animal", "human", "non_animal", "other")]
    if (
        type(assessment["human_winner"]) is not bool
        or any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in values)
        or not math.isclose(sum(values), 1, abs_tol=1e-5)
    ):
        raise ValueError("Garden worker returned invalid presence evidence")
    if probe:
        probabilities = native.get("probabilities")
        if (
            not isinstance(probabilities, list)
            or len(probabilities) != 2498
            or any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in probabilities)
            or not math.isclose(sum(probabilities), 1, abs_tol=1e-5)
        ):
            raise ValueError("Garden device check returned invalid probabilities")


def agrees_with_cpu(baseline: dict[str, Any], candidate: dict[str, Any]) -> bool:
    first, second = baseline["assessment"], candidate["assessment"]
    if first["human_winner"] != second["human_winner"] or presence_outcome(
        first["mass"], first["human_winner"]
    ) != presence_outcome(second["mass"], second["human_winner"]):
        return False
    if max(abs(a - b) for a, b in zip(baseline["probabilities"], candidate["probabilities"], strict=True)) > 0.03:
        return False
    ordered = sorted(enumerate(baseline["probabilities"]), key=lambda v: v[1], reverse=True)
    return ordered[0][1] - ordered[1][1] < 0.05 or ordered[0][0] == max(
        range(2498), key=lambda i: candidate["probabilities"][i]
    )


class GardenAutomaticRuntime:
    def __init__(self) -> None:
        self._validated: OrderedDict[str, None] = OrderedDict()
        self.quarantine = NativeCrashQuarantine(lambda: {})

    async def _profile(self, payload: dict[str, Any], provider: str) -> dict[str, Any]:
        actual = await asyncio.to_thread(artifact_digest, payload["model"])
        if actual != payload["model_sha256"]:
            raise ValueError("Garden model changed before device selection")
        return {
            "model_id": "garden-speciesnet-" + payload["variant"],
            "model_sha256": actual,
            "provider": provider,
            "image_flavor": get_image_flavor(),
            "runtime_signature": await asyncio.to_thread(current_provider_runtime_signature, provider),
            "auxiliary_artifacts": {
                "package_sha256": payload["package_sha256"],
                "reference_runtime": await asyncio.to_thread(current_inference_runtime_signature),
            },
        }

    async def _reject(self, profile: dict[str, Any]) -> None:
        self.quarantine.remember_retirement(profile)
        await asyncio.to_thread(
            self.quarantine.record_retirement,
            profile,
            "garden_device_check_failed",
            "Automatic Garden runtime failed or disagreed with CPU; use CPU until the native model/runtime changes.",
        )

    async def run(
        self, image: bytes, payload: dict[str, Any], blocked: Callable[[], bool], worker: Worker
    ) -> tuple[dict[str, Any], str]:
        selection = candidate_providers()
        for provider in selection:
            profile = await self._profile(payload, provider)
            try:
                await asyncio.to_thread(self.quarantine.guard_in_process, profile)
                break
            except NativeCrashQuarantinedError:
                if provider == "cpu":
                    raise
        key = hashlib.sha256(json.dumps(profile, sort_keys=True).encode()).hexdigest()

        async def invoke(device: str, probe: bool = False) -> dict[str, Any]:
            current = await self._profile(payload, device)
            await asyncio.to_thread(self.quarantine.guard_in_process, current)
            if blocked():
                raise GardenBusy("Birds or camera activity need the hardware")
            try:
                native = await worker(image, payload | {"provider": device, "validation_probe": probe}, blocked)
            except GardenNativeWorkerFailed as error:
                if self.quarantine.remember(current, error.exit_code):
                    await asyncio.to_thread(self.quarantine.record, current, error.exit_code)
                raise
            checked_result(native, payload, device, probe=probe)
            return native

        if provider == "cpu":
            return await invoke("cpu"), "cpu"
        try:
            await asyncio.to_thread(self.quarantine.guard_in_process, profile)
        except NativeCrashQuarantinedError:
            return await invoke("cpu"), "cpu"
        baseline = None
        if key not in self._validated:
            baseline = await invoke("cpu", True)
        try:
            native = await invoke(provider, baseline is not None)
            if baseline is not None and not agrees_with_cpu(baseline, native):
                raise ValueError("Garden accelerator disagreed with CPU")
            if blocked() or candidate_providers() != selection or await self._profile(payload, provider) != profile:
                raise GardenBusy("Garden device check context changed")
        except (GardenBusy, GardenCleanupFailed):
            raise
        except (OSError, ValueError, RuntimeError, KeyError, TypeError, TimeoutError):
            self._validated.pop(key, None)
            await self._reject(profile)
            if blocked():
                raise GardenBusy("Garden fallback context changed")
            cpu_profile = await self._profile(payload, "cpu")
            await asyncio.to_thread(self.quarantine.guard_in_process, cpu_profile)
            result = baseline if baseline is not None else await invoke("cpu")
            result.pop("probabilities", None)
            return result, "cpu"
        self._validated[key] = None
        self._validated.move_to_end(key)
        while len(self._validated) > 32:
            self._validated.popitem(last=False)
        native.pop("probabilities", None)
        return native, provider
