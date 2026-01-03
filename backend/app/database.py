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
                sub_label TEXT,
                audio_confirmed BOOLEAN DEFAULT 0,
                audio_species TEXT,
                audio_score FLOAT,
                temperature FLOAT,
                weather_condition TEXT,
                scientific_name TEXT,
                common_name TEXT,
                taxa_id INTEGER
            )
        """)
        
        # Migrations: Add new columns if they don't exist
        cursor = await db.execute("PRAGMA table_info(detections)")
        columns = [row[1] for row in await cursor.fetchall()]
        
        # v1: Frigate metadata
        if "frigate_score" not in columns:
            await db.execute("ALTER TABLE detections ADD COLUMN frigate_score FLOAT")
            await db.execute("ALTER TABLE detections ADD COLUMN sub_label TEXT")
            
        # v2: Hidden toggle
        if "is_hidden" not in columns:
            await db.execute("ALTER TABLE detections ADD COLUMN is_hidden BOOLEAN DEFAULT 0")
            
        # v3: Audio correlation
        if "audio_confirmed" not in columns:
            await db.execute("ALTER TABLE detections ADD COLUMN audio_confirmed BOOLEAN DEFAULT 0")
            await db.execute("ALTER TABLE detections ADD COLUMN audio_species TEXT")
            await db.execute("ALTER TABLE detections ADD COLUMN audio_score FLOAT")
            
        # v4: Weather context
        if "temperature" not in columns:
            await db.execute("ALTER TABLE detections ADD COLUMN temperature FLOAT")
            await db.execute("ALTER TABLE detections ADD COLUMN weather_condition TEXT")

        # v5: Taxonomy normalization
        if "scientific_name" not in columns:
            await db.execute("ALTER TABLE detections ADD COLUMN scientific_name TEXT")
            await db.execute("ALTER TABLE detections ADD COLUMN common_name TEXT")
            await db.execute("ALTER TABLE detections ADD COLUMN taxa_id INTEGER")
            
        # Index for faster filtering and sorting
        await db.execute("CREATE INDEX IF NOT EXISTS idx_detections_time ON detections(detection_time)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_detections_species ON detections(display_name)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_detections_hidden ON detections(is_hidden)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_detections_camera ON detections(camera_name)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_detections_scientific ON detections(scientific_name)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_detections_common ON detections(common_name)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_detections_taxa_id ON detections(taxa_id)")
            
        await db.commit()

@asynccontextmanager
async def get_db():
    async with aiosqlite.connect(DB_PATH) as db:
        yield db
