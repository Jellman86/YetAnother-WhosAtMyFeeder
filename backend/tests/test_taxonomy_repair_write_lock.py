"""Taxonomy repair must not hold the database write lock across name lookups.

Each lookup can be a slow iNaturalist request. Committing only once per batch of
200 kept a write transaction open across all of them, and a live detection save
waits at most `busy_timeout` (30 s) before failing with "database is locked".
"""

import asyncio
import os
from pathlib import Path
import shutil
import subprocess
import sys

import aiosqlite
import pytest

from app.services import canonical_identity_repair_service as repair_module
from app.services.canonical_identity_repair_service import CanonicalIdentityRepairService


@pytest.fixture(scope="module")
def migrated_template(tmp_path_factory):
    path = tmp_path_factory.mktemp("taxonomy-repair-schema") / "template.db"
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "DB_PATH": str(path)},
        check=True,
        capture_output=True,
    )
    return path


@pytest.mark.asyncio
async def test_live_writes_proceed_while_taxonomy_repair_waits_on_lookups(monkeypatch, tmp_path, migrated_template):
    path = tmp_path / "repair.db"
    shutil.copyfile(migrated_template, path)

    async with aiosqlite.connect(path) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        for index in range(3):
            await db.execute(
                """INSERT INTO detections (detection_time, detection_index, score, display_name, category_name,
                                           frigate_event, camera_name, is_hidden, manual_tagged)
                   VALUES (?, ?, 0.9, ?, ?, ?, 'feeder', 0, 0)""",
                (f"2026-09-26 10:0{index}:00", index, f"Lookupbird {index}", f"Lookupbird {index}", f"evt-{index}"),
            )
        await db.commit()

        lookups_started = asyncio.Event()

        async def slow_lookup(name, db=None):
            lookups_started.set()
            await asyncio.sleep(0.3)
            return {"scientific_name": f"Avis {name.split()[-1]}", "common_name": name, "taxa_id": 1000}

        async def no_cache(self, name):
            return {}

        monkeypatch.setattr(repair_module.taxonomy_service, "get_names", slow_lookup)
        monkeypatch.setattr(repair_module.DetectionRepository, "get_taxonomy_names", no_cache)

        repair = asyncio.create_task(CanonicalIdentityRepairService().run(db=db))
        await lookups_started.wait()
        # Let the first row resolve and write, so any transaction the repair keeps open is live.
        await asyncio.sleep(0.45)

        async with aiosqlite.connect(path) as live:
            await live.execute("PRAGMA busy_timeout=100")
            await live.execute(
                """INSERT INTO detections (detection_time, detection_index, score, display_name, category_name,
                                           frigate_event, camera_name, is_hidden, manual_tagged,
                                           scientific_name, common_name, taxa_id)
                   VALUES ('2026-09-26 11:00:00', 9, 0.95, 'Dunnock', 'Dunnock', 'evt-live', 'feeder', 0, 0,
                           'Prunella modularis', 'Dunnock', 13094)"""
            )
            await live.commit()

        summary = await repair
        assert summary["updated"] == 3

        async with db.execute("SELECT COUNT(*) FROM detections WHERE scientific_name LIKE 'Avis %'") as cursor:
            assert (await cursor.fetchone())[0] == 3
