# Species reference: resolving the source decision

Date: 2026-08-19
Status: Partly implemented — the bundled layer is built and wired in; the eBird
layer is not yet. Resolves the two open decisions in
[2026-08-06-species-reference-and-name-resolution.md](2026-08-06-species-reference-and-name-resolution.md)

## Decision

Take reference data from three layers rather than one:

1. **eBird taxonomy, fetched at runtime with the installation's own API key.** 11,167 species with
   scientific and common names, and localized common names for most of the languages we present.
2. **A bundled baseline derived from the Coral MobileNet labels (Apache-2.0), shipped in the
   repository as a prepopulated SQLite file.** Covers installations with no eBird key and every
   offline install.
3. **iNaturalist, unchanged, as the gap filler** for anything neither layer covers.

Fetching eBird per installation with the owner's own key means no eBird data is redistributed, so
the licence question that blocked the earlier document does not arise for that layer. The bundled
layer is Apache-2.0 and may be committed.

## Why the earlier document could not proceed

It left two decisions open, and offered one permissively licensed candidate for the first:

> The bundled MobileNet labels are Apache-2.0 (Google Coral) and pair 965 scientific names with
> common names, which is a permissively licensed alternative covering the bird species this project
> cares about.

That claim was never measured. It does not hold.

## Measurements

Taken on 2026-08-19 from the label files installed on a live deployment, and from the eBird
taxonomy endpoint using that deployment's configured key.

`rope_vit_b14_inat21` carries 10,000 labels, of which **1,486 are Aves**. Coverage of those 1,486:

| Source | Covers | Percentage | Missing |
| --- | ---: | ---: | ---: |
| Coral MobileNet (Apache-2.0) | 860 | 57.9% | 626 |
| eBird taxonomy | 1,410 | **94.9%** | 76 |
| Both combined | 1,443 | 97.1% | 43 |

The Coral label set contains 964 usable scientific/common pairs, but only 860 of them are birds the
flagship model can emit. **Bundling Coral alone would leave 42% of this model's birds without a
local name**, which is the case the reference exists to remove.

Common-name matching is also lossier than the earlier document implies. For the two models whose
labels are common names only, matching those labels against eBird's English common names resolves
`flexivit_il_all` 430/550 (78.2%) and `eu_medium_focalnet_b` 551/707 (77.9%). Roughly a fifth of
labels do not match on common name, because naming authorities disagree. Scientific name is the
identity that survives; common name is a rendering.

### Localized names

eBird returns the whole taxonomy per locale. Measured as the number of species whose common name
differs from the English name, against the nine locales this project ships:

| Locale | eBird code | Translated | Note |
| --- | --- | ---: | --- |
| `de` | `de` | 98.5% | |
| `es` | `es` | 99.9% | |
| `fr` | `fr` | 100% | |
| `it` | `it` | **5.8%** | Effectively untranslated |
| `ja` | `ja` | 94.4% | |
| `pt` | `pt_BR` | 100% | `pt` alone returns 0%; the code must be `pt_BR` |
| `ru` | `ru` | 92.8% | |
| `zh` | `zh_SIM` | **30.8%** | `zh` alone returns 7.1% |

Six of the eight non-English locales are well covered. **Italian and Chinese are not**, and no
choice of locale code fixes them. That is a finding for the 3.0 exit criterion on translated names,
not a blocker: the criterion already permits residual limitations provided they are labelled
honestly. Either accept and state it, or add a fourth layer for those two languages. Wikidata is
CC0 and carries vernacular names in both, and is worth evaluating if we want to close the gap
rather than describe it.

## Sources considered and rejected

- **iNaturalist taxonomy export.** Unchanged from the earlier document: it states no licence, so
  redistribution cannot be justified. It remains available as a per-installation runtime lookup,
  which is what it already is.
- **GBIF Backbone (CC0), Catalogue of Life (CC-BY), IOC World Bird List (CC-BY).** All viable and
  all redistributable. Not selected because eBird already covers 94.9% at runtime with no
  redistribution and no new dependency, and the project already integrates it. Worth revisiting if
  the bundled baseline needs to be larger than Coral allows.

## What this changes in the code

