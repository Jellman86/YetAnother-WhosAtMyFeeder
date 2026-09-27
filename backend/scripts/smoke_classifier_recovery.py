"""Exercise native-timeout recovery in a disposable service with real workers.

Run from the backend directory with PYTHONPATH=. and an installed model. This
never starts ingestion or writes detections. The injected stall is cooperative
and belongs only to this process, never to the running application's singleton.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import threading
import time

from PIL import Image

from app.services import classifier_service as module
from app.services.classification_admission import ClassificationLeaseExpiredError


async def exercise(image_path: str) -> dict:
    with Image.open(image_path) as source:
        image = source.convert("RGB")
    service = module.ClassifierService()
    release = threading.Event()
    finished = threading.Event()
    native_calls = 0
    original_timeout = module.CLASSIFIER_LIVE_IMAGE_LEASE_TIMEOUT_SECONDS

    def stalled_native(*_args):
        nonlocal native_calls
        native_calls += 1
        try:
            if not release.wait(30):
                raise TimeoutError("smoke-test native stall exceeded its safety limit")
            return []
        finally:
            finished.set()

    try:
        # Warm the real worker before injecting the separate native-call stall.
        baseline = await service.classify_async_background(image, input_context={"is_cropped": True})
        original_mode = service._image_execution_mode
        service._image_execution_mode = "in_process"
        service._classifier_supervisor = None
        service.classify = stalled_native
        module.CLASSIFIER_LIVE_IMAGE_LEASE_TIMEOUT_SECONDS = 0.1
        started = time.monotonic()
        try:
            await service.classify_async_live(image, input_context={"is_cropped": True})
        except ClassificationLeaseExpiredError:
            pass
        else:
            raise AssertionError("native stall did not expire")
        elapsed = time.monotonic() - started
        assert not finished.is_set(), "native call finished before recovery was exercised"
        assert service._image_execution_mode == "subprocess"
        assert service.check_health()["status"] == "error"
        module.CLASSIFIER_LIVE_IMAGE_LEASE_TIMEOUT_SECONDS = original_timeout
        recovered = await service.classify_async_live(image, input_context={"is_cropped": True})
        background = await service.classify_async_background(image, input_context={"is_cropped": True})
        assert native_calls == 1, "new work reused the quarantined native path"
        assert service.get_status()["inference_health"]["last_recovery"]["status"] == "recovered"
        assert service.check_health()["status"] == "ok"
        for results in (baseline, recovered, background):
            assert results, "use a real retained bird crop that produces classifier candidates"
            assert all(math.isfinite(float(row["score"])) and 0 <= float(row["score"]) <= 1 for row in results)
        assert baseline[0]["label"] == recovered[0]["label"] == background[0]["label"]
        status = service.get_status()
        return {
            "ok": True,
            "initial_mode": original_mode,
            "recovered_mode": service._image_execution_mode,
            "native_expiry_seconds": round(elapsed, 3),
            "native_calls": native_calls,
            "provider": status["active_provider"],
            "model_id": status["effective_model_id"],
            "top_label": recovered[0]["label"],
            "scores": [rows[0]["score"] for rows in (baseline, recovered, background)],
            "restart_recommended": status["native_runtime_quarantine"]["restart_recommended"],
        }
    finally:
        module.CLASSIFIER_LIVE_IMAGE_LEASE_TIMEOUT_SECONDS = original_timeout
        release.set()
        if native_calls:
            await asyncio.to_thread(finished.wait, 5)
        await service.shutdown()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", help="path to an existing bird crop; never modified")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(exercise(args.image)), indent=2))


if __name__ == "__main__":
    main()
