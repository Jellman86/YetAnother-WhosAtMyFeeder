# Versioned species catalogue and model-output identity

**Roadmap item:** [The Road to 3.0 §1.2, Versioned species catalogue and model-output identity](../../ROADMAP.md#versioned-species-catalogue-and-model-output-identity-%EF%B8%8F)
**Status:** Proposed, required before `3.0`
**Scope:** Replace label-text identity with a dedicated, versioned, enrichable SQLite species catalogue that owns scientific names, source identifiers, synonyms, translated common names, and the exact output-index mapping for every supported classifier artifact.

## Outcome

Every class that a supported YA-WAMF model can emit resolves locally and deterministically to one
catalogue taxon. Inference records the model artifact, output index, and canonical species identity;
the UI, filters, notifications, exports, and integrations resolve names from that identity instead
of treating a model label or translated common name as a key.

The catalogue lives in `/data/species_catalog.db`, separate from the detection-history database at
`/data/speciesid.db`. The separation is deliberate: YA-WAMF can enrich, version, validate, and roll
back taxonomy and translations without rewriting the user's detection history. Both files are user
data and both are included in backup, restore, integrity checks, and upgrade testing.

The current `taxonomy_cache` and `taxonomy_translations` data is migrated conservatively into the
catalogue. During the compatibility window it remains readable in `speciesid.db`; it is not dropped
until the separate catalogue has been proven complete on upgraded installations.

## Why this is needed

YA-WAMF currently has three overlapping sources of species identity:

- model output position plus `labels.txt`;
- detection snapshots in `display_name`, `scientific_name`, `common_name`, and the iNaturalist
  `taxa_id`;
- provider-backed rows in `taxonomy_cache` and `taxonomy_translations`.

That is why an old detection can know enough to show the right Species Details view while a
different query still has only a scientific name. It also makes a translated common name look like
a different species unless every read path performs the same recovery logic.

Common names cannot safely be identifiers. They are not unique, they vary by locale and region,
and owners may override them. Scientific names are the best interchange value but also change when
taxonomies split, lump, or synonymise a taxon. The durable identity therefore needs to be an opaque
YA-WAMF key with explicit, versioned links to provider taxon concepts.

## Research findings

- Darwin Core deliberately separates `taxonID`, `scientificNameID`,
  `acceptedNameUsageID`, `scientificName`, and `vernacularName`. YA-WAMF should mirror that
  separation instead of making one provider ID or display string carry every meaning.
- The Catalogue of Life publishes pinned monthly and annual releases. Its Base Release prioritises
  scrutinised sources, while its Extended Release maximises coverage. The Base Release is the
  conservative starting point for accepted scientific names and synonym relationships.
- eBird publishes a versioned taxonomy annually and supports more than 115 alternate common-name
  sets. It is useful as a bird-specific crosswalk and name source, but bundled redistribution must
  remain behind a documented licence/attribution check.
- GBIF's species API works with name usages from multiple checklists, exposes vernacular names and
  synonyms, and supports identifier-first matching. It is suitable for crosswalk validation, not
  as an unversioned runtime identity.
- LiteRT formally maps an output tensor axis to a label associated file. ONNX offers optional
  model metadata but does not define a universal species-label contract. A classifier therefore
  always needs an ordered output mapping, even when there is no standalone `labels.txt` at
  runtime.
- RFC 5646 language tags can include language, script, region, and variants. The existing
  five-character `language_code` limit is too narrow for values such as `zh-Hant` or `pt-BR`.

## Boundaries

### In scope

- Every species, aggregate, hybrid, background, and unknown class emitted by every model in the
  supported YA-WAMF registry.
- Accepted scientific names, synonyms, provider identifiers, translated common names, provenance,
  source release, and owner overrides.
- Exact mapping from `(model artifact SHA-256, output index)` to catalogue identity or a deliberate
  non-species class.
- Offline runtime resolution after the model and catalogue are installed.
- Compatibility and lossless backfill for existing detections and installed models.

### Out of scope for the `3.0` gate

- Bundling every known taxon in every kingdom. The first catalogue covers the complete YA-WAMF
  model-output universe and its aliases, not millions of unrelated taxa.
- Translating application UI copy. Species vernacular names and UI localisation remain separate
  datasets and review processes.
- Automatically merging ambiguous homonyms or silently rewriting historical classifications after
  a taxonomic split or lump.
- Requiring a live taxonomy provider during inference or ordinary read paths.

## Data model

Names are illustrative; the implementation design review may refine them before the first
migration.

| Table | Purpose and required constraints |
|---|---|
| `catalogue_releases` | One row per imported catalogue build: schema version, source release identifiers, generated time, content SHA-256, licence/citation manifest, and activation state. A new release becomes active only after a complete transactional import and validation. |
| `species` | Opaque YA-WAMF `species_id`, rank, accepted/deprecated state, and optional `accepted_species_id` for synonym or successor relationships. No common name is stored as identity. |
| `species_concepts` | Source-specific taxon concept: `species_id`, provider, provider taxon ID, source release, accepted-name usage, canonical scientific name, authorship, and status. Unique on provider + release + provider ID. |
| `species_names` | `species_id`, RFC 5646 language tag, name, name kind, preferred flag, region where applicable, provider, source release, and provenance. Unique provider records coexist; deterministic precedence chooses one display value. |
| `species_aliases` | Normalised legacy label, former scientific name, provider synonym, or curated alias mapped to `species_id`, with source and confidence. Ambiguous aliases are stored as unresolved candidates, never guessed. |
| `model_artifacts` | Registry model/variant ID, model SHA-256, mapping-set SHA-256, output width, runtime, model version, and installation state. The artifact checksum, not the friendly model ID, owns the mapping. |
| `model_output_taxa` | `model_artifact_id`, zero-based output index, class kind (`species`, `hybrid`, `aggregate`, `background`, `unknown`), optional `species_id`, and original source label for audit. Unique on artifact + output index. |
| `species_name_overrides` | Owner-owned display names, separate from provider data, so catalogue refreshes never overwrite them. Scope is species + optional RFC 5646 language tag. |

Detections gain nullable `species_id`, `model_artifact_id`, and `model_output_index` columns. Existing
scientific/common/display fields remain as historical snapshots and compatibility fields through the
transition. Existing iNaturalist `taxa_id` becomes one external identifier rather than the canonical
key.

## Database and lifecycle boundary

- **Separate connections:** repositories open `speciesid.db` and `species_catalog.db` independently.
  Runtime code does not rely on a permanent SQLite `ATTACH`, cross-database foreign keys, or a
  distributed transaction. The shared value is an opaque, immutable `species_id`.
- **Detection writes stay autonomous:** classification resolves the model output from the catalogue
  before it writes a detection. The detection transaction stores `species_id`, artifact/index
  provenance, and name snapshots, but never mutates catalogue tables.
- **Enrichment stays autonomous:** taxonomy sync, translations, synonyms, provider identifiers, and
  owner naming overrides write only to `species_catalog.db`. A failed enrichment cannot roll back or
  corrupt a detection write.
- **Independent migration stream:** `species_catalog.db` has a dedicated Alembic environment with
  one linear head. CI applies fresh, upgrade, downgrade, upgrade, idempotency, and path-matrix checks
  to both databases. No runtime `create_all` or implicit schema repair path is permitted.
- **First installation:** the image carries a checksum-pinned seed catalogue. YA-WAMF validates and
  atomically copies it into `/data` only when no catalogue has ever been initialised. It never
  mistakes a later missing file for a fresh install.
- **Missing or corrupt catalogue:** YA-WAMF fails closed for new species classification, preserves
  incoming event recoverability, and serves existing detections from their stored name snapshots
  with an owner-visible degraded-state warning. It does not silently replace a database that may
  contain owner enrichments or overrides.
- **Reads and cache:** the checksum-verified active model mapping can be held in an immutable
  in-memory cache after startup. Catalogue release activation atomically replaces that cache only
  after validation; partially imported data is never visible.
- **Backup and restore:** a supported backup is one coordinated bundle containing
  `speciesid.db`, `species_catalog.db`, catalogue/version metadata, and configuration. Restore
  validates both SQLite files and their recorded catalogue IDs before making either live.

## Source and precedence policy

1. **Canonical taxonomy:** import a pinned Catalogue of Life Base Release for the taxa required by
   supported model mappings. Record its DOI/release, checksum, licence, and source citations.
2. **Bird-specific crosswalk:** validate scientific names, eBird species codes, hybrids, and
   aggregates against one pinned eBird taxonomy release. A taxonomy disagreement remains explicit;
   import tooling does not silently choose a fuzzy match.
3. **Common names:** store each name with language tag, provider, release, and region. Import or
   redistribute only when the source licence permits it. Existing iNaturalist/eBird calls may enrich
   an installation's local catalogue on demand, but provider failure cannot block inference.
4. **Owner override:** an owner's name wins for display and survives every provider refresh. It does
   not change canonical identity, exports that require provider names, or another locale.
5. **Fallback:** requested locale + region, requested base language, configured English provider
   name, scientific name. The API should expose provenance so the UI never presents a fallback as a
   verified translation.

The build pipeline fails when a source has no explicit compatible licence/citation record. It never
scrapes names from arbitrary web pages.

## Model contract

Species classifiers do not emit names. ONNX and OpenVINO models normally return a floating-point
tensor shaped `[1, N]`, with one logit per trained class; YA-WAMF applies softmax. TFLite returns
the same class-axis shape as probabilities, logits, or quantised integers; YA-WAMF dequantises and
normalises it. In every case the semantic result is an output position and score, for example
`index=2, score=0.84`. Only the mapping gives index `2` a species meaning.

The versioned SQLite catalogue directly stores the complete mapping for each supported classifier
artifact. Model installation performs a lookup by model SHA-256; it does not download or read a
label or mapping sidecar at runtime.

Release tooling may consume embedded LiteRT metadata, ONNX metadata, or a reviewed legacy label
file as build input. It normalises that evidence into `model_artifacts` and `model_output_taxa`
rows before the catalogue is published. A machine-readable intermediate record can look like this:

```json
{
  "schema_version": 1,
  "model_sha256": "...",
  "output_count": 1486,
  "taxonomy_release": "...",
  "outputs": [
    {
      "index": 0,
      "kind": "species",
      "source": "catalogue-of-life",
      "source_taxon_id": "...",
      "scientific_name": "Passer domesticus"
    }
  ]
}
```

That intermediate file is reproducibility evidence for the catalogue builder, not a runtime model
dependency. The catalogue release stores its resulting mapping-set checksum and source provenance.

Installation is fail-closed. YA-WAMF verifies the model checksum, finds exactly one matching
database mapping, checks its mapping-set checksum, contiguous indices, output count against the
model tensor, unique source identifiers, and complete resolution of every species class before
activation. Non-species outputs must be declared rather than hidden in special label strings.

At inference time the winning tensor index resolves through `model_output_taxa`. Several indices
may deliberately resolve to the same `species_id`; their probabilities are aggregated according to
the stored mapping policy, replacing today's label-text grouping. Supported models no longer parse
a text label to discover identity. `labels.txt` remains only as an import adapter for legacy or
owner-supplied models until their mapping has been imported and verified; it is not the runtime
source of truth.

The separate crop detector is outside this species mapping. Its raw outputs are bounding boxes,
numeric detector class IDs, and confidence values (or a YOLOX tensor containing those values). Its
single target `bird` class stays in checksum-bound detector configuration rather than being treated
as a taxonomic species.

## Delivery plan

### Phase 0: freeze the contract and provenance gate

- Inventory every current registry model/region variant, output width, model SHA-256, label
  checksum, label grammar, non-species class, and training taxonomy.
- Decide and document the pinned Catalogue of Life and eBird releases used for the first build.
- Add a machine-readable source manifest with URL, release, checksum, licence, attribution, and
  redistribution decision.
- Produce a report of exact, synonym, split/lump, aggregate, hybrid, and unresolved mappings. No
  fuzzy result may enter a release without review.

**Evidence:** the inventory covers 100% of supported artifact checksums; rebuilding from pinned
inputs produces the same catalogue checksum; the licence gate rejects an unknown source.

### Phase 1: catalogue schema and deterministic builder

- Add a dedicated, single-head Alembic migration environment for `species_catalog.db`, with
  reversible and idempotent migrations for the catalogue tables and RFC 5646 language tags. Do not
  drop or repurpose `taxonomy_cache` or `taxonomy_translations` in `speciesid.db` yet.
- Add a repository-owned importer that validates a release in staging tables and activates it in
  one transaction. Interrupted imports leave the previous release active.
- Build only the complete model-output taxon set plus aliases and supported-locale names. Keep the
  source artifact outside migration code so migrations remain small and deterministic.
- Add repository methods for identity lookup, locale fallback, alias search, and provenance.

**Evidence:** fresh install, upgrade, downgrade, upgrade, interrupted import, repeat import,
catalogue rollback, missing/corrupt catalogue, and coordinated backup/restore tests all preserve
detection history and owner overrides.

### Phase 2: checksum-bound model mappings

- Compile reviewed mapping rows into the catalogue for every supported artifact and regional
  variant. Keep source manifests only as deterministic build inputs and review evidence.
- During model installation and activation, resolve the model SHA-256 directly against SQLite and
  verify output tensor width before a model becomes selectable. Do not download a runtime mapping
  sidecar.
- Add diagnostics that report mapping coverage, catalogue release, source mismatch, and unresolved
  classes without exposing raw provider credentials.
- Reject a same-name model whose checksum differs from the registered mapping.

**Evidence:** every supported model has exactly one mapping for every output index; swapped,
truncated, duplicated, or wrong-checksum mappings fail activation; hardware smoke tests resolve the
same top outputs on every runtime flavour.

### Phase 3: shadow resolution and historical backfill

- Resolve inference through both the current label path and the new catalogue path, persist only
  when they agree, and surface mismatches in owner diagnostics.
- Backfill `species_id` conservatively from existing iNaturalist IDs, exact scientific names, and
  unambiguous aliases. Keep unresolved rows unchanged and report counts; never guess from a common
  name shared by multiple taxa.
- Copy existing provider taxonomy, translations, and manual overrides into the separate catalogue
  with provenance. Re-running the migration is a no-op and never deletes the source rows.
- Record model artifact and output index on new detections while retaining name snapshots.
- Update audio correlation, manual observations, backfill, and video reclassification to use the
  same resolver.

**Evidence:** a copy of a real upgraded database produces identical detection counts, grouping,
filters, notification decisions, and exports; every unresolved row remains readable and repairable.

### Phase 4: make catalogue identity authoritative

- Move leaderboard, Events, Species Details, search, filters, notifications, BirdNET correlation,
  eBird export, and external integrations to `species_id` joins through repositories.
- Resolve translated display names at read time with one shared precedence function. Do not write a
  locale-dependent name back into canonical detection identity.
- Preserve API compatibility fields while adding canonical identity and name provenance to typed
  response models and generated frontend types.
- Make taxonomy provider sync an explicit catalogue enrichment job with visible status, version,
  errors, and rollback rather than scattered read-time network lookups.

**Evidence:** changing locale changes display only; every affected surface shows the same species;
provider outage tests prove normal inference and reads remain local; query benchmarks meet or beat
the current taxonomy joins.

### Phase 5: remove label-file authority before `3.0`

- Stop requiring standalone `labels.txt` or another mapping sidecar for registry-supported models.
  Prefer embedded model metadata as build evidence where available, but always compile it into the
  catalogue mapping tables before release.
- Keep a documented compatibility importer for owner-supplied/pre-3.0 models. It must produce an
  explicit unresolved mapping report before activation.
- Retire duplicated name-recovery SQL after `taxonomy_cache` and `taxonomy_translations` data has
  migrated into the separate catalogue without loss. Keep a bounded compatibility reader through
  the pre-3.0 upgrade window rather than attempting cross-database compatibility views.
- Document catalogue version, model mapping status, source citations, update/rollback behaviour,
  and backup implications in owner diagnostics and upgrade notes.

**Evidence:** a clean install and an upgraded install run all supported models without runtime
label-file reads; all model flavours pass image smoke tests; the full Definition of Done and `3.0`
migration evidence are green.

#### The compatibility importer, as shipped

`species_catalog_compatibility.py` derives a mapping for a model the registry does not publish, by
resolving that model's own labels against the live catalogue. It runs once per startup, detached
from it, after waiting for the classifier to load the model whose checksum the mapping is keyed on.

It resolves a label only by exact catalogue match — a scientific name, a recorded resolved synonym,
or an English vernacular name, each also compared in a folded form that drops a trailing qualifier,
apostrophes and case. Where no format is declared, the label is read every way at once: as a common
name, as a scientific name, through the two self-announcing shapes `scientific_name_from_label`
accepts without a declaration, and through the bracketed half of a paired label. An identity is
recorded only when every reading that reaches one reaches the *same* one. Two readings that
disagree, and a name more than one species holds, both resolve to nothing. A declared format is
obeyed exactly, because the declaration exists to stop the shape of a line being trusted.

Four rules keep it safe to run unattended:

- **A registry model is skipped.** Its mapping is reviewed and arrives in the release bundle. One
  derived from a file on disk must never stand in for one that was checked, not even while the
  reviewed one is missing.
- **An artifact the catalogue already holds is never touched**, so a published mapping cannot be
  overwritten by a derived one.
- **Every unresolved output still gets a row**, carrying the model's verbatim label and the kind
  `unknown` — the same shape a published mapping uses for its own gaps — so coverage counts
  identity rather than the presence of a row, and the label text no longer lives only in
  `labels.txt`.
- **The artifact is recorded as locally derived**, under the reserved `local:` registry namespace,
  and `catalogue_labels_for_model` refuses to serve its labels. Handing them back as catalogue
  labels would launder the file this work exists to stop trusting, and would report a verification
  that never happened.

The report — outputs written, resolved, unresolved, and a capped sample of the unresolved ones with
the reason each failed — is returned by the importer and surfaced in owner diagnostics under
`species_catalog.local_mapping`.

## Safety and second-order effects

- **Taxonomic change is not historical correction.** A later split or lump must not silently
  rewrite what an older model predicted. Detection evidence stays bound to the model artifact and
  output mapping used at the time; current accepted names are a separate presentation layer.
- **Model names are not model identity.** Region variants and replaced artifacts may share a
  friendly ID while changing output order. Only SHA-256-bound mappings may activate.
- **Translations are not keys.** Locale changes must never alter filters, notification policy,
  deduplication, audio correlation, or exports.
- **Manual overrides are user data.** Catalogue import, provider refresh, rollback, and migration
  must preserve them exactly.
- **Ambiguity fails closed.** Homonyms, fuzzy matches, missing taxa, and source disagreements remain
  unresolved until reviewed. The system keeps the raw output and remains operable.
- **Source updates are explicit.** A new upstream taxonomy is a reviewed catalogue release with a
  diff and rollback, not an automatic mutable dependency at startup.
- **Storage and backup remain bounded.** Scope the bundled catalogue to taxa YA-WAMF can emit;
  measure database growth and coordinated two-database backup/restore time before widening it.
- **No cross-database foreign keys.** `speciesid.db` retains an opaque `species_id` and historical
  name snapshots. Integrity diagnostics report orphaned identifiers, while catalogue rollback keeps
  previously referenced identities available or explicitly deprecated rather than deleting them.
- **Search indexes are derived.** If SQLite FTS5 is introduced, rebuild it from catalogue tables and
  integrity-check it; never make the index the only copy of a name.

## Acceptance criteria for `3.0`

- Every supported model artifact and regional variant has complete, checksum-bound output mapping.
- New visual, video, manual, and audio-correlated detections persist canonical `species_id`; model
  detections also persist artifact and output-index provenance.
- All primary species surfaces and policies join by canonical identity, not common-name or raw-label
  equality.
- Supported UI locales can resolve available species names locally with documented provenance and
  deterministic fallback.
- Existing detections, manual overrides, and external IDs survive a tested upgrade and rollback;
  unresolved legacy rows remain visible.
- A supported backup and restore round trip preserves and validates both SQLite files; a missing or
  corrupt catalogue degrades safely without modifying `speciesid.db`.
- Registry-supported inference no longer depends on standalone label files at runtime.
- Catalogue refresh is transactional, versioned, observable, reversible, and never required for
  startup or inference.
- Source licences, versions, citations, and content checksums are present in the shipped catalogue
  manifest and owner diagnostics.

## References

- [Darwin Core taxon and language terms](https://dwc.tdwg.org/terms/)
- [Catalogue of Life downloads and version archive](https://www.catalogueoflife.org/data/download)
- [Catalogue of Life release metadata](https://www.catalogueoflife.org/data/metadata)
- [eBird taxonomy and release model](https://science.ebird.org/en/use-ebird-data/the-ebird-taxonomy)
- [GBIF Species API](https://techdocs.gbif.org/en/openapi/v1/species)
- [GBIF taxonomy interpretation and identifier matching](https://techdocs.gbif.org/en/data-processing/taxonomy-interpretation)
- [RFC 5646 language tags](https://www.rfc-editor.org/rfc/rfc5646)
- [LiteRT model metadata and tensor-axis labels](https://developers.google.com/edge/litert/conversion/tensorflow/metadata)
- [ONNX intermediate representation and model metadata](https://onnx.ai/onnx/repo-docs/IR.html)
- [SQLite FTS5 integrity considerations](https://www.sqlite.org/fts5.html)
