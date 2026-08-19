# Species reference: resolving the source decision

Date: 2026-08-19
Note: the accepted design is
[2026-08-12-versioned-species-catalogue-design.md](2026-08-12-versioned-species-catalogue-design.md);
this document supplies its source measurements. See
[2026-08-19-species-catalogue-reconciliation.md](2026-08-19-species-catalogue-reconciliation.md).
Status: Implemented, except the Italian question. Resolves the two open decisions in
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
| Map each model output **index** to a taxon; stop treating label text as identity | Match on label text; no per-model artifact needed | **Superseded: follow the roadmap.** See [2026-08-19-model-output-index-mapping.md](2026-08-19-model-output-index-mapping.md). This row was wrong. It measured resolution only, and missed that index binding takes the flagship model from 57.9% to 100% coverage and removes an unverified runtime input. The original reasoning was: ** Index binding buys nothing for resolution, and the acceptance test as written ("two models with different label orders resolve the same bird to the same taxon") passes trivially when nothing keys on order. The real concern behind it is that label text can change when a model is republished, which is answered by treating model artifacts as immutable and checksummed, which they already are. |
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

- Decide the Italian question. Chinese is answered: fixing the locale resolution moved it from 7.1%
  to 30.8%, so Italian at 5.8% is the only locale left largely untranslated.
- The model-output-index mapping, if the roadmap keeps that criterion after the reconciliation above.


### The locale mapping was a live bug, not just a gap

`resolve_locale` normalized the *requested* locale from `pt_BR` to `pt-BR`, but compared it against
eBird's published codes unchanged, which use underscores. Its regional fallback tested
`code.startswith("pt-")` against values like `pt_AO`, so it could never match. eBird publishes no
bare `pt` either, so a Portuguese installation fell through every branch to English and silently
received English bird names.

Chinese resolved to the supported but sparse `zh` rather than `zh_SIM`, which carries four times as
many translated names.

Both are fixed. Codes are compared on one normalized form, and a bare language with a thin or absent
code takes its preferred regional variant. An explicit regional choice such as `zh_HK` is matched
exactly and is unaffected.


### Where localized names ended up

Not in the bundled file, and not in `taxonomy_translations`.

The bundled asset is read-only inside the image and replaced on update, so it cannot accumulate
anything. `taxonomy_translations` is keyed on an iNaturalist taxon id, which is exactly what a
reference-resolved species does not have, and its `language_code` column is five characters while
`zh_SIM` is six.

So localized names live in `species_names.db`, beside the application database, keyed on scientific
name. It is populated in bulk from eBird, one request per locale rather than one per species, and
carries no Alembic migration because it holds a reproducible copy of a public reference. Losing it
costs one refresh.

A name eBird returns unchanged from English is not stored. eBird answers with the English name when
it has no translation, and recording that would claim a translation we do not have, which is how a
locale like Italian would have looked complete while being 5.8% translated.


## What the bundled reference does and does not do

**It does not replace model label files.** The classifier loads `labels.txt` and indexes into it to
turn an output index into label text; the reference takes that text and resolves names from it. Both
are needed, and the reference cannot remove the label file while it keys on text.

That matters for the 3.0 exit criterion, which asks for names "without requiring model label text
files at runtime". Meeting it as written needs the output-index mapping this document recommends
dropping. The two positions are still unreconciled in `ROADMAP.md`, and that is a release-scope call.

### Measured resolution per model

Against the committed reference, using label files from a live deployment:

| Model | Labels | Resolved | Rate |
| --- | ---: | ---: | ---: |
| `rope_vit_b14_inat21` | 10,000 | 860 | 8.6% of all, 57.9% of its 1,486 birds |
| `convnext_large_inat21` | 10,000 | 860 | as above |
| `eva02_large_inat21` | 10,000 | 860 | as above |
| `mobilenet_v2_birds` | 965 | 964 | 99.9% |
| `flexivit_il_all` | 550 | 178 | 32.4% |
| `eu_medium_focalnet_b` | 707 | 234 | 33.1% |
| `uniformer_s_eu_common` | 707 | 234 | 33.1% |

**The European models get the least from it.** The bundled source is Google Coral's bird set, which
leans North American, so labels like `African blue tit`, `Algerian nuthatch` and `Arabian babbler`
are simply absent. Those installs depend on eBird and iNaturalist as before. This is a property of
the only permissively licensed source available, not of the matching.

### Correctness checks

