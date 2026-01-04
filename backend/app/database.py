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
        # Enable Write-Ahead Logging for better concurrency
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA synchronous=NORMAL;")
        
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

        await db.execute("""
            CREATE TABLE IF NOT EXISTS taxonomy_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scientific_name TEXT NOT NULL UNIQUE,
                common_name TEXT,
                taxa_id INTEGER,
                is_not_found BOOLEAN DEFAULT 0,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_taxonomy_scientific ON taxonomy_cache(scientific_name)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_taxonomy_common ON taxonomy_cache(common_name)")
        
        # Migrations: Add new columns if they don't exist
        cursor = await db.execute("PRAGMA table_info(detections)")
        columns = [row[1] for row in await cursor.fetchall()]
        
        migrations = [
            ("frigate_score", "FLOAT"),
            ("sub_label", "TEXT"),
            ("is_hidden", "BOOLEAN DEFAULT 0"),
            ("audio_confirmed", "BOOLEAN DEFAULT 0"),
            ("audio_species", "TEXT"),
            ("audio_score", "FLOAT"),
            ("temperature", "FLOAT"),
            ("weather_condition", "TEXT"),
            ("scientific_name", "TEXT"),
            ("common_name", "TEXT"),
            ("taxa_id", "INTEGER")
        ]

        for col_name, col_type in migrations:
            if col_name not in columns:
                log.info(f"Auto-healing DB: Adding missing column {col_name}")
                await db.execute(f"ALTER TABLE detections ADD COLUMN {col_name} {col_type}")
            
        # Index for faster filtering and sorting
        indices = [
            ("idx_detections_time", "detection_time"),
            ("idx_detections_species", "display_name"),
            ("idx_detections_hidden", "is_hidden"),
            ("idx_detections_camera", "camera_name"),
            ("idx_detections_scientific", "scientific_name"),
            ("idx_detections_common", "common_name"),
            ("idx_detections_taxa_id", "taxa_id"),
            ("idx_detections_frigate_event", "frigate_event")
        ]
        
        for idx_name, col_name in indices:
            await db.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON detections({col_name})")
            
        await db.commit()

@asynccontextmanager
async def get_db():
    async with aiosqlite.connect(DB_PATH) as db:
        yield db
