# Mapping model output indices to taxa

Date: 2026-08-19
Status: Partly implemented
Supersedes: the recommendation in
[2026-08-19-species-reference-source-decision.md](2026-08-19-species-reference-source-decision.md)
to drop the output-index criterion from `ROADMAP.md`

## The correction

That document recommended dropping the 3.0 exit criterion that binds each model output index to a
canonical taxon, on the grounds that index binding "buys nothing for resolution" and that the
acceptance test as written passes trivially.

The first half was wrong. It is true that index binding adds nothing to *matching a label to a
name*, which is what I was measuring. It was the wrong thing to measure. Index binding buys two
things text matching cannot:

1. **Coverage.** Text matching resolves what a redistributable source happens to contain. The
   flagship model reaches 57.9% of its birds that way, and the European models around a third.
2. **Integrity.** Text matching requires reading `labels.txt` at runtime, and that file is verified
   when a model is downloaded and never again. A label file altered afterwards is read as
   authoritative and its names are written into detection history.

## What makes this cheap

The scientific name is already in the label the model ships with.

| Model | Labels | Scientific name present in the label | Common-name only |
| --- | ---: | ---: | ---: |
| `rope_vit_b14_inat21` | 10,000 | **10,000** | 0 |
| `convnext_large_inat21` | 10,000 | 9,999 | 1 |
| `eva02_large_inat21` | 10,000 | 9,999 | 1 |
| `mobilenet_v2_birds` | 965 | 964 | 1 |
| `flexivit_il_all` | 550 | 0 | 550 |
| `eu_medium_focalnet_b` | 707 | 0 | 707 |
| `uniformer_s_eu_common` | 707 | 0 | 707 |

For the iNaturalist *hierarchy* format the mapping is **derivable from the model's own label file,
with no external source and no licence question at all**. A scientific name is a fact, and it is already
sitting in `04815_Animalia_Chordata_Aves_..._Cyanistes_caeruleus`.

That takes the flagship model from **57.9% to 100%** name coverage without redistributing anything
new. The bundled reference stops being the ceiling and becomes what it should always have been: a
source of *common* names for taxa the mapping already identifies.

The three common-name-only models carry no scientific name. eBird resolves 430/550 (78.2%) and
551/707 (78.0%) of their labels at build time. The remainder needs another source or stays
unresolved, and either way it is measured rather than assumed.

## Design

### The mapping

A table in the species reference keyed by the model artifact, not the model name:

```
model_taxon_map(model_key, output_index, scientific_name, source_label, source)
```

`model_key` is the label file's `sha256`. A republished model with corrected labels is a different
artifact and gets its own mapping, which is the property the roadmap's "immutable model artifact"
wording was reaching for. Nothing keys on a mutable name.

### When it is built

At model install, in the same step that already verifies `labels_sha256`. The label file is present
and proven at that moment, which is exactly when it should be turned into something durable.

That is also what closes the integrity gap: the mapping is derived from a verified file once, rather
than from an unverified file on every detection.

### What runtime does

The classifier already returns `{"index", "score", "label"}` and can resolve the active model id, so
the plumbing exists. Naming becomes: output index plus model key, look up the taxon, resolve names
through the existing layers.

Missing or ambiguous mappings **fail closed** to the current text path rather than guessing, so a
model with no mapping behaves exactly as it does today.

### Staging

1. **Build and store the mapping, and use it for naming.** Falls back to the text path when a
   mapping is absent. This is where the coverage and integrity wins land.
2. **Remove the runtime dependency on `labels.txt`.** The classifier still reads it for grouped
   labels and display, so that has to move to the mapping before the file can go. This is the step
   that satisfies the exit criterion's "without requiring model label text files at runtime".

Stage 1 is worth shipping on its own. Stage 2 is a refactor of the classifier's label handling and
should not ride along with it.

## Consequences

- The flagship model resolves every one of its 10,000 outputs to a taxon, offline, with no licensed
  data beyond what the model already ships.
- A `labels.txt` corrupted after download can no longer put wrong species into history, because the
  authoritative mapping was taken from the verified file.
- Coverage becomes a property that can be asserted per model, so "every shipped classifier has
  complete index coverage" is a test rather than a hope.
