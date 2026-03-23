import os
import sys
import shutil
import asyncio
import time
import aiosqlite
import structlog
from datetime import datetime, timezone
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional

log = structlog.get_logger()

DEFAULT_DB_POOL_SIZE = int(os.environ.get("DB_POOL_SIZE", "5"))
DEFAULT_DB_BUSY_TIMEOUT_MS = int(os.environ.get("DB_BUSY_TIMEOUT_MS", "30000"))
DB_POOL_SLOW_ACQUIRE_WARN_MS = float(os.environ.get("DB_POOL_SLOW_ACQUIRE_WARN_MS", "250"))

def _is_testing() -> bool:
    # PYTEST_CURRENT_TEST is only set while a test is executing (not during collection/import).
    return (
        "pytest" in sys.modules
        or bool(os.getenv("PYTEST_CURRENT_TEST"))
        or os.getenv("YA_WAMF_TESTING") == "1"
    )


def _get_db_path() -> str:
    env_path = os.environ.get("DB_PATH")
    if env_path:
        return env_path
    # Default to a writable location during tests to avoid hangs if /data isn't mounted.
    if _is_testing():
        return "/tmp/yawamf-test.db"
    return "/data/speciesid.db"


def get_db_path_diagnostics() -> dict:
    """Return non-fatal DB path diagnostics for startup logging."""
    db_path = _get_db_path()
    parent = Path(db_path).expanduser().resolve().parent
    exists = parent.exists()
    writable = os.access(parent, os.W_OK | os.X_OK) if exists else False
    return {
        "db_path": db_path,
        "parent": str(parent),
        "parent_exists": exists,
        "parent_writable": writable,
        "process_uid_gid": f"{os.getuid()}:{os.getgid()}",
    }


def _assert_db_path_writable(db_path: str) -> None:
    """Fail fast with a clear error if DB directory is not writable."""
    parent = Path(db_path).expanduser().resolve().parent
    if not parent.exists():
        raise RuntimeError(
            f"DB_PATH directory does not exist: {parent}. "
            f"Set DB_PATH to a writable location (current: {db_path})."
        )

    # Explicitly check directory access before sqlite connect so errors are actionable.
    if not os.access(parent, os.W_OK | os.X_OK):
        try:
            st = parent.stat()
            mode = oct(st.st_mode & 0o777)
            owner = f"{st.st_uid}:{st.st_gid}"
        except Exception:
            mode = "unknown"
            owner = "unknown"
        raise RuntimeError(
            "DB_PATH directory is not writable by current process: "
            f"path={parent} owner={owner} mode={mode} process_uid_gid={os.getuid()}:{os.getgid()}. "
            f"Set DB_PATH to a writable location (current: {db_path})."
        )

    # Probe write permission with a temporary file to catch FS/userns edge cases.
    probe = parent / ".yawamf_write_probe.tmp"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except Exception as e:
        raise RuntimeError(
            "DB_PATH directory exists but write probe failed: "
            f"path={parent} process_uid_gid={os.getuid()}:{os.getgid()} error={e}. "
            f"Set DB_PATH to a writable location (current: {db_path})."
        ) from e

