# October 2026 model integration validation

The integrated application was tested on Quark with the published model files and normal species
catalogue. These are diagnostics on a selected dataset, not a claim of population accuracy or a
reason to change the default for every installation. DINOv2 with configured location was the
strongest candidate for this feeder at its existing confidence thresholds.

## Public diagnostic

The normal ModelEvalRunner scored nine classifiers on the same 311 public images covering
149 species: 243 iNaturalist images and 68 Wikimedia images. All nine completed, with no skipped
models, producing 2,799 inference rows. DINOv2 used missing location, date and uncertainty.
The fixed European subset contains the same 230 images for every model, selected by the EU
catalogue vocabulary rather than by whether a prediction was correct. A narrower regional head
can be unable to name some species even in this subset. Scores compare canonical species identity,
with the existing conservative name fallback for unresolved taxonomy.

| Model | Correct / all 311 | Correct / fixed EU 230 | Top-5, all images | Images in vocabulary |
| --- | ---: | ---: | ---: | ---: |
| Current RoPE Wildlife 224 | 231/311 | 168/230 | 87.1% | 308/311 |
| DINOv2 without location | 231/311 | 171/230 | 86.5% | 308/311 |
| RoPE Wildlife 336 | 243/311 | 177/230 | 88.8% | 308/311 |
| RoPE EU 336 | 197/311 | 197/230 | 69.1% | 230/311 |
| Arabian RoPE DeiT3 | 144/311 | 143/230 | 52.7% | 190/311 |
| NaFlex EU | 201/311 | 201/230 | 70.7% | 230/311 |
| NaFlex Israel Birds | 169/311 | 168/230 | 59.5% | 193/311 |
| Parallel ViT EU | 193/311 | 193/230 | 68.5% | 230/311 |
| BioCLIP 2.5 application head | 274/311 | 207/230 | 93.9% | 305/311 |

BioCLIP leads this public panel, but its confidence accepts more incorrect feeder predictions
at the current threshold. Public accuracy alone therefore does not select the operating model.
The Arabian and Israel heads retain their intended regional scope; these images do not establish
performance in either region. The evaluation used an interim NaFlex ID ending in `global_birds`;
the released ID is `naflex_so150m_il_all`. This corrects its name and scope, with identical graph
and preprocessing checksums.

## Retained feeder replay

The 48 retained inputs include 42 birds and six squirrel negatives. Ten bird labels are owner
corrections: three from the initial panel and seven later corrections. The other 32 bird labels
and six squirrel labels are visual review. The panel is stratified from existing history, contains
difficult baseline mistakes, and may include repeated individuals. It is not an independent random
sample. No private images, coordinates or credentials are included in this report.

Each model used the actual saved application settings, including 0.6 confidence thresholds,
subprocess workers, automatic region selection, NPU preference and unchanged optional crop policy.
The normal input-context factory restored the retained Frigate snapshot provenance and aligned
hints; previously cropped inputs were respected. The history database was copied using SQLite
backup. Network integrations and history persistence were not started. DINOv2 used the saved feeder
coordinates at runtime; date and uncertainty remained absent.

| Model | Bird top-1 correct /42 | Correct birds accepted | Wrong birds accepted | Bird abstentions | Squirrels: correct / wrong / abstain |
| --- | ---: | ---: | ---: | ---: | --- |
| Current RoPE Wildlife 224 | 30/42 | 30 | 11 | 1 | 0 / 6 / 0 |
| DINOv2 with feeder location | 41/42 | 38 | 0 | 4 | 5 / 0 / 1 |
| RoPE Wildlife 336 | 33/42 | 29 | 2 | 11 | 6 / 0 / 0 |
| RoPE EU 336 | 34/42 | 31 | 3 | 8 | 0 / 0 / 6 |
| Arabian RoPE DeiT3 | 23/42 | 23 | 14 | 5 | 0 / 2 / 4 |
| NaFlex EU | 37/42 | 37 | 1 | 4 | 0 / 0 / 6 |
| NaFlex Israel Birds | 35/42 | 33 | 1 | 8 | 0 / 0 / 6 |
| Parallel ViT EU | 35/42 | 32 | 2 | 8 | 0 / 0 / 6 |
| BioCLIP 2.5 application head | 35/42 | 35 | 7 | 0 | 6 / 0 / 0 |

DINOv2 accepted 38 correct birds and no wrong bird species, versus 30 correct and 11 wrong for
the current RoPE 224. It correctly accepted five squirrels and abstained on one. Of the ten
owner-labelled bird cases, nine top predictions were correct; six were accepted and four abstained.
A correct top prediction below threshold remains an abstention. These findings support trying
DINOv2 with the existing 0.6 settings at this site, without lowering thresholds to make the result
look better. They do not prove location improves every capture or transfers to another feeder.

