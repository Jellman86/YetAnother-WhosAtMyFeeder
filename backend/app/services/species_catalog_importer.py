"""Import a catalogue release bundle into the live catalogue, transactionally.

A bundle is a built catalogue file (what the seed builder produces): a fully
migrated `species_catalog.db` holding exactly one release. The importer
validates the bundle — schema revision, one release row, recorded content
digest, foreign-key integrity — then stages its rows and activates the release
inside a single transaction against the live catalogue. Interruption at any
point rolls back to the previous release with no partial rows.

Species identity is stable and durable: an incoming taxon already known
through any provider concept keeps its live `species_id`; an unknown one gets
a new identity; and identities are never deleted, only left behind by newer
releases, so rollback keeps every previously referenced `species_id` valid.
Owner overrides live in their own table and are never touched.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

import structlog

from app.services.species_catalog_migrations import catalog_migration_heads, default_catalog_path
from app.services.species_catalog_release import release_content_digest

from app.services.species_catalog_compatibility import LOCAL_REGISTRY_PREFIX

log = structlog.get_logger()


class CatalogImportError(Exception):
    """A release bundle failed validation, or the import could not complete."""


@dataclass(frozen=True)
class ImportResult:
    status: str
    release_id: int
    species_added: int = 0
    species_matched: int = 0
    names_added: int = 0


@dataclass(frozen=True)
class _Bundle:
    release: sqlite3.Row
    species: list[sqlite3.Row]
    concepts: list[sqlite3.Row]
    names: list[sqlite3.Row]
    aliases: list[sqlite3.Row]
    model_artifacts: list[sqlite3.Row]
    model_outputs: list[sqlite3.Row]


def _schema_revision(connection: sqlite3.Connection) -> Optional[str]:
    try:
        row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    except sqlite3.Error:
        return None
    return row[0] if row else None


def _read_bundle(bundle_path: Path) -> _Bundle:
    try:
        connection = sqlite3.connect(f"file:{bundle_path}?mode=ro", uri=True)
    except sqlite3.Error as error:
        raise CatalogImportError(f"Bundle unreadable at {bundle_path}: {error}") from error
    connection.row_factory = sqlite3.Row
    try:
        head = catalog_migration_heads()[0]
        revision = _schema_revision(connection)
        if revision != head:
            raise CatalogImportError(f"Bundle schema revision '{revision}' does not match the expected head '{head}'")

        releases = connection.execute("SELECT * FROM catalogue_releases").fetchall()
        if len(releases) != 1:
            raise CatalogImportError(f"A bundle must hold exactly one release, found {len(releases)}")
        release = releases[0]

        recomputed = release_content_digest(
            connection,
            schema_version=int(release["schema_version"]),
            source_manifest=str(release["source_manifest"]),
            generated_at=str(release["generated_at"]),
        )
        if recomputed != release["content_sha256"]:
            raise CatalogImportError(
                "Bundle content does not match its recorded digest: "
                f"recorded {release['content_sha256']}, recomputed {recomputed}"
            )

        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise CatalogImportError("Bundle fails foreign-key integrity")

        return _Bundle(
            release=release,
            species=connection.execute("SELECT * FROM species ORDER BY species_id").fetchall(),
            concepts=connection.execute(
                "SELECT * FROM species_concepts ORDER BY species_id, provider, provider_taxon_id"
            ).fetchall(),
            names=connection.execute("SELECT * FROM species_names ORDER BY species_id, language_tag, name").fetchall(),
            aliases=connection.execute(
                "SELECT * FROM species_aliases ORDER BY alias, alias_kind, species_id"
            ).fetchall(),
            model_artifacts=connection.execute("SELECT * FROM model_artifacts ORDER BY model_sha256").fetchall(),
            model_outputs=connection.execute(
                "SELECT t.*, a.model_sha256 AS artifact_sha256 FROM model_output_taxa t"
                " JOIN model_artifacts a ON a.id = t.model_artifact_id"
                " ORDER BY a.model_sha256, t.output_index"
            ).fetchall(),
        )
    finally:
        connection.close()


def _rollback_quietly(live: sqlite3.Connection) -> None:
    """Roll back if a transaction is still open.

    A failed COMMIT (disk full, I/O error) already ends the transaction, and a
    ROLLBACK then raises its own error, masking the real cause. The original
    exception is the one worth surfacing.
    """
    try:
        live.execute("ROLLBACK")
    except sqlite3.Error:
        pass


def _before_activation(connection: sqlite3.Connection) -> None:
    """Test seam: the last point an interruption can strike before activation."""


def _map_species(live: sqlite3.Connection, bundle: _Bundle) -> tuple[dict[int, int], int, int]:
    """Match bundle species to live identities; create the ones nobody knows."""
    concepts_by_species: dict[int, list[sqlite3.Row]] = {}
    for concept in bundle.concepts:
        concepts_by_species.setdefault(concept["species_id"], []).append(concept)

    id_map: dict[int, int] = {}
    added = matched = 0
    for species in bundle.species:
        bundle_id = species["species_id"]
        live_id: Optional[int] = None
        for concept in concepts_by_species.get(bundle_id, []):
            row = live.execute(
                "SELECT species_id FROM species_concepts WHERE provider = ? AND provider_taxon_id = ? LIMIT 1",
                (concept["provider"], concept["provider_taxon_id"]),
            ).fetchone()
            if row:
                live_id = row[0]
                break
        if live_id is None:
            cursor = live.execute(
                "INSERT INTO species (rank, status) VALUES (?, ?)", (species["rank"], species["status"])
            )
            live_id = int(cursor.lastrowid or 0)
            added += 1
        else:
            matched += 1
        id_map[bundle_id] = live_id

    for species in bundle.species:
        accepted = species["accepted_species_id"]
        if accepted is not None and accepted in id_map:
            live.execute(
                "UPDATE species SET accepted_species_id = ? WHERE species_id = ?",
                (id_map[accepted], id_map[species["species_id"]]),
            )
    return id_map, added, matched


def _mapped_outputs(outputs, id_map: dict[int, int]) -> list[dict]:
    """Bundle output rows with their species ids translated to live ones.

    The bundle numbers its species from its own build. Writing those numbers
    into the live catalogue would bind an output to whichever species happens
    to hold that number here.
    """
    return [
        {
            "output_index": output["output_index"],
            "class_kind": output["class_kind"],
            "species_id": id_map[output["species_id"]] if output["species_id"] is not None else None,
            "source_label": output["source_label"],
        }
        for output in outputs
    ]


def _identity_gains(
    held: dict[int, tuple[str, Optional[int], str]], incoming: list[dict]
) -> Optional[list[tuple[int, int]]]:
    """The outputs this mapping names that the catalogue could not, or None.

    An output the catalogue holds as `unknown` with no species carries no
    claim: it records the model's label and says nothing about what it is.
    A release that can name it is therefore adding knowledge, not correcting
    a claim, and that is the one difference a mapping set may carry.

    Every other difference returns None so the caller refuses the release:
    an identity being replaced or withdrawn, a label being rewritten, or a
    class kind moving between anything else. Those are corrections, and a
    correction needs a deliberate supersession rather than a quiet arrival.
    """
    # An index the catalogue holds and the mapping no longer describes means
    # the mapping shrank. Recording that mapping's digest while keeping rows it
    # does not contain would have the catalogue claim a mapping it does not
    # hold, so it is a difference like any other.
    if set(held) - {int(row["output_index"]) for row in incoming}:
        return None

    gains: list[tuple[int, int]] = []
    for row in incoming:
        index = int(row["output_index"])
        current = held.get(index)
        if current is None:
            # Absent rather than different; added by `complete_artifact_mapping`.
            continue
        candidate = (str(row["class_kind"]), row["species_id"], str(row["source_label"]))
        if current == candidate:
            continue
        if current[2] != candidate[2]:
            return None
        gained_identity = (
            current[0] == "unknown" and current[1] is None and candidate[0] == "species" and candidate[1] is not None
        )
        if not gained_identity:
            return None
        gains.append((index, int(candidate[1])))
    return gains


def complete_artifact_mapping(live: sqlite3.Connection, *, artifact_row_id: int, bundle_rows) -> int:
    """Add output rows the live catalogue lacks, and change none that it has.

    Only called when the bundle's `mapping_set_sha256` matches the registered
    artifact's, which means the source mapping is identical. A row the live
    catalogue does not hold is therefore absent rather than different, and
    adding it claims no identity that the mapping did not already carry.

    The digest is computed over the whole source mapping, including outputs
    nothing could resolve, while the stored rows were once a filtered subset of
    it. That is why a live catalogue can hold fewer rows than its own digest
    describes, and why this exists.

    A row that would *change* is refused. That is a mapping correction, and it
    needs an explicit supersession policy rather than arriving quietly here.
    """
    # Read by position so this does not depend on the caller's row factory.
    existing = {
        int(index): (str(kind), species_id, str(label))
        for index, kind, species_id, label in live.execute(
            "SELECT output_index, class_kind, species_id, source_label FROM model_output_taxa"
            " WHERE model_artifact_id = ?",
            (artifact_row_id,),
        )
    }

    added = 0
    for row in bundle_rows:
        index = int(row["output_index"])
        incoming = (str(row["class_kind"]), row["species_id"], str(row["source_label"]))
        held = existing.get(index)
        if held is not None:
            if held != incoming:
                raise CatalogImportError(
                    f"Bundle mapping for output {index} differs from the one already recorded"
                    f" for this artifact; refusing to rewrite it"
                )
            continue
        live.execute(
            "INSERT INTO model_output_taxa (model_artifact_id, output_index, class_kind, species_id, source_label)"
            " VALUES (?, ?, ?, ?, ?)",
            (artifact_row_id, index, row["class_kind"], row["species_id"], row["source_label"]),
        )
        added += 1
    return added


def _complete_registered_mappings(live: sqlite3.Connection, bundle: "_Bundle") -> int:
    """Add absent output rows for every artifact already registered here.

    Only artifacts whose `mapping_set_sha256` matches are touched: a differing
    digest is a mapping change, which `import_release` refuses outright.
    """
    added = 0
    for artifact in bundle.model_artifacts:
        row = live.execute(
            "SELECT id, mapping_set_sha256 FROM model_artifacts WHERE model_sha256 = ?",
            (artifact["model_sha256"],),
        ).fetchone()
        if row is None or row["mapping_set_sha256"] != artifact["mapping_set_sha256"]:
            continue
        added += complete_artifact_mapping(
            live,
            artifact_row_id=int(row["id"]),
            # Only rows that carry no identity. This repair runs before any
            # species mapping is built, so a bundle's species number cannot be
            # translated to a live one here, and writing it raw would bind an
            # output to whichever species happens to hold that number in this
            # catalogue. The rows this exists to restore are exactly the ones
            # with no identity: outputs nothing could resolve, counted in the
            # mapping digest but filtered out before they were stored.
            bundle_rows=[
                output
                for output in bundle.model_outputs
                if str(output["artifact_sha256"]) == str(artifact["model_sha256"]) and output["species_id"] is None
            ],
        )
    return added


def import_release(bundle_path: Path, catalog_path: Optional[Path] = None) -> ImportResult:
    bundle = _read_bundle(Path(bundle_path))
    path = Path(catalog_path or default_catalog_path())
    if not path.is_file():
        raise CatalogImportError(f"No live catalogue at {path}")

    live = sqlite3.connect(path, isolation_level=None)
    live.row_factory = sqlite3.Row
    try:
        live.execute("PRAGMA foreign_keys = ON")
        head = catalog_migration_heads()[0]
        if _schema_revision(live) != head:
            raise CatalogImportError("Live catalogue schema is not at the expected head; run migrations first")

        live.execute("BEGIN IMMEDIATE")
        try:
            existing = live.execute(
                "SELECT id FROM catalogue_releases WHERE content_sha256 = ?",
                (bundle.release["content_sha256"],),
            ).fetchone()
            if existing:
                # The release is already held, but its artifacts may still be
                # missing output rows: the stored mapping was once a filtered
                # subset of the mapping its own digest describes. Completing
                # that is a repair rather than an import, so it happens here
                # too, adding only rows that are absent.
                repaired = _complete_registered_mappings(live, bundle)
                if repaired:
                    live.execute("COMMIT")
                    log.info(
                        "Completed mappings on an already-imported release",
                        release_id=existing["id"],
                        outputs_added=repaired,
                    )
                else:
                    live.execute("ROLLBACK")
                    log.info("Catalogue release already imported", release_id=existing["id"])
                return ImportResult(status="already_imported", release_id=existing["id"])

            cursor = live.execute(
                "INSERT INTO catalogue_releases (schema_version, source_manifest, content_sha256, generated_at, state)"
                " VALUES (?, ?, ?, ?, 'staged')",
                (
                    bundle.release["schema_version"],
                    bundle.release["source_manifest"],
                    bundle.release["content_sha256"],
                    bundle.release["generated_at"],
                ),
            )
            release_id = int(cursor.lastrowid or 0)

            id_map, added, matched = _map_species(live, bundle)

            for concept in bundle.concepts:
                live.execute(
                    "INSERT INTO species_concepts"
                    " (species_id, provider, provider_taxon_id, source_release, scientific_name,"
                    "  authorship, accepted_name_usage, status)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                    " ON CONFLICT (provider, source_release, provider_taxon_id) DO NOTHING",
                    (
                        id_map[concept["species_id"]],
                        concept["provider"],
                        concept["provider_taxon_id"],
                        concept["source_release"],
                        concept["scientific_name"],
                        concept["authorship"],
                        concept["accepted_name_usage"],
                        concept["status"],
                    ),
                )

            names_before = live.total_changes
            for name in bundle.names:
                live.execute(
                    "INSERT INTO species_names"
                    " (species_id, language_tag, name, name_kind, preferred, region, provider, source_release)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                    " ON CONFLICT (species_id, language_tag, provider, source_release, name) DO NOTHING",
                    (
                        id_map[name["species_id"]],
                        name["language_tag"],
                        name["name"],
                        name["name_kind"],
                        name["preferred"],
                        name["region"],
                        name["provider"],
                        name["source_release"],
                    ),
                )
            names_added = live.total_changes - names_before

            for alias in bundle.aliases:
                mapped = id_map.get(alias["species_id"]) if alias["species_id"] is not None else None
                if mapped is None:
                    # SQLite treats NULLs as distinct in unique constraints, so
                    # unresolved aliases are deduplicated explicitly.
                    exists = live.execute(
                        "SELECT 1 FROM species_aliases"
                        " WHERE alias = ? AND alias_kind = ? AND species_id IS NULL AND source = ?",
                        (alias["alias"], alias["alias_kind"], alias["source"]),
                    ).fetchone()
                    if exists:
                        continue
                live.execute(
                    "INSERT INTO species_aliases (alias, alias_kind, species_id, resolution, source, confidence)"
                    " VALUES (?, ?, ?, ?, ?, ?)"
                    " ON CONFLICT (alias, alias_kind, species_id, source) DO NOTHING",
                    (
                        alias["alias"],
                        alias["alias_kind"],
                        mapped,
                        alias["resolution"],
                        alias["source"],
                        alias["confidence"],
                    ),
                )

            outputs_by_artifact: dict[str, list[sqlite3.Row]] = {}
            for output in bundle.model_outputs:
                outputs_by_artifact.setdefault(output["artifact_sha256"], []).append(output)
            outputs_added = 0
            for artifact in bundle.model_artifacts:
                existing_artifact = live.execute(
                    "SELECT id, mapping_set_sha256, registry_id FROM model_artifacts WHERE model_sha256 = ?",
                    (artifact["model_sha256"],),
                ).fetchone()
                if existing_artifact:
                    artifact_row_id = int(existing_artifact["id"])
                    incoming = _mapped_outputs(outputs_by_artifact.get(artifact["model_sha256"], []), id_map)
                    locally_derived = str(existing_artifact["registry_id"] or "").startswith(LOCAL_REGISTRY_PREFIX)
                    if locally_derived:
                        # This install derived a mapping for a model nobody had
                        # published, from that model's own labels. A published
                        # mapping is reviewed and outranks it outright. Refusing
                        # the release because it disagrees with a local guess
                        # would block every future catalogue update for this
                        # owner, which is a far worse failure than replacing a
                        # mapping that was never authoritative.
                        log.info(
                            "Replacing a locally derived mapping with the published one",
                            model_sha256=artifact["model_sha256"],
                            was=existing_artifact["registry_id"],
                        )
                        live.execute("DELETE FROM model_output_taxa WHERE model_artifact_id = ?", (artifact_row_id,))
                        live.execute("DELETE FROM model_artifacts WHERE id = ?", (artifact_row_id,))
                        existing_artifact = None
                    elif existing_artifact["mapping_set_sha256"] != artifact["mapping_set_sha256"]:
                        # The artifact checksum owns its mapping, so a
                        # same-checksum artifact arriving with a different one
                        # fails the whole import closed per §1 -- unless the
                        # only difference is that outputs the catalogue could
                        # not name have been named. That withdraws nothing and
                        # rewrites nothing, so it is applied and the artifact
                        # records the mapping set it was actually given.
                        held = {
                            int(index): (str(kind), species_id, str(label))
                            for index, kind, species_id, label in live.execute(
                                "SELECT output_index, class_kind, species_id, source_label FROM model_output_taxa"
                                " WHERE model_artifact_id = ?",
                                (artifact_row_id,),
                            )
                        }
                        gains = _identity_gains(held, incoming)
                        if gains is None:
                            raise CatalogImportError(
                                "Bundle carries a different mapping set for already-registered artifact "
                                f"{artifact['model_sha256']}; refusing the release"
                            )
                        for output_index, species_id in gains:
                            live.execute(
                                "UPDATE model_output_taxa SET class_kind = 'species', species_id = ?"
                                " WHERE model_artifact_id = ? AND output_index = ?",
                                (species_id, artifact_row_id, output_index),
                            )
                        live.execute(
                            "UPDATE model_artifacts SET mapping_set_sha256 = ? WHERE id = ?",
                            (artifact["mapping_set_sha256"], artifact_row_id),
                        )
                        if gains:
                            log.info(
                                "Outputs the catalogue could not name have been named by this release",
                                model_sha256=artifact["model_sha256"],
                                outputs_named=len(gains),
                            )
                    if existing_artifact is not None:
                        # Any row the live catalogue lacks is absent rather
                        # than different. It can hold fewer rows than its own
                        # digest describes, because outputs nothing could
                        # resolve were counted in the digest but not stored.
                        outputs_added += complete_artifact_mapping(
                            live,
                            artifact_row_id=artifact_row_id,
                            bundle_rows=incoming,
                        )
                        continue
                cursor = live.execute(
                    "INSERT INTO model_artifacts"
                    " (registry_id, model_sha256, mapping_set_sha256, output_width, runtime, model_version, state)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        artifact["registry_id"],
                        artifact["model_sha256"],
                        artifact["mapping_set_sha256"],
                        artifact["output_width"],
                        artifact["runtime"],
                        artifact["model_version"],
                        artifact["state"],
                    ),
                )
                new_artifact_id = int(cursor.lastrowid or 0)
                for output in outputs_by_artifact.get(artifact["model_sha256"], []):
                    species_id = id_map[output["species_id"]] if output["species_id"] is not None else None
                    live.execute(
                        "INSERT INTO model_output_taxa"
                        " (model_artifact_id, output_index, class_kind, species_id, source_label)"
                        " VALUES (?, ?, ?, ?, ?)",
                        (
                            new_artifact_id,
                            output["output_index"],
                            output["class_kind"],
                            species_id,
                            output["source_label"],
                        ),
                    )

            _before_activation(live)
            live.execute("UPDATE catalogue_releases SET state = 'retired' WHERE state = 'active'")
            live.execute(
                "UPDATE catalogue_releases SET state = 'active', activated_at = ? WHERE id = ?",
                (datetime.now(UTC).isoformat(), release_id),
            )
            live.execute("COMMIT")
        except CatalogImportError:
            _rollback_quietly(live)
            raise
        except Exception as error:
            _rollback_quietly(live)
            raise CatalogImportError(f"Import interrupted, previous release left active: {error}") from error
    finally:
        live.close()

    log.info(
        "Catalogue release imported",
        release_id=release_id,
        species_added=added,
        species_matched=matched,
        names_added=names_added,
        outputs_added=outputs_added,
    )
    return ImportResult(
        status="imported",
        release_id=release_id,
        species_added=added,
        species_matched=matched,
        names_added=names_added,
    )


def rollback_to_release(release_id: int, catalog_path: Optional[Path] = None) -> None:
    """Reactivate a retired release. Identities and rows are kept, only the
    active-release pointer moves; that is what makes a refresh reversible."""
    path = Path(catalog_path or default_catalog_path())
    live = sqlite3.connect(path, isolation_level=None)
    try:
        live.execute("BEGIN IMMEDIATE")
        try:
            row = live.execute("SELECT state FROM catalogue_releases WHERE id = ?", (release_id,)).fetchone()
            if row is None or row[0] != "retired":
                raise CatalogImportError(f"Release {release_id} is not a retired release; nothing to roll back to")
            live.execute("UPDATE catalogue_releases SET state = 'retired' WHERE state = 'active'")
            live.execute(
                "UPDATE catalogue_releases SET state = 'active', activated_at = ? WHERE id = ?",
                (datetime.now(UTC).isoformat(), release_id),
            )
            live.execute("COMMIT")
        except CatalogImportError:
            _rollback_quietly(live)
            raise
        except Exception as error:
            _rollback_quietly(live)
            raise CatalogImportError(f"Rollback interrupted, nothing changed: {error}") from error
    finally:
        live.close()
    log.info("Catalogue rolled back", release_id=release_id)
