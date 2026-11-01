"""Every in-process settings change takes the staged writer boundary.

A settings save copies the live configuration, persists the copy and then publishes it.
A change made directly to the live object while that save is in flight is overwritten by
the publication, and a temporary value placed on the live object can be copied into the
saved file. These tests pin the rule that nothing writes the live settings except
through ``commit_settings_change`` / ``apply_update``.
"""

import asyncio
import json
import re
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import BackgroundTasks

import app.config as config_module
from app.auth import AuthContext, AuthLevel, require_owner
from app.config import Settings, settings
from app.main import app
from app.routers import settings as settings_router
from app.services import settings_update
from app.services.notification_service import notification_service
from app.services.settings_update import commit_settings_change

OWNER = AuthContext(auth_level=AuthLevel.OWNER, username="test")
APP_DIR = Path(__file__).resolve().parents[1] / "app"


@pytest.fixture
def isolated_settings(monkeypatch, tmp_path):
    monkeypatch.setattr(settings_update, "settings_update_lock", asyncio.Lock())
    monkeypatch.setattr(config_module, "CONFIG_PATH", tmp_path / "config.json")
    snapshot = settings.model_copy(deep=True)
    yield
    for field in Settings.model_fields:
        setattr(settings, field, getattr(snapshot, field))


@pytest.mark.asyncio
async def test_programmatic_change_waits_for_an_inflight_save_and_is_not_reverted(monkeypatch, isolated_settings):
    settings.public_access.enabled = False
    settings.classification.model = "before"
    await settings.save()
    entered, release = asyncio.Event(), asyncio.Event()
    original_save = Settings.save
    saves = 0

    async def controlled_save(candidate):
        nonlocal saves
        saves += 1
        if saves == 1:
            entered.set()
            await release.wait()
        await original_save(candidate)

    monkeypatch.setattr(Settings, "save", controlled_save)
    monkeypatch.setattr("app.services.broadcaster.broadcaster.broadcast", AsyncMock())

    def select_model(candidate: Settings) -> None:
        candidate.classification.model = "after"

    update = asyncio.create_task(
        settings_router.update_settings(
            settings_router.SettingsUpdate(public_access_enabled=True), BackgroundTasks(), OWNER
        )
    )
    change = None
    try:
        await asyncio.wait_for(entered.wait(), 5)
        change = asyncio.create_task(commit_settings_change(select_model))
        await asyncio.sleep(0)
        assert saves == 1
        assert settings.classification.model == "before"
        release.set()
        await asyncio.wait_for(asyncio.gather(update, change), 5)
    finally:
        release.set()
        await asyncio.gather(update, *([change] if change else []), return_exceptions=True)

    assert saves == 2
    assert settings.public_access.enabled is True
    assert settings.classification.model == "after"
    assert json.loads(config_module.CONFIG_PATH.read_text()) == settings.model_dump(mode="json")


@pytest.mark.asyncio
async def test_failed_programmatic_change_leaves_memory_and_references_unchanged(monkeypatch, isolated_settings):
    before = settings.model_dump(mode="json")
    classification = settings.classification
    monkeypatch.setattr(Settings, "save", AsyncMock(side_effect=OSError("disk full")))

    def select_model(candidate: Settings) -> None:
        candidate.classification.model = "never_published"

    with pytest.raises(OSError, match="disk full"):
        await commit_settings_change(select_model)

    assert settings.model_dump(mode="json") == before
    assert settings.classification is classification


@pytest.mark.asyncio
async def test_rejected_programmatic_change_saves_nothing(monkeypatch, isolated_settings):
    save = AsyncMock()
    monkeypatch.setattr(Settings, "save", save)
    before = settings.model_dump(mode="json")

    def refuse(candidate: Settings) -> None:
        candidate.classification.model = "half_applied"
        raise ValueError("not allowed")

    with pytest.raises(ValueError, match="not allowed"):
        await commit_settings_change(refuse)

    save.assert_not_awaited()
    assert settings.model_dump(mode="json") == before