## Hardware, installation and load

- All eight new classifiers were downloaded afresh through unmodified ModelManager from the real
  GitHub release, verified by graph/weight checksums, and ready with no classifier `labels.txt`.
  BioCLIP verified each downloaded weight part and the complete assembled file. Existing release
  assets were retained; 30 new unique assets were verified against GitHub server digests.
- Exact integrated graphs were compared on 24 real inputs per provider against ONNX Runtime CPU.
  Every advertised tested Intel accelerator was finite and matched 24/24 CPU top predictions.
  Lower ranks and probabilities can differ; this is not a claim of bit-identical output. CUDA was
  not tested. NaFlex and Parallel ViT exclude NPU. See the [model reference](../features/model-catalogue-2026-10.md)
  for per-provider timings, memory estimates, scopes and preprocessing.
- The feeder replay produced 432 valid sequential predictions across all nine models. Each model
  then received five three-request simultaneous bursts through the real EventProcessor MQTT queue
  budget, followed by one recovery per burst: **135/135 concurrent requests and 45/45 recoveries**
  returned valid predictions matching the sequential top prediction. No overload, unexpected
  errors or recovery failures occurred in this warmed scenario. This is worker/admission testing;
  it is not an end-to-end MQTT/media/notification ingestion test.
- Official provider probes warmed fresh caches before the unchanged live-worker startup deadline.
  DINOv2 first-request latency was 8.9 seconds and subsequent median was 201 ms; these include the
  application worker path. BioCLIP first-request latency was 16.9 seconds. Warm success does not
  remove the known cold-cache compilation and memory costs, especially for BioCLIP.
- Protected production configuration, active selection, validation and eligibility hashes remained
  unchanged throughout these tests. The 682-row history snapshot retained identical logical and
  file hashes. All owned evaluation children exited; watchdog exit status was zero.

## Catalogue and reporting checks

All 18 registered classifier artifacts have checksum-bound output rows in the standard seed.
All seven original vocabularies were retained exactly. Ten unique vocabularies contain 43,092
ordered rows, including explicitly unresolved taxonomy; no species identity was guessed. Complete
index coverage, ordered-name digest and runtime output width are checked separately.

The completed public run exposed a reporting bug: valid catalogue-backed installs were given a
critical missing-label-file warning. Reporting now records `catalogue_labels_present` separately
from the truthful `labels_file_present: false`. A second fix makes parent-process label counts use
the resolved model checksum. Both have regression tests, and an isolated Quark audit of the latest
reporting code verified the correct label counts and no incomplete-install warning for all eight
fresh downloads. The audit also verified DINOv2 receives float32 `[1, 8]` metadata with the location
presence flag set and date/uncertainty absent. This audit did not repeat the accuracy inferences.

## Other screened candidates

The earlier candidate screening also covered HieraDet Small and ViT-M I-JEPA from the model
issue. Those exploratory runs preceded this final integration and are not substituted for the
integrated measurements above. HieraDet Small produced nonfinite Intel GPU output again and
failed on NPU; its CPU paths were finite, but no final feeder replay justified adding it.
ViT-M I-JEPA had finite Intel paths and matched CPU top-1 on the 24-image provider probe, but
its public diagnostic did not displace the shortlisted candidates. Neither was published as a
new supported application model. CUDA remains untested for the entire new shortlist.

## Evidence identifiers

Private raw evidence is retained outside the repository. The hashes below allow the published
counts to be traced without publishing feeder imagery or private settings.

| Evidence | SHA-256 |
| --- | --- |
| `integration-public-summary.json` | `7b4fdb162022b14eb7124771b601c5de91cf12fd74fd5f0a211bb7c2a0fd43fe` |
| `integration-public-results.jsonl` | `16c64b0951d2195f6eadf3f7f71dc01b61aa62f6350636e44d2bf7b59f3e5b59` |
| `integration-owner-final/results.jsonl` | `69d768dae81f7e17f3660e91ca70ecc0cfc6c7469606b5540420e00c6e346ef6` |
| `integration-owner-final/runner-result.json` | `ac671c944e1ed266e368f1876e1fea641199aff83b359f71b490f99729f92544` |
| `integration-reporting-audit.json` | `b13931c48527c058315a0544eeeecc4dcfeb49b0be9abeb5f732381fe97b4e42` |

Public harness run: `20261010-150324`. Feeder runner source SHA-256:
`63765b6aa59c917189be59ea4b7e4b225208cb764f8b411bc0f0c8b0bc32e597`.
See [mapping coverage](2026-10-10-model-output-mapping-coverage.md) and the
[model reference](../features/model-catalogue-2026-10.md) for the complete input and catalogue contracts.
