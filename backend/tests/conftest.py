"""Pytest configuration and fixtures for all tests."""
import os
import tempfile
import pytest
import pytest_asyncio
import sys
from pathlib import Path


def pytest_configure(config):
    """
    Configure pytest environment BEFORE test collection.
    This runs before any modules are imported, allowing us to set
    environment variables that affect module-level code.
    """
    # Create a temporary directory for test data
    temp_dir = tempfile.mkdtemp(prefix="yawamf_test_")

    # Set environment variables to use temp directory instead of /config
    os.environ["MEDIA_CACHE_DIR"] = os.path.join(temp_dir, "media_cache")
    os.environ["DATA_DIR"] = os.path.join(temp_dir, "data")
    os.environ["CONFIG_DIR"] = os.path.join(temp_dir, "config")
    os.environ["CONFIG_FILE"] = os.path.join(temp_dir, "config", "config.json")

    # Create necessary directories
    Path(os.environ["MEDIA_CACHE_DIR"]).mkdir(parents=True, exist_ok=True)
    Path(os.environ["DATA_DIR"]).mkdir(parents=True, exist_ok=True)
    Path(os.environ["CONFIG_DIR"]).mkdir(parents=True, exist_ok=True)

    # Set test database to use temp directory
    db_path = os.path.join(temp_dir, "test_speciesid.db")
    os.environ["DB_PATH"] = db_path

    # Initialize test database schema using Alembic
    backend_dir = Path(__file__).parent.parent.resolve()
    
    # We must ensure the backend_dir is in sys.path so alembic's env.py can find 'app'
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

    print(f"\nInitializing test database schema at {db_path}...")
    
    # Use synchronous subprocess to run alembic upgrade
    import subprocess
    env = os.environ.copy()
    env["PYTHONPATH"] = str(backend_dir)
    env["DB_PATH"] = db_path
    
    # Alembic usually looks for 'alembic.ini' in the current dir.
    # We'll run it from backend_dir.
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(backend_dir),
        env=env,
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        print(f"FAILED to initialize test database: {result.stderr}")
    else:
        print("Test database schema initialized successfully")

    # Flag to tell app.database.init_db to skip migrations if already done
    os.environ["YA_WAMF_TEST_DB_INITIALIZED"] = "1"

    # Cleanup is handled by tempfile when process exits


@pytest.fixture(autouse=True)
def disable_rate_limiting():
    """Disable rate limiting for all tests by default."""
    from app.ratelimit import limiter
    old_enabled = limiter.enabled
    limiter.enabled = False
    yield
    limiter.enabled = old_enabled


@pytest_asyncio.fixture(autouse=True)
async def cleanup_async_singletons():
    yield
    from app.services.notification_dispatcher import notification_dispatcher

    await notification_dispatcher.stop()



# All previously skipped tests have been fixed:
# - AudioService fixture updated to use settings instead of buffer_minutes parameter
# - detection_repository test schema updated with ai_analysis and ai_analysis_timestamp columns
# - event_processor tests use proper mocking and should work correctly
#
# Leaving this function commented out for reference:
# def pytest_collection_modifyitems(config, items):
#     """Skip pre-existing broken tests to allow CI/CD to pass."""
#     pass
