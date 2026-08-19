"""Localized bird names held beside the application database.

The bundled species reference ships English names only, and
`taxonomy_translations` is keyed on an iNaturalist taxon id the reference does
not have. This store is keyed on scientific name instead, so a species resolved
from the bundled reference can still be named in the owner's language.

It is populated in bulk from eBird while the network is available, which is what
makes a localized name survive an outage or an offline install.

The contents are reproducible: losing the file costs one refresh. That is why it
sits beside the application database rather than inside it, and why it carries no
Alembic migration. It is a cache of a public reference, not user data.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

import structlog

log = structlog.get_logger()

SCHEMA = """
CREATE TABLE IF NOT EXISTS species_name (
    scientific_name TEXT NOT NULL,
    locale          TEXT NOT NULL,
    common_name     TEXT NOT NULL,
    PRIMARY KEY (scientific_name, locale)
);
CREATE TABLE IF NOT EXISTS locale_refresh (
    locale       TEXT PRIMARY KEY,
    refreshed_at TEXT NOT NULL
);
"""


def default_store_path() -> Path:
    """Beside the application database, wherever that has been configured."""
    configured = os.environ.get("DB_PATH")
    if configured:
        return Path(configured).expanduser().resolve().parent / "species_names.db"
    return Path("/data/species_names.db")


def _key(value: Optional[str]) -> str:
    return str(value or "").strip().casefold()


class LocalizedNameStore:
    """A small writable SQLite file. Never raises into the naming path."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = Path(path) if path is not None else default_store_path()
        self._connection: Optional[sqlite3.Connection] = None
        self._lock = threading.Lock()
        self._disabled = False

    def _parent_is_writable(self) -> bool:
        parent = self._path.parent
        return parent.is_dir() and os.access(parent, os.W_OK | os.X_OK)

    def _connect(self) -> Optional[sqlite3.Connection]:
        if self._disabled:
            return None
        if self._connection is not None:
            return self._connection
        with self._lock:
            if self._disabled:
                return None
            if self._connection is not None:
                return self._connection
            if not self._path.exists() and not self._parent_is_writable():
                log.info("Localized name store unavailable; names stay English", path=str(self._path))
                self._disabled = True
                return None
            try:
                connection = sqlite3.connect(self._path, check_same_thread=False)
                connection.row_factory = sqlite3.Row
                connection.executescript(SCHEMA)
                connection.commit()
            except sqlite3.Error as error:
                log.warning("Localized name store unusable; names stay English", error=str(error))
                self._disabled = True
                return None
            self._connection = connection
            return connection

    @property
    def available(self) -> bool:
        return self._connect() is not None

    def upsert_many(
        self,
        locale: str,
        entries: Iterable[tuple[Optional[str], Optional[str]]],
        english: Optional[dict[str, str]] = None,
    ) -> int:
        """Store localized names, returning how many were kept.

        `english` lets the caller pass the English names so an untranslated
        species is skipped. eBird returns the English name when it has no
        translation, and storing that would claim a translation we do not have.
        """
        locale_key = _key(locale)
        if not locale_key:
            return 0
        connection = self._connect()
        if connection is None:
            return 0

        rows: list[tuple[str, str, str]] = []
        for scientific, common in entries:
            scientific_key = _key(scientific)
            name = str(common or "").strip()
            if not scientific_key or not name:
                continue
            if english and english.get(scientific_key, "").strip().casefold() == name.casefold():
                continue
            rows.append((scientific_key, locale_key, name))

        if not rows:
            return 0

        try:
            connection.executemany(
                "INSERT INTO species_name (scientific_name, locale, common_name) VALUES (?, ?, ?)"
                " ON CONFLICT (scientific_name, locale) DO UPDATE SET common_name = excluded.common_name",
                rows,
            )
            connection.execute(
                "INSERT INTO locale_refresh (locale, refreshed_at) VALUES (?, ?)"
                " ON CONFLICT (locale) DO UPDATE SET refreshed_at = excluded.refreshed_at",
                (locale_key, datetime.now(timezone.utc).isoformat()),
            )
            connection.commit()
        except sqlite3.Error as error:
            log.warning("Could not store localized names", locale=locale_key, error=str(error))
            return 0
        return len(rows)

    def lookup(self, scientific_name: Optional[str], locale: Optional[str]) -> Optional[str]:
        scientific_key = _key(scientific_name)
        locale_key = _key(locale)
        if not scientific_key or not locale_key:
            return None
        connection = self._connect()
        if connection is None:
            return None
        try:
            row = connection.execute(
                "SELECT common_name FROM species_name WHERE scientific_name = ? AND locale = ?",
                (scientific_key, locale_key),
            ).fetchone()
        except sqlite3.Error as error:
            log.warning("Localized name lookup failed", error=str(error))
            return None
        return row["common_name"] if row else None

    def status(self) -> dict[str, object]:
        connection = self._connect()
        if connection is None:
            return {"available": False, "locales": {}, "refreshed_at": {}}
        try:
            locales = {
                row["locale"]: row["count"]
                for row in connection.execute(
                    "SELECT locale, COUNT(*) AS count FROM species_name GROUP BY locale"
                ).fetchall()
            }
            refreshed = {
                row["locale"]: row["refreshed_at"]
                for row in connection.execute("SELECT locale, refreshed_at FROM locale_refresh").fetchall()
            }
        except sqlite3.Error:
            return {"available": False, "locales": {}, "refreshed_at": {}}
        return {"available": True, "locales": locales, "refreshed_at": refreshed}


