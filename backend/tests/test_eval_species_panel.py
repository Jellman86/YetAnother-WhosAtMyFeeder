"""Tests for backend/app/services/eval/species_panel.py."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.eval import species_panel
from app.services.eval.species_panel import (
    SpeciesEntry,
    fetch_regional_species,
    load_shared_core_seed,
    merge_panel,
    resolve_shared_core,
)


def test_shared_core_seed_loads_and_has_entries():
    seed = load_shared_core_seed()
    assert isinstance(seed, list)
    assert len(seed) >= 30
    for row in seed:
        assert "scientific_name" in row
        assert "common_name" in row


@pytest.mark.asyncio
async def test_resolve_shared_core_uses_seed_taxa_id_when_present():
    seed = [{"scientific_name": "X y", "common_name": "X", "taxa_id": 999}]
    with patch.object(species_panel, "_resolve_taxa_id_via_taxonomy_service", AsyncMock()) as inat:
        out = await resolve_shared_core(client=MagicMock(), seed=seed, inter_lookup_delay_seconds=0)
    assert len(out) == 1
    assert out[0].taxa_id == 999
    assert out[0].panel == "shared_core"
    inat.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_shared_core_calls_inat_when_taxa_missing():
    seed = [{"scientific_name": "Passer domesticus", "common_name": "House Sparrow"}]
    with patch.object(
        species_panel, "_resolve_taxa_id_via_taxonomy_service", AsyncMock(return_value=12345)
    ):
        out = await resolve_shared_core(client=MagicMock(), seed=seed, inter_lookup_delay_seconds=0)
    assert len(out) == 1
    assert out[0].taxa_id == 12345


@pytest.mark.asyncio
async def test_resolve_shared_core_skips_unresolvable():
    seed = [
        {"scientific_name": "Real bird", "common_name": "Real"},
        {"scientific_name": "Made up", "common_name": "Fake"},
    ]
    async def fake_lookup(name):
        return 1 if name == "Real bird" else None
    with patch.object(species_panel, "_resolve_taxa_id_via_taxonomy_service", AsyncMock(side_effect=fake_lookup)):
        out = await resolve_shared_core(client=MagicMock(), seed=seed, inter_lookup_delay_seconds=0)
    assert [s.scientific_name for s in out] == ["Real bird"]


@pytest.mark.asyncio
async def test_fetch_regional_species_parses_payload():
    fake_resp = MagicMock()
    fake_resp.json.return_value = {
        "results": [
            {"taxon": {"id": 11, "name": "Aaa bbb", "preferred_common_name": "AB"}},
            {"taxon": {"id": 12, "name": "Ccc ddd"}},  # no common name
            {"taxon": {"name": "no id here"}},
        ]
    }
    fake_resp.raise_for_status = MagicMock()
    fake_client = MagicMock()
    fake_client.get = AsyncMock(return_value=fake_resp)

    out = await fetch_regional_species(
        fake_client, latitude=10.0, longitude=20.0, count=10
    )
    assert len(out) == 2
    assert out[0].taxa_id == 11
    assert out[0].common_name == "AB"
    assert out[0].panel == "regional"
    assert out[1].common_name == ""


def test_merge_panel_dedupes_by_taxa_id():
    core = [SpeciesEntry(1, "A a", "A", "shared_core"), SpeciesEntry(2, "B b", "B", "shared_core")]
    regional = [
        SpeciesEntry(2, "B b", "B", "regional"),  # duplicate of core
        SpeciesEntry(3, "C c", "C", "regional"),
    ]
    merged = merge_panel(core, regional)
    by_taxa = {e.taxa_id: e for e in merged}
    assert by_taxa[2].panel == "shared_core"  # core wins
    assert by_taxa[3].panel == "regional"
    assert len(merged) == 3


def test_merge_panel_preserves_core_when_regional_empty():
    core = [SpeciesEntry(1, "A a", "A", "shared_core")]
    merged = merge_panel(core, [])
    assert len(merged) == 1


@pytest.mark.asyncio
async def test_build_panel_falls_back_to_core_only_when_no_coords():
    seed = [{"scientific_name": "X y", "common_name": "X", "taxa_id": 1}]
    with patch.object(species_panel, "load_shared_core_seed", return_value=seed):
        out = await species_panel.build_panel(latitude=None, longitude=None)
    assert len(out) == 1
    assert out[0].panel == "shared_core"
