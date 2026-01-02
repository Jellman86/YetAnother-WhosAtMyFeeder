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
                score FLOAT NOT NULL,
                display_name TEXT NOT NULL,
                category_name TEXT NOT NULL,
                frigate_event TEXT UNIQUE NOT NULL,
                camera_name TEXT NOT NULL,
                is_hidden BOOLEAN DEFAULT 0,
                frigate_score FLOAT,
                sub_label TEXT
            )
        """)
        
        # Migrations: Add new columns if they don't exist
        # Check for frigate_score (v1 migration)
        cursor = await db.execute("PRAGMA table_info(detections)")
        columns = [row[1] for row in await cursor.fetchall()]
        
        if "frigate_score" not in columns:
            await db.execute("ALTER TABLE detections ADD COLUMN frigate_score FLOAT")
            await db.execute("ALTER TABLE detections ADD COLUMN sub_label TEXT")
            
        # Check for audio columns (v2 migration)
        if "audio_confirmed" not in columns:
            await db.execute("ALTER TABLE detections ADD COLUMN audio_confirmed BOOLEAN DEFAULT 0")
            await db.execute("ALTER TABLE detections ADD COLUMN audio_species TEXT")
            await db.execute("ALTER TABLE detections ADD COLUMN audio_score FLOAT")
            
        # Check for weather columns (v3 migration)
        if "temperature" not in columns:
            await db.execute("ALTER TABLE detections ADD COLUMN temperature FLOAT")
            await db.execute("ALTER TABLE detections ADD COLUMN weather_condition TEXT")
            
        await db.commit()

@asynccontextmanager
async def get_db():
    async with aiosqlite.connect(DB_PATH) as db:
        yield db
