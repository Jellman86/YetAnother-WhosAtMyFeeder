# Species reference and name resolution

Date: 2026-08-06
Status: Superseded in part — the open decisions are resolved in
[2026-08-19-species-reference-source-decision.md](2026-08-19-species-reference-source-decision.md),
which measures the coverage this document assumed

## Decision

Introduce one central species reference that model label sets resolve against, so scientific and
common names come from local data rather than a live lookup. iNaturalist becomes an enrichment
source for localized names, photographs, and species the reference does not cover, instead of the
only source of a species' common name.

No per-model taxonomy sidecar is proposed. An earlier draft included one; it does not survive
review, because every shipped label format already resolves against a single table using existing
code (see Mapping below).

## Context

Names are resolved lazily per species from iNaturalist and cached in `taxonomy_cache`. Measured on
a live feeder running a 10,000-label classifier for two days, that cache held **144 rows** (140
resolved, 4 recorded as not-found). The cache only ever contains species that have already been
detected, so a species seen for the first time requires a network call while the event is being
processed.

Models do not share a label vocabulary or even a label format:

| Model | Labels | Format | Carries a common name |
| --- | ---: | --- | --- |
| `rope_vit_b14_inat21` | 10,000 | `04815_Animalia_Chordata_..._Rattus_rattus` | No |
| `convnext_large_inat21` | 10,000 | `Rattus rattus` | No |
| `mobilenet_v2_birds` | 965 | `Haemorhous cassinii (Cassin's Finch)` | Yes |
| `eu_medium_focalnet_b`, `uniformer_s_eu_common` | 707 | `African blue tit` | Common name only |
| `flexivit_il_all` | 550 | `African crake` | Common name only |

Of the 10,000 iNaturalist labels, 1,486 are birds. The two 10,000-label models carry no common name
at all, so for those models iNaturalist is the only source of one — and a failed lookup used to be
cached permanently as "no such species", which is the cause behind issue #132.

## Mapping

A central reference needs no per-model artifact. Existing code already reduces every shipped format
to something the table can match, and `_query_cache` matches on either name:

```text
04815_Animalia_..._Rattus_rattus     -> "Rattus rattus"                  -> scientific_name
Rattus rattus                        -> "Rattus rattus"                  -> scientific_name
Haemorhous cassinii (Cassin's Finch) -> ("Haemorhous cassinii", "Cassin's Finch") -> either
African blue tit                     -> "African blue tit"               -> common_name
```

`normalize_classifier_label` handles the taxonomic-hierarchy form, `_parenthetical_aliases` splits
the paired form, and the cache lookup is already bidirectional. The mapping is a pure function of
the label plus one indexed lookup.

## Name fields on a detection

A detection stores four name columns that hold three different kinds of value:

| Column | What it is |
| --- | --- |
| `category_name` | the raw model label, in whatever format that model uses |
| `scientific_name`, `common_name`, `taxa_id` | resolved facts |
| `display_name` | a rendering, computed at write time |

`display_name` is derived from `notification_language` and `display_common_names` at the moment the
row is written, so it freezes a preference into history. Changing either setting does not re-render
existing detections; canonical-identity repair compensates for some of this after the fact.

Deriving the display name at read time from a stable species identity would remove that, and is
worth doing independently of whether a bundled reference is adopted. It is not part of this
decision.

## Options considered

### A. Central species reference, seeded from local data

One table of species identity (scientific name, English common name, rank, lineage, iNaturalist
taxon id), seeded at startup into `taxonomy_cache`, with iNaturalist filling gaps.

- Removes the network from the naming path for covered species.
- Gives a species identity that does not depend on which model produced the detection.
- Costs a build-time generation step and a staleness policy for taxonomic revisions.
- Does not address localized names, which remain an enrichment concern.

### B. Per-model taxonomy sidecar

Each model ships its own label-to-taxonomy file.

- Rejected. The mapping above needs no precomputation, and N sidecars can disagree with each other
  about the same species. The only case it uniquely covers — a model published after the
  application's reference — is already covered by the iNaturalist fallback.

### C. Keep lazy resolution, harden it

Retain the current design with the fix that a failed request is no longer cached as not-found.

- Already implemented, and still required regardless of which option is chosen: species outside any
  bundled reference will always resolve lazily.
- Leaves a fresh install with an empty cache and a network dependency during event processing.

### D. Pre-resolve the active model's labels in the background

Walk the active model's label set after startup and resolve each species, so the cache is populated
before a species is first seen. Attractive because it needs no redistributed data at all.

- **Rejected on API load.** iNaturalist asks for under 10,000 requests per day, requests 60 requests
  per minute or fewer against a 100 per minute ceiling, returns HTTP 429 beyond that, and states that
  multiple IP addresses used in coordination to bypass the limits may be blocked. Pre-resolving one
  10,000-label model consumes an entire day's allowance for a single installation, and every
  installation would repeat it on each model change. The plausible outcome is throttling that denies
  names to everyone, which is the opposite of the intent.
- The problem it solves is also smaller than it appears. The lookup on the event path is wrapped in
  `asyncio.wait_for(..., EVENT_TAXONOMY_LOOKUP_TIMEOUT_SECONDS)`, two seconds by default, with a
  logged fallback. It costs one bounded delay the first time a species is seen, not a stall.

This changes how option A should be read. Measured against a background pre-resolve, a bundled
reference is the *considerate* design rather than the risky one: it moves the cost to a single
build-time extraction instead of recurring requests from every installation against a free
community service. The licensing question in the next section still governs whether it is available,
but load is now an argument in its favour rather than a neutral factor.

## Open decisions

Both must be resolved before implementation starts.

1. **Where the reference data comes from.** iNaturalist publishes a taxonomy export containing the
   full tree and common names, but states no licence for it; its open-data documentation addresses
   photographs only. Redistributing it cannot be justified on the public terms. The bundled
   MobileNet labels are Apache-2.0 (Google Coral, see `backend/app/assets/mobilenet-v2-inat-bird.NOTICE.md`)
   and pair 965 scientific names with common names. **Measured since: this covers only 860 of the
   1,486 birds the flagship model can emit, leaving 42% without a local name.** See the source
   decision above.
2. **Whether reference data belongs in the repository.** Model assets are deliberately not committed
   today — `backend/app/assets/labels.txt` is a three-line placeholder, and real labels arrive with
   the model. Committing a species table would change that policy.

## Consequences

- Offline and air-gapped installations resolve names for covered species.
- Naming becomes deterministic, so tests no longer depend on a live service.
- A species identity independent of the active model becomes available to history and statistics.
- A release step must regenerate the reference, and taxonomic revisions need a refresh policy.
- Localized common names continue to depend on enrichment and are unaffected.

## Already delivered

Two fixes from this investigation are merged and stand on their own, whichever option is chosen:

- A request that fails to reach iNaturalist is no longer recorded as "no such species", so an outage
  or rate limit cannot withhold a name.
- A cached not-found entry is re-tested after a retry window, which repairs installations already
  carrying a wrong negative. Nothing repaired them before: the only routine that force-refreshed
  such rows was never called, and has since been removed.

Between them, the permanent damage is fixed. What remains is one bounded delay the first time a
species is seen, which is what makes option D's cost impossible to justify.

## Validation

Figures in this document were read from a live deployment on 2026-08-05 and 2026-08-06: label
formats and counts from the installed model directories, cache size from `taxonomy_cache`, and name
column contents from `detections`. All 36 detections without a taxon id were `Unknown Bird`, so name
resolution on that deployment currently succeeds for every identified species.
