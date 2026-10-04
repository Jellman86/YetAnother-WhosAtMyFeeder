# Taxonomy tree: where each bird belongs

Roadmap item: [Taxonomy explorer and family tree](../../ROADMAP.md#taxonomy-explorer-and-family-tree-).
It also settles one 3.0 catalogue decision: the catalogue gains higher-rank concepts rather than
keeping a permanent compatibility reader for identifications coarser than a species.

## Data

Every rank is a catalogue taxon of its own, pointing at the next higher one
(`species.parent_species_id`), with `species.sequence` ordering siblings the way the source lists
them. This is how Catalogue of Life's data package and Darwin Core model a classification
(`parentID` / `parentNameUsageID` with explicit rows for the higher ranks), and it keeps one opaque
identity for any rank, so a model output such as `Rattus` or `Troglodytidae` can later resolve to a
real catalogue row at its own rank.

Sources, both already pinned in `species_sources.json`, and bundled rather than fetched at runtime
so reads work offline, are reproducible and follow one taxonomy:

| Ranks | Source | Notes |
| --- | --- | --- |
| order, family, genus (birds) | IOC World Bird List 14.2 | The multilingual file the catalogue already names birds from carries each species' order, family and sequence; genus is the first word of the binomial. English family names come from the master list of the same release, added to the manifest. 44 orders, 254 families, 2,392 genera. |
| Animalia to Aves | Catalogue of Life COL26.7 | `N` Animalia, `CH2` Chordata, then the intermediate ranks COL records (Vertebrata, Gnathostomata, Osteichthyes, Tetrapoda) and `V2` Aves. Intermediate ranks are kept and flagged `principal: false`. |

Runtime fetches (iNaturalist) stay what they are: per-installation enrichment, never a source of
the classification. iNaturalist's taxonomy also differs from IOC's for birds and states no licence.

A ranked classification is not an evolutionary tree: no dates, no branch lengths, no invented
ancestors, and a taxon with no recorded parent is shown as a gap.

## Delivered first: the data layer

- `species_reference.db` (schema 3) carries order, family and sequence per species and the English
  family names; built from the two pinned IOC workbooks.
- Catalogue migration `c4e8d1a7b2f3` adds `parent_species_id` and `sequence`.
- The seed builder adds the higher taxa after every species (species keep their ids) and links
  each species to its genus. The release digest covers the classification.
- The importer carries the classification into existing catalogues, translating parents to live
  identities; a release without a parent never orphans a taxon.
- Species counts, the resolver and the compatibility importer stay species-only, so a genus or
  family name does not start resolving detection history as a side effect.
- `GET /api/taxonomy/{taxon_id}/lineage` and `/children` (with species counts) read it.

## Next

1. Feeder context on the tree: species and visit counts seen here for each taxon (owner and guest
   windows as the leaderboard applies them).
2. Resolve coarser-than-species outputs to their rank on purpose, with backfill tests, and retire
   the compatibility reader for them.
3. Non-bird lineages from the pinned Catalogue of Life export (the 7,865 non-bird model classes
   currently have no parent).
4. The small view in the detection card: a lineage line from Birds to the species with one line of
   context and a button to the full view.
5. The full view: a horizontal tree centred on the bird, its path expanded and everything else
   collapsed with counts; a fan layout as an optional overview; an indented ARIA tree as the
   accessible and phone layout, all from the same data.
