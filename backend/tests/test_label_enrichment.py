"""Mapping the models whose labels are common names only.

`flexivit_il_all` and the European models carry no scientific name in their
labels, so nothing can be derived from the file alone and they map at zero. A
common name can be resolved to a scientific one at build time, once, against
sources that are already present.
"""

import pytest

from app.services.label_enrichment import enrich_unmapped_labels, resolve_common_name
from app.services.label_integrity import LabelCheck, LabelVerdict
from app.services.model_taxon_map import ModelTaxonMap


@pytest.fixture
def mapping(tmp_path):
    return ModelTaxonMap(tmp_path / "map.db")


def _check(labels, verdict=LabelVerdict.VERIFIED, key="labels-1"):
    return LabelCheck("eu_medium_focalnet_b", verdict, key, key, len(labels), tuple(labels))


@pytest.fixture
def sources(monkeypatch):
    """The bundled reference answers offline; eBird covers the rest."""
    from app.services import label_enrichment as module

    class Reference:
        def lookup(self, name):
            if str(name).casefold() == "american robin":
                return {"scientific_name": "Turdus migratorius", "common_name": "American Robin"}
            return None

    async def get_taxonomy(locale=None):
        return [
            {"sciName": "Cyanistes teneriffae", "comName": "African Blue Tit", "category": "species"},
            {"sciName": "Sitta ledanti", "comName": "Kabylian Nuthatch", "category": "species"},
            {"sciName": "Anas platyrhynchos/rubripes", "comName": "Mallard/Black Duck", "category": "slash"},
        ]

    from app.services import ebird_service as ebird_module

    monkeypatch.setattr(module, "species_reference", Reference())
    monkeypatch.setattr(ebird_module.ebird_service, "get_taxonomy", get_taxonomy)


@pytest.mark.asyncio
async def test_resolves_a_common_name_from_the_bundled_reference_without_the_network(sources):
    assert await resolve_common_name("American robin") == "Turdus migratorius"


@pytest.mark.asyncio
async def test_resolves_a_common_name_from_ebird_when_the_reference_does_not_have_it(sources):
    assert await resolve_common_name("African blue tit") == "Cyanistes teneriffae"


@pytest.mark.asyncio
async def test_matching_ignores_case(sources):
    assert await resolve_common_name("AFRICAN BLUE TIT") == "Cyanistes teneriffae"


@pytest.mark.asyncio
async def test_a_name_no_source_knows_stays_unresolved(sources):
    assert await resolve_common_name("Not A Real Bird") is None
    assert await resolve_common_name("") is None
    assert await resolve_common_name(None) is None


@pytest.mark.asyncio
async def test_a_slash_form_is_not_offered_as_a_species(sources):
    """eBird returns pair and spuh forms a classifier can never emit."""
    assert await resolve_common_name("Mallard/Black Duck") is None


@pytest.mark.asyncio
async def test_fills_in_the_indices_the_label_file_could_not(mapping, sources):
    labels = ["African blue tit", "Kabylian nuthatch", "Not A Real Bird"]
    check = _check(labels)
    mapping.build(check.actual_sha256, labels)
    assert mapping.coverage(check.actual_sha256)["mapped"] == 0

    filled = await enrich_unmapped_labels(check, mapping=mapping)

    assert filled == 2
    assert mapping.lookup(check.actual_sha256, 0) == "Cyanistes teneriffae"
    assert mapping.lookup(check.actual_sha256, 1) == "Sitta ledanti"
    assert mapping.lookup(check.actual_sha256, 2) is None


@pytest.mark.asyncio
async def test_an_index_already_mapped_is_left_alone(mapping, sources):
    """The label file is the better authority; enrichment only fills gaps."""
    labels = ["Turdus migratorius", "African blue tit"]
    check = _check(labels)
    mapping.build(check.actual_sha256, labels, assume_scientific=True)
    assert mapping.lookup(check.actual_sha256, 0) == "Turdus migratorius"

    await enrich_unmapped_labels(check, mapping=mapping)

    assert mapping.lookup(check.actual_sha256, 0) == "Turdus migratorius"
    assert mapping.lookup(check.actual_sha256, 1) == "Cyanistes teneriffae"


@pytest.mark.asyncio
async def test_a_changed_label_file_is_not_enriched(mapping, sources):
    check = _check(["African blue tit"], verdict=LabelVerdict.CHANGED)

    assert await enrich_unmapped_labels(check, mapping=mapping) == 0


@pytest.mark.asyncio
async def test_a_fully_mapped_model_costs_no_lookups(mapping, monkeypatch):
    from app.services import label_enrichment as module

    calls: list[str] = []

    async def should_not_run(name):
        calls.append(name)
        return None

    monkeypatch.setattr(module, "resolve_common_name", should_not_run)
    labels = ["04815_Animalia_Chordata_Aves_Passeriformes_Paridae_Cyanistes_caeruleus"]
    check = _check(labels)
    mapping.build(check.actual_sha256, labels)

    assert await enrich_unmapped_labels(check, mapping=mapping) == 0
    assert calls == []
