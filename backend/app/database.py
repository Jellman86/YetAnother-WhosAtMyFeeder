import aiosqlite
import structlog
from contextlib import asynccontextmanager

log = structlog.get_logger()
DB_PATH = "/data/speciesid.db"

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
                is_hidden INTEGER DEFAULT 0
            )
        """)

        # Migration: Add is_hidden column to existing databases
        # Must run BEFORE creating the index on is_hidden
        try:
            await db.execute("ALTER TABLE detections ADD COLUMN is_hidden INTEGER DEFAULT 0")
            log.info("Added is_hidden column to detections table")
        except Exception:
            # Column already exists, ignore
            pass

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
