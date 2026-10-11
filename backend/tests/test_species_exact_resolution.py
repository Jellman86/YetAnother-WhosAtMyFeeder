"""Names selected by species search must resolve exactly when a counted bird is saved."""

import os
from contextlib import closing
import sqlite3

import aiosqlite
import pytest
import pytest_asyncio

from app.repositories.species_repository import SpeciesRepository


@pytest_asyncio.fixture
async def repository(tmp_path):
    path = tmp_path / "species.db"
    with closing(sqlite3.connect(os.environ["DB_PATH"])) as source, closing(sqlite3.connect(path)) as target:
        source.backup(target)
        target.execute("DELETE FROM detections")
        target.execute("DELETE FROM taxonomy_translations")
        target.execute("DELETE FROM taxonomy_cache")
        target.commit()
    async with aiosqlite.connect(path) as db:
        yield SpeciesRepository(db)


@pytest.mark.asyncio
@pytest.mark.parametrize("label", ["Dunnock (Prunella modularis)", "Prunella modularis (Dunnock)"])
@pytest.mark.parametrize("name", ["Prunella modularis", "Dunnock", "dunnock"])
async def test_uncached_compound_model_label_accepts_complete_scientific_and_common_names(repository, label, name):
    assert await repository.resolve_exact_species(name, [label]) == "Prunella modularis"


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["Dun", "Prunella", "modularis"])
async def test_uncached_compound_model_label_rejects_partial_names(repository, name):
    assert await repository.resolve_exact_species(name, ["Dunnock (Prunella modularis)"]) is None


@pytest.mark.asyncio
async def test_uncached_model_common_name_collision_is_ambiguous(repository):
    labels = ["Robin (Erithacus rubecula)", "Robin (Turdus migratorius)"]
    assert await repository.resolve_exact_species("Robin", labels) is None
    assert await repository.resolve_exact_species("Erithacus rubecula", labels) == "Erithacus rubecula"


@pytest.mark.asyncio
async def test_cached_and_model_common_name_collision_is_ambiguous(repository):
    await repository.db.execute(
        "INSERT INTO taxonomy_cache (scientific_name,common_name,taxa_id) VALUES ('Erithacus rubecula','Robin',1)"
    )
    assert await repository.resolve_exact_species("Robin", ["Robin (Turdus migratorius)"]) is None


@pytest.mark.asyncio
async def test_bare_model_common_name_uses_cached_canonical_identity(repository):
    await repository.db.execute(
        "INSERT INTO taxonomy_cache (scientific_name,common_name,taxa_id) VALUES ('Prunella modularis','Dunnock',1)"
    )
    assert await repository.resolve_exact_species("Dunnock", ["Dunnock"]) == "Prunella modularis"


@pytest.mark.asyncio
async def test_case_variants_do_not_mask_an_ambiguous_common_name(repository):
    await repository.db.executemany(
        "INSERT INTO taxonomy_cache (scientific_name,common_name,taxa_id) VALUES (?,'Robin',?)",
        [("ERITHACUS RUBECULA", 1), ("Erithacus Rubecula", 2), ("Erithacus rubecula", 3), ("Turdus migratorius", 4)],
    )
    assert await repository.resolve_exact_species("Robin", []) is None


@pytest.mark.asyncio
async def test_selected_scientific_identity_takes_precedence_over_another_common_name(repository):
    await repository.db.executemany(
        "INSERT INTO taxonomy_cache (scientific_name,common_name,taxa_id) VALUES (?,?,?)",
        [("Prunella modularis", "Dunnock", 1), ("Turdus migratorius", "Prunella modularis", 2)],
    )
    assert await repository.resolve_exact_species("Prunella modularis", []) == "Prunella modularis"


@pytest.mark.asyncio
async def test_bare_model_scientific_identity_takes_precedence_over_another_common_name(repository):
    await repository.db.execute(
        "INSERT INTO taxonomy_cache (scientific_name,common_name,taxa_id) VALUES ('Turdus migratorius','Prunella modularis',1)"
    )
    assert await repository.resolve_exact_species("Prunella modularis", ["Prunella modularis"]) == "Prunella modularis"