The eBird layer is close to free. `ebird_service.get_taxonomy(locale)` already calls
`/ref/taxonomy/ebird` and caches the result in memory. What it needs is persistence into the
reference table, a locale mapping (`pt` to `pt_BR`, `zh` to `zh_SIM`), and a refresh policy.

The bundled layer needs a generator that reads the Coral labels and writes the baseline SQLite file,
plus a checksum so a shipped file can be verified. Shipping it in the repository is a change to the
current no-model-assets policy, and is accepted deliberately: this is reference data, not a model
artifact, it is small, and it is the layer that makes offline installs work.

## Reconciling with the 3.0 exit criteria

The earlier document and `ROADMAP.md` describe different systems. Three points differ, and the
roadmap should be amended rather than the design, except on the third.

| Roadmap says | Earlier design says | Recommendation |
| --- | --- | --- |
| A separately versioned SQLite catalogue | Seed into the existing `taxonomy_cache` | **Follow the roadmap.** A separate file is what makes the baseline shippable, checksummable and independently upgradable. The earlier design predates the decision to ship a prepopulated database. |
| Map each model output **index** to a taxon; stop treating label text as identity | Match on label text; no per-model artifact needed | **Follow the design, and amend the roadmap.** Index binding buys nothing for resolution, and the acceptance test as written ("two models with different label orders resolve the same bird to the same taxon") passes trivially when nothing keys on order. The real concern behind it is that label text can change when a model is republished, which is answered by treating model artifacts as immutable and checksummed, which they already are. |
| Supplies common, scientific **and translated** names | Localized names stay with enrichment, "unaffected" | **Follow the roadmap.** eBird supplies translated names for six of eight locales at no extra cost, so the criterion is now largely achievable. State the Italian and Chinese shortfall honestly. |

## Consequences

- Installations with an eBird key resolve 94.9% of the flagship model's birds locally, with
  localized names in six of eight non-English locales.
- Installations without one fall back to a bundled baseline covering 57.9%, then to iNaturalist.
- No eBird data is redistributed, because each installation fetches it under its own key.
- The repository gains a committed reference database and a generator that produces it.
- Italian and Chinese bird names remain largely English unless a fourth source is added.

## Open questions

- Whether to add Wikidata (CC0) for Italian and Chinese, or to state the limitation in the release
  notes as the exit criterion permits.
- The eBird refresh cadence. The taxonomy changes roughly annually; a check on model change plus a
  long periodic refresh is likely enough.

## Validation

Label counts and formats were read from the model directories of a live deployment on 2026-08-19.
The eBird figures come from `/ref/taxonomy/ebird` called with that deployment's configured key, once
per locale. Coverage percentages are set intersections on lower-cased scientific names; the
localization figures count species whose returned common name differs from the English one.


## Implementation notes

### Where the bundled layer actually sits

It resolves *after* iNaturalist, not before it. Placing it first was tried and rejected: the
reference carries no iNaturalist taxon id, so answering from it first cost the id for every covered
species, which enrichment needs. The full test suite caught this immediately.

That placement is also the honest one. The earlier document established that the network cost is
already one bounded, cached, two-second delay on first sight, so removing it was never the prize.
The prize is that an offline install, or one riding out an iNaturalist outage, gets a name at all.

A reference hit is not written to `taxonomy_cache`, because a row with no taxon id would stop a
later lookup supplying one.

### Shipping the asset

`backend/app/assets/species_reference.db` is committed. `.gitignore` carries `*.db`, so the file
needed an explicit negation; a test asserts it is not ignored, because the failure mode is silent
and the layer would simply never exist in a release.

Regenerate with:

```bash
python backend/scripts/build_species_reference.py --labels /path/to/mobilenet_v2_birds/labels.txt
```

The Dockerfile already downloads that label file with a pinned sha256, so the input is verified.

### Still to do

- Persist eBird taxonomy into `taxon_name` per locale, with `pt` mapped to `pt_BR` and `zh` to
  `zh_SIM`, and a refresh policy.
- Decide the Italian and Chinese question.
- The model-output-index mapping, if the roadmap keeps that criterion after the reconciliation above.
