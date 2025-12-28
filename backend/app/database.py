import aiosqlite
import structlog
from contextlib import asynccontextmanager

log = structlog.get_logger()
DB_PATH = "/data/speciesid.db"

async def column_exists(db, table: str, column: str) -> bool:
    """Check if a column exists in a table using PRAGMA table_info."""
    cursor = await db.execute(f"PRAGMA table_info({table})")
    columns = await cursor.fetchall()
    return any(col[1] == column for col in columns)


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS detections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                detection_time TIMESTAMP NOT NULL,
                detection_index INTEGER NOT NULL,
                score REAL NOT NULL,
                display_name TEXT NOT NULL,
                category_name TEXT NOT NULL,
                frigate_event TEXT NOT NULL UNIQUE,
                camera_name TEXT NOT NULL,
                is_hidden INTEGER DEFAULT 0,
                frigate_score REAL,
                sub_label TEXT
            )
        """)

        # Migration: Add columns to existing databases
        columns_to_add = [
            ("is_hidden", "INTEGER DEFAULT 0"),
            ("frigate_score", "REAL"),
            ("sub_label", "TEXT")
        ]
        
        for col_name, col_def in columns_to_add:
            if not await column_exists(db, "detections", col_name):
                try:
                    await db.execute(f"ALTER TABLE detections ADD COLUMN {col_name} {col_def}")
                    log.info(f"Added {col_name} column to detections table")
                except Exception as e:
                    log.error(f"Failed to add {col_name} column", error=str(e))
                    raise

        # Add indexes for common query patterns (after migrations)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_detections_time ON detections(detection_time DESC)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_detections_species ON detections(display_name)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_detections_camera ON detections(camera_name)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_detections_hidden ON detections(is_hidden)")

        await db.commit()
        log.info("Database initialized", path=DB_PATH)

@asynccontextmanager
async def get_db():
    async with aiosqlite.connect(DB_PATH) as db:
        yield db
