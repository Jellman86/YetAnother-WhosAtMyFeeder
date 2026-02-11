#!/usr/bin/env python3
"""CI regression guard for Alembic upgrade paths.

This script validates that multiple historical revision paths can be upgraded
to head cleanly, with SQLite integrity checks and app-level DB init.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def _run(cmd: list[str], cwd: Path, env: dict[str, str]) -> None:
    result = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(cmd)}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


def _verify_sqlite(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys=ON;")
        fk_enabled = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
        if fk_enabled != 1:
            raise RuntimeError("foreign_keys pragma is not enabled")

        integrity = conn.execute("PRAGMA integrity_check;").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"integrity_check failed: {integrity}")

        fk_violations = conn.execute("PRAGMA foreign_key_check;").fetchall()
        if fk_violations:
            raise RuntimeError(f"foreign_key_check violations: {fk_violations[:20]}")

        fk_list = conn.execute("PRAGMA foreign_key_list(taxonomy_translations);").fetchall()
        if fk_list:
            raise RuntimeError(f"taxonomy_translations has unexpected foreign keys: {fk_list}")

        conn.execute(
            "INSERT OR REPLACE INTO taxonomy_translations (taxa_id, language_code, common_name) VALUES (?, ?, ?)",
            (123456, "ru", "test-name"),
        )
        conn.commit()
    finally:
        conn.close()


async def _run_init_db() -> None:
    from app.database import close_db, init_db

    await init_db()
    await close_db()


def _pick_anchor_revisions(revisions: list[str]) -> list[str]:
    """Pick a deterministic sample of historical revisions (excluding head)."""
    if len(revisions) <= 1:
        return []
    head_index = len(revisions) - 1
    candidate_indexes = {
        0,
        max(0, len(revisions) // 3),
        max(0, (2 * len(revisions)) // 3),
        max(0, head_index - 1),
    }
    anchors = []
    for idx in sorted(candidate_indexes):
        if idx >= head_index:
            continue
        anchors.append(revisions[idx])
    return anchors


def main() -> int:
    backend_dir = Path(__file__).resolve().parents[1]
    alembic_config = Config(str(backend_dir / "alembic.ini"))
    script = ScriptDirectory.from_config(alembic_config)

    heads = script.get_heads()
    if len(heads) != 1:
        raise RuntimeError(f"Expected one Alembic head, found: {heads}")

    revisions_head_to_base = [rev.revision for rev in script.walk_revisions("base", "heads")]
    revisions_base_to_head = list(reversed([r for r in revisions_head_to_base if r]))
    if not revisions_base_to_head:
        raise RuntimeError("No Alembic revisions found")

    head = revisions_base_to_head[-1]
    anchors = _pick_anchor_revisions(revisions_base_to_head)
    print("Migration path check anchors:", anchors)
    print("Migration head:", head)

    with tempfile.TemporaryDirectory(prefix="yawamf_ci_migration_paths_") as tmpdir:
        for i, anchor in enumerate(anchors, start=1):
            db_path = str(Path(tmpdir) / f"path_{i}.db")
            env = os.environ.copy()
            env["DB_PATH"] = db_path
            print(f"[path {i}] upgrade from {anchor} -> {head}")
            _run([sys.executable, "-m", "alembic", "upgrade", anchor], cwd=backend_dir, env=env)
            _run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=backend_dir, env=env)
            _verify_sqlite(db_path)

            # Validate app-level startup DB init against the upgraded DB.
            os.environ["DB_PATH"] = db_path
            asyncio.run(_run_init_db())
            _verify_sqlite(db_path)
            print(f"[path {i}] OK")

    print("Migration upgrade path matrix OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