- The three common-name-only models remain partial until a source covers the last fifth.
- `ROADMAP.md` keeps its criterion. The reconciliation table in the source-decision document is
  wrong on that row and is corrected there.

## Validation

Label formats and counts were read from the model directories of a live deployment on 2026-08-19.
The classification of each label as carrying a scientific name, or a common name only, was made
against the eBird taxonomy rather than by pattern: an earlier pass using a binomial-shaped regular
expression counted "African crake" as a scientific name and was discarded.


## What is derived, and what is not

Two label formats guarantee a scientific name and are read without being told anything:

| Format | Example | Guarantee |
| --- | --- | --- |
| iNaturalist hierarchy | `04815_..._Cyanistes_caeruleus` | last two parts are genus and species |
| Paired | `Haemorhous cassinii (Cassin's Finch)` | the left half is the scientific name |

A bare `Genus species` is **not** read unless the caller states that the file holds scientific names,
because `Cyanistes caeruleus` and `African crake` are the same shape.

Two ways of guessing were tried against the real label files and both were rejected:

- A list of adjectives that cannot begin a genus claimed **198 common names as scientific** on
  `eu_medium_focalnet_b`, and would have written those into history as identities.
- A statistical discriminator, the ratio of distinct second words, separated the scientific files
  from the common-name files by only 0.65 against 0.31. A factor of two is not a margin worth
  betting species identity on.

So the rule is to derive only what the format guarantees and resolve everything else by lookup.

### Measured against the installed models

| Model | Labels | Mapped from the label alone | False positives |
| --- | ---: | ---: | ---: |
| `rope_vit_b14_inat21` | 10,000 | **10,000 (100%)** | 0 |
| `mobilenet_v2_birds` | 965 | 964 (99.9%) | 0 |
| `convnext_large_inat21` | 10,000 | 0 | 0 |
| `eva02_large_inat21` | 10,000 | 0 | 0 |
| `flexivit_il_all` | 550 | 0 | 0 |
| `eu_medium_focalnet_b` / `uniformer_s_eu_common` | 707 | 0 | 0 |

The flagship model, which is what the reference deployment runs, reaches **100%** with nothing
external. `convnext` and `eva02` use bare binomials and need one line in their model spec to say so.
The three common-name-only models need a build-time taxonomy lookup, which eBird satisfies for about
78% of their labels.

## Remaining work

1. ~~Declare the label format so bare-binomial files map without guessing.~~ Done: the two models
   whose labels are bare binomials are named in `label_integrity`, taking them from 0% to 100%.
2. ~~Verify the label file against its published checksum, and build the map from a proven file.~~
   Done, and the verdict is reported in classifier status.
3. Resolve common-name-only labels against a taxonomy, which eBird satisfies for about 78%.
4. Use the map for naming, falling back to the text path when a model has no mapping.
5. Move grouped labels and display off `labels.txt` so the file is not needed at runtime at all.

### Verification against installed models

Every label file on the reference deployment was checked against the checksum the registry
publishes. All seven match, so nothing has drifted, and the mechanism works end to end.

| Model | Verdict | Labels | Mapped |
| --- | --- | ---: | ---: |
| `rope_vit_b14_inat21` | verified | 10,000 | **10,000** |
| `convnext_large_inat21` | verified | 10,000 | **9,999** |
| `eva02_large_inat21` | verified | 10,000 | **9,999** |
| `mobilenet_v2_birds` | verified | 965 | 964 |
| `flexivit_il_all` | verified | 550 | 0 |
| `eu_medium_focalnet_b` | verified | 707 | 0 |
| `uniformer_s_eu_common` | unverifiable | 707 | 0 |

`uniformer_s_eu_common` is retired. Retired models keep their installed files so an operator can
roll back, and the registry no longer publishes a checksum for them, so `unverifiable` is the
correct verdict rather than a fault.

Two pairs of models share a label file and therefore one mapping, which is what keying on the
file's digest rather than the model name buys.

Region variants such as `small_birds/eu` carry no id of their own and hang off a parent under
`region_variants`, so resolving their checksum needs the region as well as the parent id.
