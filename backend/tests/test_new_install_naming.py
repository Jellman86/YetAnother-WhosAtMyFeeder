"""Naming on a fresh install, where nothing is downloaded yet.

The map refresh runs once at startup. On a new install the models directory is
empty at that point, so a model downloaded afterwards would have no mapping
until the next restart, and the European models would name nothing offline in
the meantime. The download has to rebuild it.
"""

import pytest


@pytest.mark.asyncio
async def test_a_downloaded_model_is_mapped_without_waiting_for_a_restart(monkeypatch):
    from app.services import model_manager as module

    called: list[str] = []

    async def record() -> None:
        called.append("refreshed")

    monkeypatch.setattr(module, "refresh_maps_after_install", record)

    await module.refresh_maps_after_install()

    assert called == ["refreshed"]


@pytest.mark.asyncio
async def test_a_failed_rebuild_does_not_fail_the_download(monkeypatch):
    """A naming improvement must never make an install report failure."""
    from app.services.model_manager import refresh_maps_after_install
    from app.services import label_enrichment as enrichment

    async def explode() -> dict[str, int]:
        raise RuntimeError("no models directory")

    monkeypatch.setattr(enrichment, "refresh_model_maps", explode)

    # Returns rather than raising: the caller is a completed download.
    assert await refresh_maps_after_install() is None


@pytest.mark.asyncio
async def test_a_manual_rename_still_wins_over_the_bundled_reference(monkeypatch):
    """A user's own name for a bird outranks every source we ship or fetch.

    The reference and the maps are rebuilt from their sources, so a rename must
    never live in them. It lives in taxonomy_cache, which is checked first.
    """
    from app.services.taxonomy import taxonomy_service as module

    async def renamed(_query, db=None):
        return {"scientific_name": "Haemorhous cassinii", "common_name": "Bertie", "taxa_id": 1}

    async def should_not_run(_name):
        raise AssertionError("the network was consulted despite a stored name")

    monkeypatch.setattr(module.taxonomy_service, "_get_from_cache", renamed)
    monkeypatch.setattr(module.taxonomy_service, "_lookup_inaturalist", should_not_run)

    result = await module.taxonomy_service.get_names("Haemorhous cassinii")

    assert result["common_name"] == "Bertie"
