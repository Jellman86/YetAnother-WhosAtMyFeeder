"""Bring the species catalogue database into service at startup.

The image carries a checksum-pinned seed catalogue built at release time. On
startup the catalogue at `/data/species_catalog.db` is migrated if it exists,
or seeded from the image only when no catalogue has ever been initialised. An
initialisation marker beside the database distinguishes a genuinely fresh
install from a database that has gone missing: a catalogue may hold owner
enrichments and overrides, so replacing a lost one with the seed would be
silent data loss, not recovery. That case is reported and left for the owner.

Never fatal to startup: a missing or refused catalogue degrades naming, and
later phases fail closed for new species classification, but the application
must still come up to say so.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import structlog

from app.services.species_catalog_migrations import default_catalog_path, upgrade_catalog

log = structlog.get_logger()

DEFAULT_SEED_PATH = Path(__file__).resolve().parent.parent / "assets" / "species_catalog_seed.db"

_DIGEST_CHUNK_BYTES = 1024 * 1024


class CatalogState(str, Enum):
    READY = "ready"
    SEEDED = "seeded"
    INITIALIZED_EMPTY = "initialized_empty"
    MISSING = "missing"
    SEED_REJECTED = "seed_rejected"
    FAILED = "failed"


@dataclass(frozen=True)
class CatalogStatus:
    state: CatalogState
    path: str
    detail: str = ""


def _marker_path(catalog_path: Path) -> Path:
    return catalog_path.with_suffix(catalog_path.suffix + ".initialized")


def _seed_digest_ok(seed_path: Path) -> bool:
    """Refuse a seed that no longer matches the digest recorded beside it.

    A seed with no sidecar is accepted: absence is a local build, not
    corruption. This mirrors the bundled species reference's contract.
    """
    sidecar = seed_path.with_suffix(seed_path.suffix + ".sha256")
    if not sidecar.is_file():
        return True
    try:
        expected = sidecar.read_text(encoding="utf-8").split()[0].strip().lower()
    except (OSError, IndexError):
        log.warning("Seed catalogue digest unreadable; using the file as found", path=str(sidecar))
        return True
    if len(expected) != 64:
        log.warning("Seed catalogue digest malformed; using the file as found", path=str(sidecar))
        return True

    digest = hashlib.sha256()
    try:
        with open(seed_path, "rb") as handle:
            for chunk in iter(lambda: handle.read(_DIGEST_CHUNK_BYTES), b""):
                digest.update(chunk)
    except OSError as error:
        log.error("Seed catalogue unreadable", path=str(seed_path), error=str(error))
        return False
    if digest.hexdigest() != expected:
        log.error(
            "Seed catalogue does not match its recorded digest; refusing it",
            path=str(seed_path),
            expected=expected,
            actual=digest.hexdigest(),
        )
        return False
    return True


def _write_marker(catalog_path: Path) -> None:
    _marker_path(catalog_path).write_text(
        "The species catalogue at this path has been initialised. Its absence now means loss, not a fresh install.\n",
        encoding="utf-8",
    )


def _copy_seed_atomically(seed_path: Path, catalog_path: Path) -> None:
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    handle, staged = tempfile.mkstemp(prefix=".species_catalog_seed_", dir=catalog_path.parent)
    os.close(handle)
    try:
        shutil.copy2(seed_path, staged)
        os.replace(staged, catalog_path)
    except OSError:
        Path(staged).unlink(missing_ok=True)
        raise


def _is_empty_shell(catalog_path: Path) -> bool:
    """True when the catalogue holds no release, no species, and no owner data.

    An install that started from an image without a seed (the split backend
    image, or a dev checkout) initialises an empty migrated catalogue. There
    is nothing in it to lose, so a later image that does carry a seed may
    replace it — unlike a catalogue with any release or override, which is
    never touched.
    """
    try:
        connection = sqlite3.connect(f"file:{catalog_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return False
    try:
        for table in ("catalogue_releases", "species", "species_name_overrides"):
            if connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]:
                return False
        return True
    except sqlite3.Error:
        return False
    finally:
        connection.close()


def ensure_catalog_ready(catalog_path: Path | None = None, seed_path: Path | None = None) -> CatalogStatus:
    """Migrate an existing catalogue, or seed a genuinely fresh install."""
    path = Path(catalog_path or default_catalog_path())
    seed = Path(seed_path or DEFAULT_SEED_PATH)

    try:
        if path.is_file():
            upgrade_catalog(path)
            if seed.is_file() and _is_empty_shell(path) and _seed_digest_ok(seed):
                _copy_seed_atomically(seed, path)
                upgrade_catalog(path)
                _write_marker(path)
                log.info("Empty species catalogue replaced with the image seed", path=str(path), seed=str(seed))
                return CatalogStatus(CatalogState.SEEDED, str(path))
            if not _marker_path(path).is_file():
                _write_marker(path)
            return CatalogStatus(CatalogState.READY, str(path))

        if _marker_path(path).is_file():
            log.error(
                "Species catalogue was initialised before but is now missing; refusing to overwrite the loss "
                "with the seed. Restore it from backup, or remove the .initialized marker to accept a fresh start.",
                path=str(path),
            )
            return CatalogStatus(CatalogState.MISSING, str(path), "initialised before, file absent")

        if seed.is_file():
            if not _seed_digest_ok(seed):
                return CatalogStatus(CatalogState.SEED_REJECTED, str(path), "seed failed digest verification")
            _copy_seed_atomically(seed, path)
            upgrade_catalog(path)
            _write_marker(path)
            log.info("Species catalogue seeded from the image", path=str(path), seed=str(seed))
            return CatalogStatus(CatalogState.SEEDED, str(path))

        path.parent.mkdir(parents=True, exist_ok=True)
        upgrade_catalog(path)
        _write_marker(path)
        log.info("No seed catalogue shipped; initialised an empty migrated catalogue", path=str(path))
        return CatalogStatus(CatalogState.INITIALIZED_EMPTY, str(path))
    except Exception as error:
        log.error("Species catalogue initialisation failed", path=str(path), error=str(error))
        return CatalogStatus(CatalogState.FAILED, str(path), str(error))


def offer_seed_release(
    catalog_path: Path | None = None,
    seed_path: Path | None = None,
    *,
    importer=None,
) -> dict[str, object]:
    """Offer the shipped seed to an existing catalogue as a release.

    `ensure_catalog_ready` seeds only a genuinely fresh install, because a live
    catalogue may hold owner overrides and imported releases and replacing the
    file would lose them. The consequence was that a newer shipped catalogue
    never reached an existing install at all.

    The release importer is built for exactly this and was never called. It
    already verifies the schema head, that the bundle holds one release, its
    content digest and its foreign keys, and it returns `already_imported`
    when the digest is one the catalogue has seen, so offering the same seed on
    every startup costs a digest comparison.

    Never raises: a catalogue that cannot take a new release still serves the
    one it has.
    """
    path = Path(catalog_path or default_catalog_path())
    seed = Path(seed_path or DEFAULT_SEED_PATH)

    if not path.is_file():
        return {"status": "no_catalogue", "release_id": None, "detail": str(path)}
    if not seed.is_file():
        return {"status": "no_seed", "release_id": None, "detail": str(seed)}

    if importer is None:
        from app.services.species_catalog_importer import import_release

        importer = import_release

    try:
        result = importer(seed, path)
    except Exception as error:
        log.warning("Shipped catalogue release not imported", seed=str(seed), error=str(error))
        return {"status": "failed", "release_id": None, "detail": str(error)}

    return {
        "status": getattr(result, "status", "imported"),
        "release_id": getattr(result, "release_id", None),
        "detail": str(seed),
    }


async def start_species_catalog() -> None:
    """Startup phase wrapper: never raises, reports the outcome."""
    import asyncio

    status = await asyncio.to_thread(ensure_catalog_ready)
    log.info("Species catalogue startup state", state=status.state.value, path=status.path, detail=status.detail)

    # A fresh install has just taken the seed wholesale; an existing one is
    # offered it as a release so a newer shipped catalogue actually arrives.
    if status.state in {CatalogState.READY, CatalogState.SEEDED}:
        outcome = await asyncio.to_thread(offer_seed_release)
        _record_release_offer(outcome)
        log.info("Shipped catalogue release offer", **outcome)


_last_release_offer: dict[str, object] = {"status": "not_attempted", "release_id": None, "detail": ""}


def _record_release_offer(outcome: dict[str, object]) -> None:
    global _last_release_offer
    _last_release_offer = dict(outcome)


def last_release_offer() -> dict[str, object]:
    """What the most recent seed offer did, for the Health payload."""
    return dict(_last_release_offer)
