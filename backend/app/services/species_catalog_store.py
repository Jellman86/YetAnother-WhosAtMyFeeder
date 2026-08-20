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


def ensure_catalog_ready(catalog_path: Path | None = None, seed_path: Path | None = None) -> CatalogStatus:
    """Migrate an existing catalogue, or seed a genuinely fresh install."""
    path = Path(catalog_path or default_catalog_path())
    seed = Path(seed_path or DEFAULT_SEED_PATH)

    try:
        if path.is_file():
            upgrade_catalog(path)
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


async def start_species_catalog() -> None:
    """Startup phase wrapper: never raises, reports the outcome."""
    import asyncio

    status = await asyncio.to_thread(ensure_catalog_ready)
    log.info("Species catalogue startup state", state=status.state.value, path=status.path, detail=status.detail)
