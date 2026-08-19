# Species catalogue: reconciling what shipped with the design

Date: 2026-08-19
Status: Accepted plan
Spine: [2026-08-12-versioned-species-catalogue-design.md](2026-08-12-versioned-species-catalogue-design.md)

## What happened

The catalogue design of 2026-08-12 sat uncommitted in a worktree. Work in mid-August proceeded from
the older note of 2026-08-06 instead, and shipped a naming layer that is roughly Phase 1 of the
design, built early and keyed wrongly.

**The 2026-08-12 design is the spine.** This document records what already exists, what it is worth,
what has to be reworked, and the order to do it in. Where the two disagree, the design wins except
on the two points called out under *Refinements*, which are backed by measurements taken since.

## What shipped, and where it belongs

| Delivered | Status against the design |
| --- | --- |
| `species_reference.db`: IOC World Bird List, 11,276 species, 87,656 localized names, CC BY 3.0, reproducible build, digest-verified | **Keep as the seed.** It is the design's checksum-pinned seed catalogue, minus the copy-into-`/data` step. |
| Source measurements: IOC vs eBird vs Coral coverage, per-locale completeness, the GBIF ambiguity finding | **Keep.** This is the evidence Phase 1's source selection needs, and it is expensive to reproduce. |
| Label-file verification against the registry checksum, verdict surfaced in status and on the Health page | **Keep.** It is the design's artifact-checksum ownership, arriving early. |
| `model_taxon_map.db`: `(label digest, output index) → scientific name` | **Replace** with `model_artifacts` + `model_output_taxa`. It has no class kind and keys on the label file rather than the model artifact. |
| `species_names.db` and the eBird localized-name store | **Replace** with `species_names`. Provider, release and region belong on each name; a separate store cannot express precedence. |
| Common-name resolution for the European models | **Fold into** `species_aliases`, which already specifies that an ambiguous alias is stored as an unresolved candidate rather than guessed. |
| Renames in `taxonomy_cache.manual_common_name` | **Migrate** to `species_name_overrides`, scoped to species plus language. |

## The defect worth naming

The shipped layer keys identity on the **scientific name**. The design keys it on an opaque
`species_id` with `accepted_species_id` for synonyms and successors, and it is right to.

A scientific name is not stable. When a taxon is split, lumped or synonymised, `Parus caeruleus` and
`Cyanistes caeruleus` become two different birds to anything that keys on the text: leaderboards
divide, filters miss history, and a species page shows half its sightings. Nothing warns anyone.

This is not a refactor for tidiness. It is the reason the design exists, and it should be fixed
before more read paths are taught to trust the current key.

## Refinements to the design

Both are backed by measurements taken while building the shipped layer.

### 1. Two canonical sources, not one

The design names a pinned Catalogue of Life release as canonical taxonomy and eBird as the bird
crosswalk. That is right for identity, and it must stay: the 10,000-class models emit **8,514
non-bird classes**, which no bird list covers.

But Catalogue of Life is the wrong source for *vernacular* names. Measured on 2026-08-19, its
aggregated names offer several candidates per language with nothing to choose between them: for
`Cyanistes caeruleus` GBIF returns both `Cinciarella` and `Cinciallegra` as Italian, and the second
is the name of a different species. Shipping that is worse than shipping English, because the reader
cannot tell it is wrong.

The IOC World Bird List carries one curated name per species per language and is CC BY 3.0.
Measured against the alternatives:

| | Coral | eBird | **IOC** |
| --- | ---: | ---: | ---: |
| Birds the flagship model emits | 57.9% | 94.9% | **95.2%** |
| `flexivit_il_all` labels | 32.4% | 78.2% | **90.2%** |
| `eu_medium_focalnet_b` labels | 33.1% | 77.9% | **88.1%** |
| Italian | n/a | **5.8%** | **90.5%** |
| Chinese | n/a | **30.8%** | **100%** |
| Requires an API key | no | **yes** | no |

So the precedence policy becomes: **Catalogue of Life for taxonomy and identity across all
kingdoms, eBird as the bird crosswalk, IOC for bird vernacular names, iNaturalist and eBird for
on-demand enrichment.** Each still carries its release, checksum, licence and citation.

This also removes an API key as a requirement for names in the owner's language, which the current
runtime-eBird arrangement makes necessary.

### 2. Do not guess a label's format

The design says an ambiguous alias is stored as an unresolved candidate, never guessed. Two attempts
to do otherwise were made and abandoned, and the results belong on the record so a third is not
attempted:

- A list of adjectives that cannot begin a genus claimed **198 common names as scientific** on
  `eu_medium_focalnet_b`. Those would have entered history as identities.
- A statistical discriminator, the ratio of distinct second words, separated scientific from
  common-name label files by only 0.65 against 0.31.

A bare `Genus species` is indistinguishable from `African crake` by shape. The format is declared per
model artifact, and anything undeclared resolves by lookup or stays unresolved.

## Plan

Phases follow the design. The delivered work moves Phase 1 substantially forward and gives Phase 2 a
worked example, but neither is complete against the schema.

| Phase | State | What remains |
| --- | --- | --- |
| 0. Freeze the contract and provenance gate | ☐ | Unchanged from the design. Pin the Catalogue of Life and eBird releases, and record IOC's release and citation alongside them. |
| 1. Catalogue schema and deterministic builder | 🔄 | The IOC seed, its reproducible build and its digest verification exist. Needed: the full schema, the Catalogue of Life import for non-bird classes, seed-then-copy into `/data`, and the dedicated Alembic stream. |
| 2. Checksum-bound model mappings | 🔄 | Label-file verification exists. Needed: `model_artifacts` keyed on the model checksum rather than the label digest, and `model_output_taxa` with class kinds for hybrid, aggregate, background and unknown. |
| 3. Shadow resolution and historical backfill | ☐ | Unchanged. |
| 4. Make catalogue identity authoritative | ☐ | Unchanged, and this is where the scientific-name key is retired. |
| 5. Remove label-file authority before `3.0` | ☐ | Unchanged. |

### Ordering note

Phase 4 retires the scientific-name key. Until then, every read path taught to trust the current key
is work that has to be undone, so **no further consumers of `model_taxon_map` should be added**. The
naming fallback it feeds today is harmless because it only supplies a display name when the network
cannot; making it authoritative is not.

### Cheap and worth doing first

Two items are small and independent of the phases:

- Explain limits on the Health page. It reports naming coverage without saying why a number is what
  it is, which §5 asks for.
- Measure the ~10% of European model labels that resolve to no scientific name in any held source,
  before deciding whether a further source is warranted. They may be regional or non-species
  classes that `class_kind` handles instead.

## What this costs

Some of what merged between 2026-08-15 and 2026-08-19 is superseded: the model map, the localized
name store, and the placement of owner overrides. The IOC seed, the measurements, the label
verification and the refusal to guess all carry forward.

That is the right outcome. The alternative is a second identity scheme accumulating read paths
alongside the one the design specifies.
