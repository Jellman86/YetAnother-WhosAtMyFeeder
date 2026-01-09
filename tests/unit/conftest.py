"""
Pytest configuration for unit tests.
"""
import sys
import os
from pathlib import Path

# Add backend directory to Python path so we can import modules
backend_dir = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

# Mock environment variables for testing
os.environ.setdefault("DB_PATH", ":memory:")
os.environ.setdefault("CONFIG_PATH", "/tmp/test_config.json")
