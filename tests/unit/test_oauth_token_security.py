from datetime import datetime

import aiosqlite
import pytest


SCHEMA_SQL = """
CREATE TABLE oauth_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    email TEXT NOT NULL,
    access_token TEXT NOT NULL,
    refresh_token TEXT,
    token_type TEXT,
    expires_at DATETIME,
    scope TEXT,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);
"""


async def _create_oauth_db(path: str) -> None:
    async with aiosqlite.connect(path) as db:
        await db.execute(SCHEMA_SQL)
        await db.commit()


@pytest.mark.asyncio
async def test_smtp_oauth_tokens_are_encrypted_at_rest(tmp_path, monkeypatch):
    from app.config import settings
    from app.services.smtp_service import smtp_service

    db_path = str(tmp_path / "oauth-smtp.db")
    monkeypatch.setenv("DB_PATH", db_path)
    monkeypatch.setattr(settings.auth, "session_secret", "unit-test-session-secret", raising=False)
    monkeypatch.setattr(settings.auth, "oauth_token_secret", "unit-test-oauth-secret", raising=False)
    await _create_oauth_db(db_path)

    stored = await smtp_service.store_oauth_token(
        provider="gmail",
        email="bird@example.com",
        access_token="access-plain",
        refresh_token="refresh-plain",
        expires_in=3600,
        scope="scope-a",
    )

    assert stored is True

    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT access_token, refresh_token FROM oauth_tokens WHERE provider = ?",
            ("gmail",),
        ) as cursor:
            row = await cursor.fetchone()

    assert row is not None
    assert row[0] != "access-plain"
    assert row[1] != "refresh-plain"

    token = await smtp_service._get_oauth_token("gmail")
    assert token is not None
    assert token["access_token"] == "access-plain"
    assert token["refresh_token"] == "refresh-plain"


@pytest.mark.asyncio
async def test_smtp_oauth_tokens_upgrade_legacy_plaintext_rows(tmp_path, monkeypatch):
    from app.config import settings
    from app.services.smtp_service import smtp_service

    db_path = str(tmp_path / "oauth-legacy.db")
    monkeypatch.setenv("DB_PATH", db_path)
    monkeypatch.setattr(settings.auth, "session_secret", "unit-test-session-secret", raising=False)
    monkeypatch.setattr(settings.auth, "oauth_token_secret", "unit-test-oauth-secret", raising=False)
    await _create_oauth_db(db_path)

    async with aiosqlite.connect(db_path) as db:
        now = datetime.utcnow()
        await db.execute(
            """
            INSERT INTO oauth_tokens (
                provider, email, access_token, refresh_token, token_type, expires_at, scope, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "gmail",
                "legacy@example.com",
                "legacy-access",
                "legacy-refresh",
                "Bearer",
                now,
                "scope-a",
                now,
                now,
            ),
        )
        await db.commit()

    token = await smtp_service._get_oauth_token("gmail")

    assert token is not None
    assert token["access_token"] == "legacy-access"
    assert token["refresh_token"] == "legacy-refresh"

    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT access_token, refresh_token FROM oauth_tokens WHERE provider = ?",
            ("gmail",),
        ) as cursor:
            row = await cursor.fetchone()

    assert row is not None
    assert row[0] != "legacy-access"
    assert row[1] != "legacy-refresh"


@pytest.mark.asyncio
async def test_inaturalist_tokens_are_encrypted_and_logout_clears_all_oauth_rows(tmp_path, monkeypatch):
    from app.config import settings
    from app.auth import AuthContext, AuthLevel
    from app.routers.auth import logout
    from app.services.inaturalist_service import inaturalist_service
    from app.services.smtp_service import smtp_service

    db_path = str(tmp_path / "oauth-logout.db")
    monkeypatch.setenv("DB_PATH", db_path)
    monkeypatch.setattr(settings.auth, "session_secret", "unit-test-session-secret", raising=False)
    monkeypatch.setattr(settings.auth, "oauth_token_secret", "unit-test-oauth-secret", raising=False)
    await _create_oauth_db(db_path)

    await smtp_service.store_oauth_token(
        provider="outlook",
        email="smtp@example.com",
        access_token="smtp-access",
        refresh_token="smtp-refresh",
        expires_in=3600,
        scope="smtp-scope",
    )
    await inaturalist_service.store_token(
        email="inat@example.com",
        access_token="inat-access",
        refresh_token="inat-refresh",
        token_type="Bearer",
        expires_in=3600,
        scope="inat-scope",
    )

    token = await inaturalist_service.get_token()
    assert token is not None
    assert token["access_token"] == "inat-access"
    assert token["refresh_token"] == "inat-refresh"

    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT access_token, refresh_token FROM oauth_tokens WHERE provider = ?",
            ("inaturalist",),
        ) as cursor:
            row = await cursor.fetchone()

    assert row is not None
    assert row[0] != "inat-access"
    assert row[1] != "inat-refresh"

    response = await logout(auth=AuthContext(AuthLevel.OWNER, username="owner"))
    assert response["message"].startswith("Logged out successfully")

    async with aiosqlite.connect(db_path) as db:
        async with db.execute("SELECT COUNT(*) FROM oauth_tokens") as cursor:
            count_row = await cursor.fetchone()

    assert count_row[0] == 0


@pytest.mark.asyncio
async def test_oauth_tokens_use_dedicated_secret_not_session_secret(tmp_path, monkeypatch):
    from app.config import settings
    from app.services.smtp_service import smtp_service

    db_path = str(tmp_path / "oauth-key-rotation.db")
    monkeypatch.setenv("DB_PATH", db_path)
    monkeypatch.setattr(settings.auth, "session_secret", "session-secret-a", raising=False)
    monkeypatch.setattr(settings.auth, "oauth_token_secret", "dedicated-oauth-secret", raising=False)
    await _create_oauth_db(db_path)

    stored = await smtp_service.store_oauth_token(
        provider="gmail",
        email="bird@example.com",
        access_token="access-plain",
        refresh_token="refresh-plain",
        expires_in=3600,
        scope="scope-a",
    )
    assert stored is True

    monkeypatch.setattr(settings.auth, "session_secret", "session-secret-b", raising=False)

    token = await smtp_service._get_oauth_token("gmail")
    assert token is not None
    assert token["access_token"] == "access-plain"
    assert token["refresh_token"] == "refresh-plain"
