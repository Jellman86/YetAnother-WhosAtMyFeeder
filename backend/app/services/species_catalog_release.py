"""The canonical content identity of a catalogue release.

A release's `content_sha256` is a digest over its species, concepts, and
names in one canonical order, independent of how the rows were inserted. The
builder records it when a release is cut, and the importer recomputes it
before admitting a bundle, so a file altered after it was built cannot enter
a live catalogue as if it were the release it claims to be.
"""

from __future__ import annotations

import hashlib
import sqlite3


def connection_content_digest(connection: sqlite3.Connection) -> str:
    """Digest the catalogue content reachable from one connection.

    Canonical order, not insertion order: species by id and concept identity,
    names by species, language, and name. Bundles hold exactly one release, so
    the whole file is the release's content.
    """
    digest = hashlib.sha256()
    for species_id, scientific_name in connection.execute(
        "SELECT species_id, scientific_name FROM species_concepts ORDER BY species_id, provider, provider_taxon_id"
    ):
        digest.update(f"species|{species_id}|{scientific_name}\n".encode())
    for species_id, language_tag, name in connection.execute(
        "SELECT species_id, language_tag, name FROM species_names ORDER BY species_id, language_tag, name"
    ):
        digest.update(f"name|{species_id}|{language_tag}|{name}\n".encode())
    return digest.hexdigest()
