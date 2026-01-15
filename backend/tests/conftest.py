"""Pytest configuration and fixtures for all tests."""
import os
import tempfile
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
    os.environ["DB_PATH"] = os.path.join(temp_dir, "test_speciesid.db")

    # Cleanup is handled by tempfile when process exits