- No duplicate common names in the reference, so a common-name match cannot resolve ambiguously.
- All 8,514 non-bird labels in the iNat model were checked against the reference: **none** resolves
  to a bird. A moth cannot be named a finch.


### Integrity of the shipped asset

The generator writes `species_reference.db.sha256` beside the database, and the runtime refuses a
file that does not match it. A reference altered on disk would write wrong species names into
detection history, which is worse than shipping no reference at all, so the failure is closed rather
than tolerated. A locally regenerated file with no sidecar is still used: absence is not corruption.

The build is reproducible. It carries no timestamp, so regenerating from the same labels produces a
byte-identical file, which is the only thing that makes a recorded digest checkable by a reviewer.
The input is identified by its own checksum in `reference_meta` instead.

### An adjacent gap, not addressed here

`labels_sha256` is verified when a model is downloaded and staged, but the label file is not checked
again when the model is loaded. A `labels.txt` altered or corrupted after download is read as
authoritative, and every detection classified against it is written to history under the wrong name.
That is a model-loading concern rather than a reference one, so it is recorded here rather than
changed as a side effect.


## New installs, and where a user's own names live

### Nothing is populated at first start

The bundled reference ships in the image and works immediately. The two things built at runtime do
not, because a fresh install has nothing to build from at the moment the refresh runs:

- **The model maps** are refreshed at startup, and a new install has no models yet. The map is now
  rebuilt when a model download completes, so a model chosen in the setup wizard is mapped straight
  away rather than at the next restart.
- **Localized names** are fetched at startup only when eBird is configured, and a new install has no
  key yet. They are now refreshed when the eBird key, language or enabled flag changes.

Both refreshes are detached and non-fatal. Neither can make a download or a settings save report a
failure it did not have.

### Renames belong in the application database, not here

`species_reference.db`, `species_names.db` and `model_taxon_map.db` are all rebuilt from their
sources. The reference is refused outright if it stops matching its checksum. A name a user chose
would be destroyed by the next rebuild, and writing it into the reference would break the file.

A rename already has a home: `taxonomy_cache.manual_common_name`, added by migration
`c7d8e9f0a1b2` and applied through `COALESCE(manual_common_name, common_name)`. It is user data, so
it is Alembic-migrated and backed up with everything else the owner would miss.

It also wins. `get_names` checks the cache before iNaturalist and before the bundled reference, so a
renamed species keeps its name whatever the reference says. A test asserts this rather than leaving
it to the ordering staying as it is.


## Superseded: the bundled source is now IOC, not Coral

The layered design above put eBird first at runtime and bundled only the 964 Coral species. That
made a free eBird account the thing standing between a European owner and names in their own
language, which is the wrong shape for a self-hosted application.

The IOC World Bird List is licensed **CC BY 3.0** and may be redistributed with attribution. It
carries 11,276 species and one *curated* name per language, which matters: aggregated sources return
several candidates with no way to choose between them, and for `Cyanistes caeruleus` GBIF offers
both `Cinciarella` and `Cinciallegra` as Italian, the second being the name of a different species.
Shipping that would be worse than shipping English, because the reader cannot tell it is wrong.

### Measured against every source

| | Coral bundled | eBird at runtime | **IOC bundled** |
| --- | ---: | ---: | ---: |
| Birds the flagship model emits | 57.9% | 94.9% | **95.2%** |
| `flexivit_il_all` labels | 32.4% | 78.2% | **90.2%** |
| `eu_medium_focalnet_b` labels | 33.1% | 77.9% | **88.1%** |
| Needs an API key | no | **yes** | no |

### Localized names

| Locale | eBird | **IOC** |
| --- | ---: | ---: |
| `de` | 98.5% | 98.3% |
| `es` | 99.9% | 98.2% |
| `fr` | 100% | 100% |
| `it` | **5.8%** | **90.5%** |
| `ja` | 94.4% | 95.4% |
| `pt` | 100% | 98.8% |
| `ru` | 92.8% | 96.1% |
| `zh` | **30.8%** | **100%** |

**This closes the Italian question**, which was the last item left open by this document. Italian
moves from effectively untranslated to 90.5%, and Chinese to complete, with no key and no network.

### Size

3.87 MB: 11,276 taxa and 87,656 localized names. A reverse index on `(locale, common_name)` would
have added 2.4 MB and nothing looks names up in that direction, so `taxon_name` is `WITHOUT ROWID`
and keyed only on the way it is read.

### What eBird is for now

An enhancement rather than a requirement: species IOC does not carry, and locales beyond the eight
bundled. The runtime store and its refresh remain, checked after the bundled list.
