"""Replay a retained crop through real inference into a disposable migrated DB.

Run from backend with PYTHONPATH=.: python scripts/smoke_backfill_replay.py
--model-dir /data/models/rope_vit_b14_inat21 --image /path/to/crop.jpg
--provider intel_npu. No live configuration, ingestion or notifications are used.
"""

from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import AsyncMock, patch


def isolate_environment(root: Path) -> None:
    """Keep device/runtime paths but discard inherited application overrides."""
    sections = (
        "FRIGATE",
        "CLASSIFICATION",
        "MAINTENANCE",
        "MEDIA_CACHE",
        "LOCATION",
        "BIRDWEATHER",
        "HA_WEATHER",
        "EBIRD",
        "INATURALIST",
        "ENRICHMENT",
        "LLM",
        "TELEMETRY",
        "NOTIFICATIONS",
        "ACCESSIBILITY",
        "APPEARANCE",
        "SYSTEM",
        "AUTH",
        "PUBLIC_ACCESS",
    )
    for key in tuple(os.environ):
        if key.startswith(tuple(f"{section}__" for section in sections)) or key.startswith("YA_WAMF_"):
            os.environ.pop(key)
    os.environ.update(
        CONFIG_FILE=str(root / "config.json"),
        DB_PATH=str(root / "detections.db"),
        MODEL_DIR=str(root / "models"),
        SPECIES_CATALOG_PATH=str(root / "catalog.db"),
    )


async def exercise(image_path: Path, provider: str, execution_mode: str) -> dict:
    # Imports must follow environment isolation in main(), including for workers.
    import aiosqlite

    from app.config import settings
    from app.repositories.detection_repository import DetectionRepository
    from app.services import backfill_service as backfill
    from app.services import classifier_service as classifier
    from app.services import detection_service as detection
    from app.services.species_catalog_resolver import ShadowResolution

    @asynccontextmanager
    async def database():
        async with aiosqlite.connect(os.environ["DB_PATH"]) as db:
            await db.execute("PRAGMA foreign_keys=ON")
            yield db

    service = classifier.ClassifierService()
    jpeg = image_path.read_bytes()
    events = [
        {"id": f"isolated-replay-{i}", "camera": "isolated-test", "start_time": 1700000000 + i, "top_score": 0.95}
        for i in range(4)
    ]
    try:
        with (
            patch.object(classifier, "_classifier_instance", service),
            patch.object(detection, "get_db", database),
            patch.object(backfill.frigate_client, "get_snapshot", AsyncMock(return_value=jpeg)) as snapshot,
            patch.object(detection.taxonomy_service, "get_names", AsyncMock(return_value={})),
            patch.object(
                detection, "_catalog_shadow_resolution", AsyncMock(return_value=ShadowResolution(verdict="unavailable"))
            ),
            patch.object(detection.birdweather_service, "report_detection", AsyncMock(return_value=False)),
            patch.object(detection.broadcaster, "broadcast", AsyncMock()),
        ):
            replay = backfill.BackfillService(service)
            first = [await replay.process_historical_event(event) for event in events]
            assert first == [("new", None)] * len(events), first
            second = [await replay.process_historical_event(event) for event in events]
            assert second == [("skipped", "already_exists")] * len(events), second
            settings.classification.threshold = 1.0
            settings.classification.min_confidence = 1.0
            filtered = await replay.process_historical_event({**events[0], "id": "filtered-replay"})
            assert filtered[0] == "skipped", filtered
            snapshot.return_value = b"invalid jpeg"
            corrupt = await replay.process_historical_event({**events[0], "id": "corrupt-replay"})
            assert corrupt[0] == "error", corrupt
            async with database() as db:
                count = (await (await db.execute("SELECT count(*) FROM detections")).fetchone())[0]
                integrity = (await (await db.execute("PRAGMA integrity_check")).fetchone())[0]
                row = await DetectionRepository(db).get_by_frigate_event(events[0]["id"])
            assert count == len(events) and integrity == "ok"
            status = service.get_status()
            assert status["active_provider"] == provider, status["active_provider"]
            assert service._image_execution_mode == execution_mode, service._image_execution_mode
            return {
                "ok": True,
                "provider": status["active_provider"],
                "model": status["effective_model_id"],
                "execution_mode": service._image_execution_mode,
                "inserted": count,
                "duplicate_replays_skipped": len(second),
                "filtered": filtered,
                "corrupt": corrupt,
                "top_label": row.category_name,
                "score": row.score,
                "database_integrity": integrity,
                "database_scope": "temporary, removed on exit",
            }
    finally:
        await service.shutdown()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--provider", choices=["cpu", "cuda", "intel_cpu", "intel_gpu", "intel_npu"], required=True)
    parser.add_argument("--execution-mode", choices=["subprocess", "in_process"], default="subprocess")
    args = parser.parse_args()
    source = args.model_dir.resolve(strict=True)
    image = args.image.resolve(strict=True)
    for filename in ("model.onnx", "labels.txt", "model_config.json"):
        if not (source / filename).is_file():
            parser.error(f"installed model is missing {filename}")
    with tempfile.TemporaryDirectory(prefix="yawamf-backfill-replay-") as temporary:
        root = Path(temporary)
        model = root / "models" / source.name
        model.mkdir(parents=True)
        # The weight file is read-only input; all configs and compiled caches are isolated.
        (model / "model.onnx").symlink_to(source / "model.onnx")
        for filename in ("labels.txt", "model_config.json"):
            shutil.copyfile(source / filename, model / filename)
        config = root / "config.json"
        config.write_text(
            json.dumps(
                {
                    "classification": {
                        "model": source.name,
                        "inference_provider": args.provider,
                        "image_execution_mode": args.execution_mode,
                        "threshold": 0.01,
                        "min_confidence": 0.01,
                        "trust_frigate_sublabel": False,
                    },
                    "media_cache": {"enabled": False},
                }
            )
        )
        isolate_environment(root)
        migration = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], capture_output=True, text=True)
        if migration.returncode:
            raise RuntimeError(f"Disposable database migration failed: {migration.stderr}")
        print(json.dumps(asyncio.run(exercise(image, args.provider, args.execution_mode)), indent=2))


if __name__ == "__main__":
    main()
