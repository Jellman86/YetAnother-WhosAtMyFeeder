"""Verify same-model CPU recovery and backfill with real workers in disposable state.

Seeds a synthetic crash record, not a GPU crash. The Linux supervisor regression
separately exercises real SIGABRT/reaping. Never imports the live service singleton.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time


async def exercise(image_path: Path) -> dict:
    from PIL import Image
    from app.services.classifier_service import ClassifierService
    from app.services.native_crash_quarantine import NativeCrashQuarantinedError
    from scripts.smoke_backfill_replay import exercise as backfill

    service = ClassifierService()
    image = Image.open(image_path).convert("RGB")
    report = {"seeded_fault": "synthetic SIGSEGV evidence", "database_scope": "temporary"}
    try:
        profile = await asyncio.to_thread(service._native_launch_profile)
        await asyncio.to_thread(service._native_crash_quarantine.record, profile, -signal.SIGSEGV)
        for priority, classify in (
            ("live", service.classify_async_live),
            ("background", service.classify_async_background),
        ):
            started = time.monotonic()
            rows = await classify(image, input_context={"is_cropped": True})
            assert rows and all(math.isfinite(float(row["score"])) for row in rows)
            state = service._native_cpu_recovery.snapshot()[priority]
            assert state["status"] == "degraded" and state["runtime"]["model_sha256"] == profile["model_sha256"]
            assert service.get_status()["active_provider"] in {"cpu", "intel_cpu"}
            assert service.check_health()["status"] == "degraded"
            report[priority] = {
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "runtime": state["runtime"],
                "top_label": rows[0]["label"],
                "score": rows[0]["score"],
            }
        import cv2
        import numpy as np

        video_path = Path(os.environ["DATA_DIR"]) / "cpu-recovery.mp4"
        frame = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)
        writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), 5, image.size)
        assert writer.isOpened()
        try:
            for _ in range(15):
                writer.write(frame)
        finally:
            writer.release()
        progress = []
        video = await service.classify_video_async(
            str(video_path),
            stride=5,
            max_frames=3,
            progress_callback=lambda *args: progress.append(args),
            input_context={"is_cropped": True},
            propagate_worker_failure=True,
        )
        assert progress and service._native_cpu_recovery.snapshot()["video"]["recovered"]
        report["video"] = {
            "progress_updates": len(progress),
            "candidates": len(video),
            "state": service._native_cpu_recovery.snapshot()["video"],
        }
        try:
            await asyncio.to_thread(service._native_crash_quarantine.guard, profile)
        except NativeCrashQuarantinedError:
            report["original_profile_still_quarantined"] = True
        else:
            raise AssertionError("CPU success erased native crash evidence")
    finally:
        image.close()
        await service.shutdown()
    report["backfill"] = await backfill(image_path, report["background"]["runtime"]["active_provider"], "subprocess")
    report["ok"] = True
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--region")
    parser.add_argument("--image", type=Path, required=True)
    args = parser.parse_args()
    source = args.model_dir.resolve(strict=True)
    image = args.image.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="yawamf-native-cpu-") as temporary:
        root = Path(temporary)
        from scripts.smoke_backfill_replay import isolate_environment

        isolate_environment(root)
        for key, directory in (
            ("CONFIG_DIR", "config"),
            ("DATA_DIR", "data"),
            ("MEDIA_CACHE_DIR", "media"),
            ("OPENVINO_CACHE_DIR", "compiled"),
        ):
            (root / directory).mkdir()
            os.environ[key] = str(root / directory)
        model = root / "models" / args.model_id
        if args.region:
            model /= args.region
        model.mkdir(parents=True)
        for name in ("model.onnx", "model.onnx.data", "model.tflite"):
            if (source / name).is_file():
                (model / name).symlink_to(source / name)
        for name in ("labels.txt", "model_config.json"):
            shutil.copyfile(source / name, model / name)
        (root / "models" / "active_model.json").write_text(json.dumps({"model_id": args.model_id}))
        (root / "config.json").write_text(
            json.dumps(
                {
                    "classification": {
                        "model": args.model_id,
                        "inference_provider": "intel_gpu",
                        "image_execution_mode": "subprocess",
                        "regional_model_override": args.region or "auto",
                        "threshold": 0.01,
                        "min_confidence": 0.01,
                        "trust_frigate_sublabel": False,
                    },
                    "media_cache": {"enabled": False},
                }
            )
        )
        migration = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"], capture_output=True, timeout=60
        )
        if migration.returncode:
            raise RuntimeError("Disposable database migration failed")
        print(json.dumps(asyncio.run(exercise(image)), indent=2))


if __name__ == "__main__":
    main()
