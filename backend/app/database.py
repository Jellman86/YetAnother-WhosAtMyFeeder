import os
import aiosqlite
import structlog
from contextlib import asynccontextmanager

log = structlog.get_logger()
DB_PATH = os.environ.get("DB_PATH", "/data/speciesid.db")


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # Enable Write-Ahead Logging for better concurrency
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA synchronous=NORMAL;")
        await db.commit()

    # Run Alembic migrations
    log.info("Running database migrations...")
    try:
        import subprocess
        # Get the path to alembic relative to the venv
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # In Docker, it might just be 'alembic' in the path, 
        # but here we should try to find it.
        # We'll use the current python interpreter to find the alembic executable
        # or just run 'alembic' and assume it's in the environment.
        
        # Determine script path (in backend directory)
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            cwd=backend_dir,
            capture_output=True,
            text=True,
            timeout=60  # 60 second timeout to prevent indefinite hangs
        )
        
        if result.returncode == 0:
            log.info("Database migrations completed successfully")
        else:
            log.error("Database migration failed", error=result.stderr)
            # We don't necessarily want to crash here if it's just a warning
            # but usually migrations are critical.
    except subprocess.TimeoutExpired:
        log.error("Database migration timed out after 60 seconds")
    except Exception as e:
        log.error("Failed to run database migrations", error=str(e))


@asynccontextmanager
async def get_db():
    async with aiosqlite.connect(DB_PATH) as db:
        yield db