localized_names = LocalizedNameStore()


# ── Populating the store ─────────────────────────────────────────────────────

#: Refresh no more often than this. eBird's taxonomy changes roughly annually.
REFRESH_INTERVAL_SECONDS = 30 * 24 * 3600


def _needs_refresh(refreshed_at: Optional[str], now: Optional[datetime] = None) -> bool:
    if not refreshed_at:
        return True
    try:
        recorded = datetime.fromisoformat(refreshed_at)
    except (TypeError, ValueError):
        return True
    if recorded.tzinfo is None:
        recorded = recorded.replace(tzinfo=timezone.utc)
    reference = now or datetime.now(timezone.utc)
    return (reference - recorded).total_seconds() > REFRESH_INTERVAL_SECONDS


async def refresh_locale_from_ebird(locale: str, *, store: Optional[LocalizedNameStore] = None) -> int:
    """Pull one locale's taxonomy from eBird into the store.

    One bulk request, not one per species: pre-resolving species individually
    against a free community service is what the design rejected.
    """
    from app.services.ebird_service import ebird_service

    target = store or localized_names
    if not target.available:
        return 0

    try:
        english_items = await ebird_service.get_taxonomy("en")
        localized_items = await ebird_service.get_taxonomy(locale)
    except Exception as error:
        log.warning("Could not fetch eBird taxonomy", locale=locale, error=str(error))
        return 0

    english = {
        _key(item.get("sciName")): str(item.get("comName") or "")
        for item in english_items or []
        if isinstance(item, dict)
    }
    entries = [(item.get("sciName"), item.get("comName")) for item in localized_items or [] if isinstance(item, dict)]
    if not entries:
        return 0

    stored = target.upsert_many(locale, entries, english=english)
    log.info("Localized names refreshed from eBird", locale=locale, stored=stored)
    return stored


async def refresh_localized_names(
    locales: Iterable[str], *, store: Optional[LocalizedNameStore] = None, force: bool = False
) -> dict[str, int]:
    """Refresh the locales that are due, skipping the rest."""
    target = store or localized_names
    if not target.available:
        return {}

    refreshed_at = target.status().get("refreshed_at") or {}
    results: dict[str, int] = {}
    for locale in locales:
        locale_key = _key(locale)
        if not locale_key or locale_key == "en":
            continue
        if not force and not _needs_refresh(refreshed_at.get(locale_key)):  # type: ignore[union-attr]
            continue
        results[locale_key] = await refresh_locale_from_ebird(locale, store=target)
    return results


_background_task: Optional["asyncio.Task[None]"] = None


async def start_background_refresh() -> None:
    """Schedule a refresh of the configured locale without holding up startup.

    Fetching a whole taxonomy is one request but a large response, so it runs
    detached. A failure costs the localized names and nothing else.
    """
    global _background_task

    from app.config import settings
    from app.services.ebird_service import ebird_service

    locale = _key(settings.ebird.locale)
    if not locale or locale == "en":
        return
    if not ebird_service.is_configured():
        log.debug("eBird not configured; localized names will not be refreshed")
        return

    async def run() -> None:
        try:
            await refresh_localized_names([locale])
        except Exception as error:  # pragma: no cover - guarded by the caller's phase
            log.warning("Localized name refresh failed", locale=locale, error=str(error))

    _background_task = asyncio.create_task(run())