@pytest.mark.asyncio
async def test_model_activation_save_failure_keeps_the_previous_selection(monkeypatch, isolated_settings):
    from app.routers import models as models_router

    target = type("Installed", (), {"id": "next_model", "validated": True, "metadata": None})()

    async def installed():
        return [target]

    monkeypatch.setattr(models_router, "_reject_retired_model", lambda _model_id: None)
    monkeypatch.setattr(models_router, "_require_classifier_artifact", lambda _model: None)
    monkeypatch.setattr(models_router.model_manager, "list_installed_models", installed)
    monkeypatch.setattr(models_router.model_manager, "activate_model", AsyncMock(return_value=True))
    monkeypatch.setattr(models_router, "activation_provider_recommendation", lambda *_a, **_k: "intel_gpu")
    monkeypatch.setattr(Settings, "save", AsyncMock(side_effect=OSError("disk full")))
    settings.classification.model = "previous_model"
    settings.classification.inference_provider = "cpu"
    tasks = BackgroundTasks()

    with pytest.raises(OSError, match="disk full"):
        await models_router.activate_model("next_model", tasks, OWNER)

    assert settings.classification.model == "previous_model"
    assert settings.classification.inference_provider == "cpu"
    assert tasks.tasks == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "platform, sender, request_fields, live_fields",
    [
        ("discord", "_send_discord", {"webhook_url": "https://typed.example/hook"}, {"webhook_url"}),
        (
            "pushover",
            "_send_pushover",
            {"user_key": "typed-user", "api_token": "typed-token"},
            {"user_key", "api_token"},
        ),
        ("telegram", "_send_telegram", {"bot_token": "typed-bot", "chat_id": "typed-chat"}, {"bot_token", "chat_id"}),
    ],
)
async def test_notification_test_credentials_never_reach_live_settings(
    monkeypatch, isolated_settings, platform, sender, request_fields, live_fields
):
    """Typed but unapplied credentials go to the test send only, never the saved configuration."""
    channel = getattr(settings.notifications, platform)
    for field in live_fields:
        setattr(channel, field, f"saved-{field}")
    saved_live = channel.model_dump()
    seen: dict = {}

    async def send(*_args, **kwargs):
        seen["live"] = getattr(settings.notifications, platform).model_dump()
        seen["config"] = kwargs.get("config")
        return True

    monkeypatch.setattr(notification_service, sender, send)
    app.dependency_overrides[require_owner] = lambda: OWNER
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/settings/notifications/test", json={"platform": platform, **request_fields}
            )
    finally:
        app.dependency_overrides.pop(require_owner, None)

    assert response.status_code == 200, response.text
    assert seen["live"] == saved_live
    assert getattr(settings.notifications, platform).model_dump() == saved_live
    for field, value in request_fields.items():
        assert getattr(seen["config"], field) == value


@pytest.mark.asyncio
async def test_notification_test_without_overrides_uses_the_saved_channel(monkeypatch, isolated_settings):
    settings.notifications.discord.webhook_url = "https://saved.example/hook"
    seen: dict = {}

    async def send(*_args, **kwargs):
        seen["config"] = kwargs.get("config")
        return True

    monkeypatch.setattr(notification_service, "_send_discord", send)
    app.dependency_overrides[require_owner] = lambda: OWNER
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/settings/notifications/test",
                json={"platform": "discord", "webhook_url": "***REDACTED***"},
            )
    finally:
        app.dependency_overrides.pop(require_owner, None)

    assert response.status_code == 200, response.text
    assert seen["config"].webhook_url == "https://saved.example/hook"


@pytest.mark.asyncio
async def test_telemetry_rotation_persists_through_the_writer_and_falls_back_to_memory(monkeypatch, isolated_settings):
    from app.services.telemetry_service import TelemetryService

    service = TelemetryService()
    settings.telemetry.installation_id = "old-id"
    monkeypatch.setattr(Settings, "save", AsyncMock(side_effect=OSError("disk full")))

    persisted = await service._persist_installation_id(replacing="old-id")

    assert persisted is False
    assert settings.telemetry.installation_id not in (None, "old-id")


@pytest.mark.asyncio
async def test_telemetry_rotation_does_not_replace_an_identity_changed_meanwhile(isolated_settings, monkeypatch):
    from app.services.telemetry_service import TelemetryService

    monkeypatch.setattr(Settings, "save", AsyncMock())
    settings.telemetry.installation_id = "imported-id"

    persisted = await TelemetryService()._persist_installation_id(replacing="old-id")

    assert persisted is True
    assert settings.telemetry.installation_id == "imported-id"


def test_only_the_settings_writer_saves_the_live_settings():
    """A direct ``settings.save()`` would bypass the stage-persist-publish boundary."""
    writer = APP_DIR / "services" / "settings_update.py"
    direct_saves = [
        f"{path.relative_to(APP_DIR)}:{number}"
        for path in APP_DIR.rglob("*.py")
        if path != writer
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if re.search(r"\bsettings\.save\(", line)
    ]
    assert direct_saves == []
