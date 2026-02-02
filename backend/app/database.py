import os
import sys
import asyncio
import aiosqlite
import structlog
from contextlib import asynccontextmanager
from typing import Optional

log = structlog.get_logger()
DB_PATH = os.environ.get("DB_PATH", "/data/speciesid.db")
REQUIRED_COLUMNS = {
    "detections": {
        "video_classification_error",
        "ai_analysis",
        "ai_analysis_timestamp",
        "manual_tagged",
        "notified_at",
        "weather_cloud_cover",
        "weather_wind_speed",
        "weather_wind_direction",
        "weather_precipitation",
        "weather_rain",
        "weather_snowfall",
    },
    "taxonomy_cache": {
        "thumbnail_url",
    }
}


async def _verify_schema(backend_dir: str) -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config(os.path.join(backend_dir, "alembic.ini"))
    script = ScriptDirectory.from_config(config)
    expected_heads = set(script.get_heads())
    if len(expected_heads) > 1:
        log.error(
            "Multiple Alembic heads detected; merge required",
            expected_heads=sorted(expected_heads),
        )
        raise RuntimeError("Multiple Alembic heads detected; merge required")

    async with aiosqlite.connect(DB_PATH) as db:
        try:
            async with db.execute("SELECT version_num FROM alembic_version") as cursor:
                rows = await cursor.fetchall()
        except Exception as e:
            log.error("Missing alembic_version table", error=str(e))
            raise RuntimeError("Missing alembic_version table") from e

        db_versions = {row[0] for row in rows if row and row[0]}
        if db_versions != expected_heads:
            log.error(
                "Database schema is not at Alembic head",
                db_versions=sorted(db_versions),
                expected_heads=sorted(expected_heads),
            )
            raise RuntimeError("Database schema is not at Alembic head")

        for table, required in REQUIRED_COLUMNS.items():
            async with db.execute(f"PRAGMA table_info({table})") as cursor:
                columns = {row[1] for row in await cursor.fetchall()}
            missing = sorted(required - columns)
            if missing:
                log.error(
                    "Database schema missing required columns",
                    table=table,
                    missing=missing,
                )
                raise RuntimeError(f"Database schema missing columns: {missing}")


class DatabasePool:
    """Simple connection pool for aiosqlite.

    SQLite benefits from connection reuse but has limited write concurrency.
    This pool maintains a small number of connections (default: 5) with
    WAL mode enabled for better concurrent read performance.
    """

    def __init__(self, database_path: str, pool_size: int = 5):
        self.database_path = database_path
        self.pool_size = pool_size
        self._pool: asyncio.Queue = asyncio.Queue(maxsize=pool_size)
        self._initialized = False
        self._lock = asyncio.Lock()

    async def _create_connection(self) -> aiosqlite.Connection:
        """Create a new database connection with optimal settings."""
        conn = await aiosqlite.connect(
            self.database_path,
            timeout=30.0,  # 30 second timeout for lock waits
            check_same_thread=False  # Required for connection pool
        )
        # Enable WAL mode for better concurrency
        await conn.execute("PRAGMA journal_mode=WAL;")
        await conn.execute("PRAGMA synchronous=NORMAL;")
        # Optimize for read-heavy workloads
        await conn.execute("PRAGMA cache_size=-64000;")  # 64MB cache
        await conn.commit()
        return conn

    async def initialize(self):
        """Initialize the connection pool."""
        async with self._lock:
            if self._initialized:
                return

            log.info("Initializing database connection pool",
                     pool_size=self.pool_size,
                     db_path=self.database_path)

            # Create initial pool of connections
            for _ in range(self.pool_size):
                conn = await self._create_connection()
                await self._pool.put(conn)

            self._initialized = True
            log.info("Database connection pool initialized")

    async def acquire(self) -> aiosqlite.Connection:
        """Acquire a connection from the pool."""
        if not self._initialized:
            await self.initialize()

        # Get connection from pool (waits if none available)
        conn = await self._pool.get()
        return conn

    async def release(self, conn: aiosqlite.Connection):
        """Release a connection back to the pool."""
        try:
            # Rollback any uncommitted transactions
            await conn.rollback()
            await self._pool.put(conn)
        except Exception as e:
            # Connection is corrupt, create a new one
            log.warning("Discarding corrupt connection", error=str(e))
            try:
                await conn.close()
            except Exception:
                pass
            # Create replacement connection
            new_conn = await self._create_connection()
            await self._pool.put(new_conn)

    async def close_all(self):
        """Close all connections in the pool."""
        async with self._lock:
            if not self._initialized:
                return

            log.info("Closing database connection pool")
            while not self._pool.empty():
                try:
                    conn = self._pool.get_nowait()
                    await conn.close()
                except Exception as e:
                    log.warning("Error closing connection", error=str(e))

            self._initialized = False
            log.info("Database connection pool closed")


# Global connection pool
_db_pool: Optional[DatabasePool] = None


async def init_db():
    """Initialize database and connection pool."""
    global _db_pool

    # Initialize WAL mode and run migrations using a temporary connection
    async with aiosqlite.connect(DB_PATH) as db:
        # Enable Write-Ahead Logging for better concurrency
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA synchronous=NORMAL;")
        await db.commit()

    # Run Alembic migrations
    log.info("Running database migrations...")
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        import subprocess
        env = os.environ.copy()
        env["DB_PATH"] = DB_PATH

        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=backend_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=60  # 60 second timeout to prevent indefinite hangs
        )

        if result.returncode == 0:
            log.info("Database migrations completed successfully")
        else:
            log.error(
                "Database migration failed",
                error=result.stderr,
                output=result.stdout
            )
            raise RuntimeError("Database migration failed")
    except subprocess.TimeoutExpired:
        log.error("Database migration timed out after 60 seconds")
        raise
    except Exception as e:
        log.error("Failed to run database migrations", error=str(e))
        raise

    log.info("Verifying database schema...")
    await _verify_schema(backend_dir)
    log.info("Database schema verification completed")

    # Initialize connection pool
    _db_pool = DatabasePool(DB_PATH, pool_size=5)
    await _db_pool.initialize()


async def close_db():
    """Close database connection pool."""
    global _db_pool
    if _db_pool:
        await _db_pool.close_all()
        _db_pool = None


@asynccontextmanager
async def get_db():
    """Get a database connection from the pool.

    Usage:
        async with get_db() as db:
            cursor = await db.execute("SELECT * FROM table")
            rows = await cursor.fetchall()
    """
    if _db_pool is None:
        # Fallback: create connection if pool not initialized
        log.warning("Database pool not initialized, using direct connection")
        async with aiosqlite.connect(DB_PATH) as db:
            yield db
        return

    conn = await _db_pool.acquire()
    try:
        yield conn
    finally:
        await _db_pool.release(conn)