REQUIRED_COLUMNS = {
    "detections": {
        "video_classification_error",
        "video_classification_provider",
        "video_classification_backend",
        "video_classification_model_id",
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


def _backup_db(db_path: str) -> Optional[str]:
    """
    Copy the database to a timestamped backup file in the same directory.

    Called before running migrations so users have a restore point when
    switching between image versions (e.g. live ↔ dev).  Returns the
    backup path on success, None if the DB does not exist yet or the copy
    fails (non-fatal — a missing backup is better than blocking startup).
    """
    src = Path(db_path)
    if not src.exists():
        return None
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dst = src.with_name(f"{src.stem}.pre-migration-{ts}{src.suffix}")
    try:
        shutil.copy2(src, dst)
        log.info("Pre-migration database backup created", backup_path=str(dst))
        return str(dst)
    except Exception as e:
        log.warning("Could not create pre-migration database backup", error=str(e))
        return None


def _db_is_ahead_of_codebase(db_versions: set, backend_dir: str) -> bool:
    """
    Return True when the database's current revision is not reachable from
    the codebase's migration tree.  This is the "rolled-forward then reverted"
    scenario: a user ran the dev image (which applied new migrations) and has
    now switched back to the live image, which doesn't know those revisions.
    """
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        cfg = Config(os.path.join(backend_dir, "alembic.ini"))
        script = ScriptDirectory.from_config(cfg)
        known = {rev.revision for rev in script.walk_revisions()}
        return bool(db_versions and not db_versions.issubset(known))
    except Exception:
        return False


async def _verify_schema(backend_dir: str, db_path: str) -> None:
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

    async with aiosqlite.connect(db_path) as db:
        try:
            async with db.execute("SELECT version_num FROM alembic_version") as cursor:
                rows = await cursor.fetchall()
        except Exception as e:
            log.error("Missing alembic_version table", error=str(e))
            raise RuntimeError("Missing alembic_version table") from e

        db_versions = {row[0] for row in rows if row and row[0]}

        if db_versions != expected_heads:
            # Distinguish "ahead" (downgrade scenario) from genuinely broken.
            if _db_is_ahead_of_codebase(db_versions, backend_dir):
                log.warning(
                    "Database schema is ahead of this image version — "
                    "the database was previously migrated by a newer build "
                    "(e.g. the dev image).  The extra schema is additive and "
                    "this image can run safely, but some newer features will "
                    "not be available.  To fully restore, either upgrade back "
                    "to the newer image or restore from the pre-migration "
                    "backup (speciesid.db.pre-migration-*.db) created before "
                    "the last migration run.",
                    db_versions=sorted(db_versions),
                    expected_heads=sorted(expected_heads),
                )
                # Do not raise — additive schema is backwards-compatible with
                # SQLite; live code that does not reference the new columns
                # continues to function correctly.
                return
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

    def __init__(self, database_path: str, pool_size: int = DEFAULT_DB_POOL_SIZE):
        self.database_path = database_path
        self.pool_size = pool_size
        self._pool: asyncio.Queue = asyncio.Queue(maxsize=pool_size)
        self._initialized = False
        self._lock = asyncio.Lock()
        self._acquire_count = 0
        self._slow_acquire_count = 0
        self._acquire_wait_total_ms = 0.0
        self._acquire_wait_max_ms = 0.0

    async def _create_connection(self) -> aiosqlite.Connection:
        """Create a new database connection with optimal settings."""
        conn = await aiosqlite.connect(
            self.database_path,
            timeout=max(1.0, DEFAULT_DB_BUSY_TIMEOUT_MS / 1000.0),
            check_same_thread=False  # Required for connection pool
        )
        # Enable WAL mode for better concurrency
        await conn.execute("PRAGMA journal_mode=WAL;")
        await conn.execute("PRAGMA synchronous=NORMAL;")
        await conn.execute("PRAGMA foreign_keys=ON;")
        await conn.execute(f"PRAGMA busy_timeout={DEFAULT_DB_BUSY_TIMEOUT_MS};")
        # Optimize for read-heavy workloads
        await conn.execute("PRAGMA cache_size=-64000;")  # 64MB cache
        await conn.execute("PRAGMA temp_store=MEMORY;")
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
        started = time.monotonic()
        conn = await self._pool.get()
        waited_ms = (time.monotonic() - started) * 1000.0
        self._acquire_count += 1
        self._acquire_wait_total_ms += waited_ms
        if waited_ms > self._acquire_wait_max_ms:
            self._acquire_wait_max_ms = waited_ms
        if waited_ms >= DB_POOL_SLOW_ACQUIRE_WARN_MS:
            self._slow_acquire_count += 1
            log.warning(
                "Slow DB pool acquire",
                waited_ms=round(waited_ms, 1),
                queue_available=self._pool.qsize(),
                pool_size=self.pool_size,
                busy_timeout_ms=DEFAULT_DB_BUSY_TIMEOUT_MS,
            )
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

    def get_status(self) -> dict:
        avg_wait_ms = (
            (self._acquire_wait_total_ms / self._acquire_count)
            if self._acquire_count > 0
            else 0.0
        )
        return {
            "initialized": self._initialized,
            "pool_size": self.pool_size,
            "available_connections": self._pool.qsize(),
            "acquire_count": self._acquire_count,
            "slow_acquire_count": self._slow_acquire_count,
            "acquire_wait_avg_ms": round(avg_wait_ms, 2),
            "acquire_wait_max_ms": round(self._acquire_wait_max_ms, 2),
            "slow_acquire_warn_ms": DB_POOL_SLOW_ACQUIRE_WARN_MS,
        }


# Global connection pool
_db_pool: Optional[DatabasePool] = None


def is_db_pool_initialized() -> bool:
    """Return True when the global DB pool has been initialized."""
    return _db_pool is not None and _db_pool._initialized


def get_db_pool_status() -> dict:
    """Return lightweight DB pool runtime diagnostics."""
    if _db_pool is None:
        return {
            "initialized": False,
            "pool_size": 0,
            "available_connections": 0,
            "acquire_count": 0,
            "slow_acquire_count": 0,
            "acquire_wait_avg_ms": 0.0,
            "acquire_wait_max_ms": 0.0,
            "slow_acquire_warn_ms": DB_POOL_SLOW_ACQUIRE_WARN_MS,
        }
    return _db_pool.get_status()


async def init_db():
    """Initialize database and connection pool."""
    global _db_pool
    if _db_pool is not None and _db_pool._initialized:
        await close_db()
        
    db_path = _get_db_path()
    _assert_db_path_writable(db_path)

    # Initialize WAL mode and run migrations using a temporary connection
    async with aiosqlite.connect(db_path) as db:
        # Enable Write-Ahead Logging for better concurrency
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA synchronous=NORMAL;")
        await db.commit()

    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Run Alembic migrations (unless already initialized by test runner)
    if os.environ.get("YA_WAMF_TEST_DB_INITIALIZED") == "1":
        log.info("Test DB already initialized, skipping migrations")
    else:
        backup_path = _backup_db(db_path)

        log.info("Running database migrations...")
        try:
            import subprocess
            env = os.environ.copy()
            env["DB_PATH"] = db_path

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
                # Detect the "rolled-forward then reverted" scenario: a newer
                # image (e.g. dev) applied migrations this image doesn't know
                # about.  Alembic fails with "Can't locate revision identified
                # by ..." in this case.  The extra schema is additive-only so
                # the live image can run safely — warn and continue instead of
                # blocking startup.
                stderr_lower = result.stderr.lower()
                is_unknown_revision = (
                    "can't locate revision" in stderr_lower
                    or "can't locate revision identified by" in stderr_lower
                    or "no such revision" in stderr_lower
                )

                if is_unknown_revision:
                    # Read the DB's current alembic_version so we can call
                    # _db_is_ahead_of_codebase with accurate data.
                    try:
                        import aiosqlite as _aiosqlite
                        async with _aiosqlite.connect(db_path) as _db:
                            async with _db.execute(
                                "SELECT version_num FROM alembic_version"
                            ) as _cur:
                                _rows = await _cur.fetchall()
                        db_versions = {r[0] for r in _rows if r and r[0]}
                    except Exception:
                        db_versions = set()

                    if _db_is_ahead_of_codebase(db_versions, backend_dir):
                        log.warning(
                            "Database schema is ahead of this image version — "
                            "the database was previously migrated by a newer build "
                            "(e.g. the dev image).  Alembic cannot upgrade because "
                            "it does not recognise the current head revision.  "
                            "The extra schema is additive and this image can run "
                            "safely, but some newer features will not be available.  "
                            "To fully restore, either upgrade back to the newer image "
                            "or restore from the pre-migration backup created at startup.",
                            db_versions=sorted(db_versions),
                            alembic_stderr=result.stderr.strip(),
                            backup_path=backup_path or "none (backup failed or DB was new)",
                        )
                        # Fall through — _verify_schema below will also detect
                        # the ahead-case and warn rather than raise.
                    else:
                        log.error(
                            "Database migration failed",
                            error=result.stderr,
                            output=result.stdout,
                        )
                        raise RuntimeError("Database migration failed")
                else:
                    log.error(
                        "Database migration failed",
                        error=result.stderr,
                        output=result.stdout,
                    )
                    raise RuntimeError("Database migration failed")
        except subprocess.TimeoutExpired:
            log.error("Database migration timed out after 60 seconds")
            raise
        except RuntimeError:
            raise
        except Exception as e:
            log.error("Failed to run database migrations", error=str(e))
            raise

        log.info("Verifying database schema...")
        await _verify_schema(backend_dir, db_path)
        log.info("Database schema verification completed")

    # Initialize connection pool
    _db_pool = DatabasePool(db_path, pool_size=DEFAULT_DB_POOL_SIZE)
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
        async with aiosqlite.connect(_get_db_path()) as db:
            await db.execute("PRAGMA journal_mode=WAL;")
            await db.execute("PRAGMA synchronous=NORMAL;")
            await db.execute("PRAGMA foreign_keys=ON;")
            await db.execute(f"PRAGMA busy_timeout={DEFAULT_DB_BUSY_TIMEOUT_MS};")
            yield db
        return

    conn = await _db_pool.acquire()
    try:
        yield conn
    finally:
        await _db_pool.release(conn)
