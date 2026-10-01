import os

import pytest

from app.database import _assert_db_path_writable, get_db_path_diagnostics
from app.services.media_cache import MediaCacheService


@pytest.fixture
def non_posix(monkeypatch):
    monkeypatch.delattr(os, "getuid", raising=False)
    monkeypatch.delattr(os, "getgid", raising=False)


def test_database_diagnostics_keep_path_details_without_posix_identity(tmp_path, non_posix, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))

    diagnostics = get_db_path_diagnostics()

    assert diagnostics["parent_exists"] is True
    assert diagnostics["parent_writable"] is True
    assert diagnostics["process_uid_gid"] is None


def test_database_permission_error_retains_its_cause_without_posix_identity(tmp_path, non_posix, monkeypatch):
    monkeypatch.setattr(os, "access", lambda *args: False)

    with pytest.raises(RuntimeError, match="not writable by current process"):
        _assert_db_path_writable(str(tmp_path / "test.db"))


def test_media_diagnostics_are_available_without_posix_identity(non_posix):
    diagnostics = MediaCacheService().get_status()

    assert diagnostics["process_uid_gid"] is None


def test_failed_cache_initialization_remains_nonfatal_without_posix_identity(non_posix, monkeypatch):
    def unavailable(self):
        raise PermissionError("Cache directory denied")

    monkeypatch.setattr(MediaCacheService, "_ensure_dirs", unavailable)

    diagnostics = MediaCacheService().get_status()

    assert diagnostics["available"] is False
    assert diagnostics["init_error"] == "Cache directory denied"
