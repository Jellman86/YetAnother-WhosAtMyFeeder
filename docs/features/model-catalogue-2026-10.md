# October 2026 classifier additions

Eight experimental classifiers extend the existing model catalogue. They require the
application integration that understands catalogue-only labels, native-aspect inputs and
DINOv2 metadata. Publishing their files on the rolling `models` release does not add these
capabilities to an older application image. Use Model Manager after updating to a build
containing this integration. The existing default and installed selections are preserved.

## Choose by coverage and cost

Download sizes include external weights, in MiB. Model RAM values are working-set estimates;
leave additional memory for the application, operating system and other services.

| Model | Output classes and coverage | Download | Estimated model RAM | Input contract | Position |
| --- | --- | ---: | ---: | --- | --- |
| DINOv2 B/14 with location | 10,000 iNat21 wildlife classes | 456.5 MiB | 2 GiB | RGB 336, bicubic centre crop, 0.875 crop fraction, ImageNet normalization; separate location input | Broad candidate; compare with RoPE and EVA rather than assuming published full-metadata accuracy applies |
| RoPE ViT-B14 Wildlife 336 | 10,000 iNat21 wildlife classes | 364.3 MiB | 1.5 GiB | RGB 336, direct resize, checkpoint mean/std | New checkpoint, distinct from the existing 224px RoPE; costs more inference time |
| RoPE ViT-B14 EU 336 | 707 European bird classes | 337.0 MiB | 1.5 GiB | RGB 336, centre crop 1.0, mean/std 0.5 | Regional comparison with FocalNet and Medium Birds; centre-crop policy retained after paired evaluation |
| RoPE DeiT3-M14 Arabian Peninsula | 735 regional bird classes | 151.6 MiB | 768 MiB | RGB 252, direct resize, checkpoint mean/std | Advanced regional option; a UK feeder panel cannot establish accuracy in its intended region |
| NaFlex SO150M EU | 707 European bird classes | 515.1 MiB | 2 GiB | RGB, native aspect, 14px patches, maximum 576 image tokens, mean/std 0.5 | Preserves shape; compare accepted mistakes as well as top-1 accuracy |
| NaFlex SO150M Israel Birds | 550 Israel-checklist bird classes, including rarities | 514.6 MiB | 2 GiB | Same native-aspect contract | Advanced regional option. `il-all` describes Israel, despite worldwide intermediate pretraining |
| Parallel ViT-S16 EU | 707 European bird classes | 247.4 MiB | 1.5 GiB | RGB 384, direct resize, mean/std 0.5 | Advanced CPU/GPU comparison; Intel NPU excluded after a compilation timeout |
| BioCLIP 2.5 Wildlife | Fixed 9,025-species iNat-intersection prototype head | 2,449.2 MiB | 8 GiB | RGB 224, bicubic centre crop 1.0, OpenCLIP normalization | Advanced comparison. Large cold-start and memory costs; confidence is not calibrated. This is not the full BioCLIP vocabulary |

All eight retain ONNX Runtime CPU and OpenVINO Intel CPU paths. Intel GPU is a host-gated
candidate for each. Intel NPU is a candidate for DINOv2, the three RoPE additions and BioCLIP;
it is excluded for both NaFlex models and Parallel ViT. Candidate status requires the exact
installation to pass the normal CPU comparison before selection. CUDA is a declared candidate,
but was not exercised on the Intel reference host. A provider being installed is insufficient.

New options do not automatically replace existing models. Region, admission thresholds,
accepted wrong predictions, abstentions, cold starts and queue contention all matter alongside
aggregate accuracy. Birds-only models cannot replace wildlife classifiers when squirrels or
other animals need identification. See [accuracy and methodology](model-accuracy.md).

## Species identities come from the catalogue

All 18 registered classifier artifacts now have checksum-bound, ordered output rows in the
species catalogue. Current installs use these rows for labels, classification, evaluation and
status, without requiring a classifier `labels.txt`. Existing installed text files and legacy
release downloads remain compatible. Custom or older models still use their verified file
fallback when no complete published catalogue mapping exists.

The eight new models have no label-file download. If their mapping is unavailable, installation
fails with an instruction to update the application. Graph and external-weight checksums come
from the reviewed registry; a downloaded sidecar cannot substitute another graph beneath a
catalogue mapping. Runtime checks also reject a catalogue/model output-width mismatch and verify ordered names
against the registry source digest, so editing or reordering complete catalogue rows is detected.

Every output index is retained, including unresolved taxonomy. The ten distinct vocabularies
contain 43,092 rows: 40,579 mapped species outputs, four declared non-species classes and
2,509 explicitly unresolved outputs. Shared vocabularies are counted once. Existing mappings
are preserved, so adding a checkpoint does not silently reinterpret historical detections.
See the [complete mapping evidence](../reviews/2026-10-10-model-output-mapping-coverage.md).

The [integration validation](../reviews/2026-10-10-model-integration-validation.md) records the
311-image public comparison, 48 retained feeder inputs per model, fresh release downloads and
180 concurrent/recovery requests on Quark. DINOv2 with saved location accepted 38 correct bird
identifications and no wrong bird species on this selected feeder panel at the existing 0.6
thresholds. BioCLIP led the public panel but accepted seven wrong feeder bird species at the same
threshold. These results do not establish a universal replacement or calibrated confidence.

## Location and downloads

DINOv2 receives the configured feeder latitude/longitude at inference time; coordinates are
not baked into the downloadable graph. Date and uncertainty remain absent. Missing or invalid
coordinates produce an all-zero metadata vector, while a real `(0, 0)` has a presence flag.
Changing or importing the location reloads classifier workers so they use the saved setting.
Model Manager explains this for location-aware models and links to **Settings → Integrations →
Location**. Switching there within Settings preserves unsaved edits; save the coordinates before
expecting them to change inference. Model-specific image preparation is automatic.
The October public accuracy comparison used location absent rather than borrowing the feeder's
location. Normal in-app diagnostics use the saved location; record that distinction when comparing
results. Published upstream full-metadata scores are not a score for this location-only policy.

BioCLIP's external weights exceed GitHub's per-file size limit. Model Manager downloads two
ordered parts, verifies each part, joins them into `model.onnx.data`, then verifies the complete
file. Installation remains staged; a failed download cannot replace a working model.

Source revisions, checkpoint hashes, ordered-output digests, graph and weight hashes are in
[`model_provenance_20261010.json`](../../backend/app/assets/model_provenance_20261010.json).
Preprocessing and provider policy are in the
[registry manifest](../../backend/app/assets/model_registry_20261010.json).
