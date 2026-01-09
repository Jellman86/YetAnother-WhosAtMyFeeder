import os
import asyncio
import aiosqlite
import structlog
from contextlib import asynccontextmanager
from typing import Optional

log = structlog.get_logger()
DB_PATH = os.environ.get("DB_PATH", "/data/speciesid.db")


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
    try:
        import subprocess
        # Get the path to alembic relative to the venv
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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
