"""Secret-bearing configuration writes preserve data and private file permissions."""

import json
import os
from pathlib import Path
import stat
from unittest.mock import patch

import pytest

from app import config
from app.config import settings
from app.config_loader import _persist_generated_auth_secret


pytestmark = pytest.mark.skipif(os.name == "nt", reason="POSIX file permissions and symbolic links")


@pytest.mark.asyncio
@pytest.mark.parametrize("existing", [False, True])
async def test_settings_save_is_private_even_with_a_public_umask(tmp_path: Path, monkeypatch, existing: bool):
    destination = tmp_path / "config.json"
    if existing:
        destination.write_text("{}")
        destination.chmod(0o644)
    monkeypatch.setattr(config, "CONFIG_PATH", destination)
    candidate = settings.model_copy(deep=True)
    candidate.api_key = "fixture-private-api-key"
    previous = os.umask(0o022)
    try:
        await candidate.save()
    finally:
        os.umask(previous)
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    assert json.loads(destination.read_text())["api_key"] == "fixture-private-api-key"


@pytest.mark.asyncio
async def test_settings_save_does_not_follow_a_predictable_temporary_symlink(tmp_path: Path, monkeypatch):
    destination = tmp_path / "config.json"
    unrelated = tmp_path / "unrelated.txt"
    unrelated.write_text("keep this data")
    destination.with_suffix(".json.tmp").symlink_to(unrelated)
    monkeypatch.setattr(config, "CONFIG_PATH", destination)
    await settings.model_copy(deep=True).save()
    assert unrelated.read_text() == "keep this data"
    assert json.loads(destination.read_text())["auth"]


def test_generated_auth_secret_is_persisted_privately(tmp_path: Path):
    destination = tmp_path / "config.json"
    destination.write_text('{"retained": "keep"}')
    destination.chmod(0o644)
    previous = os.umask(0o022)
    try:
        assert _persist_generated_auth_secret(destination, "session_secret", "fixture-secret")
    finally:
        os.umask(previous)
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    assert json.loads(destination.read_text()) == {"retained": "keep", "auth": {"session_secret": "fixture-secret"}}


@pytest.mark.asyncio
async def test_failed_settings_replace_preserves_the_original_and_removes_private_temporary_files(
    tmp_path: Path, monkeypatch
):
    destination = tmp_path / "config.json"
    original = '{"auth": {"session_secret": "original"}}'
    destination.write_text(original)
    monkeypatch.setattr(config, "CONFIG_PATH", destination)
    with patch("os.replace", side_effect=OSError("fixture replacement failure")):
        with pytest.raises(OSError):
            await settings.model_copy(deep=True).save()
    assert destination.read_text() == original
    assert list(tmp_path.iterdir()) == [destination]
