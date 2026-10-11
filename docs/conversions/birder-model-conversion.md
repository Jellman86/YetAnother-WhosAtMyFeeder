# Converting Birder PyTorch models to YA-WAMF ONNX

The [Birder project](https://huggingface.co/birder-project) publishes pretrained
bird classifiers as PyTorch checkpoints. YA-WAMF runs ONNX, so adding a Birder
model means a one-time PyTorch → ONNX conversion.

## When to use this

You want a wider bird vocabulary than the existing `medium_birds` family or a
different architecture profile (DaViT, MViT, PVT, etc.). You're willing to do
empirical iGPU validation through the model evaluation harness afterward. Older OpenVINO stacks
often produced NaN logits, wrong predictions, or process crashes for larger architectures, while
current Quark/OpenVINO validation shows that some of those results are runtime-specific. ConvNeXt
Large, for example, failed on OpenVINO 2025.4.1 but matches CPU on the current 2026.2.1 stack.
Two recently-converted candidates that both **fail on iGPU** are documented
in the legacy OpenVINO diagnostic tests under `backend/tests/additional/`:

- `davit_tiny_il_all` — clean compile, NaN output on iGPU. CPU-only.
- `mvit_v2_t_il_all` — process crash (`CL_OUT_OF_RESOURCES`) on iGPU. CPU-only.

Both work fine on CPU. Validate any new candidate the same way before declaring
iGPU support in the registry.

## Export in an isolated workspace

Use a disposable Python 3.12 environment with pinned PyTorch, Birder, ONNX and ONNX Runtime
versions appropriate to the checkpoint. Record those versions, the upstream revision and weight
hash. Never install conversion dependencies in the running application or write an unvalidated
export into its active model directory.

The committed exporter is `backend/scripts/export_and_config_birder_model.py`. From the repository
root in that conversion environment:

```bash
python backend/scripts/export_and_config_birder_model.py \
  --model focalnet_b_lrf_intermediate-eu-common \
  --output_dir /tmp/yawamf-conversion/focalnet-eu \
  --taxonomy_scope birds_only
```

This older exporter creates ONNX weights, `model_config.json` and a build-time `labels.txt`.
Preserve the original checkpoint output order. The text file can serve as a conversion input;
new registered models should resolve outputs through the species catalogue and should not need
a text label file at installation. Complete the catalogue procedure below before publishing.
Do not assume this generic exporter implements a newer architecture's dynamic shape or metadata
inputs. Use and verify the architecture-specific export contract where required.

## Verify preprocessing and predictions

### Verify the input contract first

Read the exact checkpoint's inference transform before choosing sidecar metadata. Record RGB or
BGR channel order, tensor layout and dtype, pixel scaling, mean/std, interpolation, resize policy,
input dimensions, and any patch or token constraints. A transform using `Resize((height, width))`
performs a direct resize; `Resize(shortest_edge)` preserves aspect ratio before a centre crop.
These policies can produce different predictions with identical weights.

Centre-crop sidecars can declare `resize_rounding: "floor"` when their reference transform truncates
the resized long edge, as torchvision does. Omitting this field preserves YA-WAMF's existing
round-to-nearest behaviour. Do not change installed models' resize policies merely because another
policy matches an upstream example: compare both policies on the same public and feeder images.

Compare actual application-prepared tensors against the native transform on varied landscape,
portrait and feeder images, including a channel-colour sentinel. Then compare finite logits and
top-1/top-5 predictions between native PyTorch and ONNX. Dynamic-aspect models need rectangular
input checks at multiple patch-aligned sizes; a successful square-only export proves too little.

Replay cached feeder images with their validated snapshot provenance and retained aligned event
hints through `build_snapshot_classification_input_context`. Frigate snapshot crop restoration
is independent of optional model cropping: a full snapshot may need its event region restored
even when model cropping is disabled, while an already-cropped snapshot must retain that flag.
Verify the selected RGB pixel hashes and dimensions across candidates. A raw-image replay with
synthetic context measures a different input path and cannot establish original-event behaviour.

The published YOLOX reference uses its own contract: BGR, contiguous float32 NCHW, unscaled 0–255
pixels, OpenCV linear resize with truncated dimensions, and top-left padding of 114. Classifier
normalization must not be reused for that detector. Its box restoration uses the same letterbox
scale and offsets. YA-WAMF currently uses Pillow resizing and rounded dimensions; changing that
implementation also changes crop selections. Compare downstream classification and rejection
behaviour before changing an installed detector. See the [upstream preprocessing](https://github.com/Megvii-BaseDetection/YOLOX/blob/main/yolox/data/data_augment.py).

### Probe the provider in a disposable process

Use the strict [installed-model/provider gate](../development/testing.md#mandatory-local-modelprovider-gate)
on a trusted hardware host with the matching provider dependencies. It uses real images, an
isolated child and a CPU baseline, retains failed runs and rejects timeouts, non-finite output
or provider mismatch. A random tensor compile check cannot establish preprocessing parity,
species accuracy or production stability. Do not run native debug inference in the live API
process: a native crash can take that process down.

A passing local probe can justify a host-gated candidate provider. It does not establish
universal GPU/NPU support. Keep unsupported combinations excluded and retain crashes as negative
evidence even when a later repeat passes. Run labelled accuracy comparisons separately.

## Register and package the model

Add the complete artifact contract to `REMOTE_REGISTRY` in
`backend/app/services/model_manager.py`: model identity, source revision, checksums, coverage,
preprocessing, input/output contract, crop policy and provider policy. Review comparable current
entries rather than copying an older model's supported-device list. Publish only complete,
checksum-verifiable assets; do not expose placeholder download URLs as installable models.

The regression tests now live in `backend/tests/`, including migrated cases in
`backend/tests/additional/`. Update the model-manager registry/download, catalogue mapping,
preprocessing and provider-policy tests affected by the new contract. Use the shared
[regression gate](../development/testing.md), not obsolete root `tests/` paths.

After the catalogue mappings are built, generate canonical release sidecars:

```bash
python backend/scripts/generate_model_release_configs.py /tmp/yawamf-model-configs
```

Review generated configs and asset digests against the real export before uploading. Retain
existing release asset names and bytes for older applications. The [Model evaluation guide](../features/model-evaluation.md)
explains the in-application compatibility sweep, its downloads, temporary model switching,
restoration and results. Compatibility and active-provider reporting are separate from a
labelled accuracy benchmark.

## Catalogue-only classifiers and October 2026 artifacts

The generic exporter above creates label files for legacy/custom models and conversion inputs. New registered
classifiers use ordered output mappings compiled into the species catalogue. Their build input
can be a JSON object keyed by the SHA-256 of canonical UTF-8 names (each followed by a newline),
with an array of source names in the exact checkpoint output order. Keep that source immutable;
never alphabetize it or substitute a translated name list.

Extend the released mapping rather than recompiling old identities:

```bash
cd backend
python scripts/build_model_output_mappings.py \
  --output-sources /scratch/ordered-output-sources.json \
  --base-mappings /scratch/released-model-output-mappings.json
python scripts/build_species_catalog_seed.py
python scripts/generate_model_release_configs.py /scratch/release-configs
```

The extension verifies source digests, preserves existing vocabulary rows and adds the new
checksum-bound artifacts. The normal catalogue release importer adds those mappings to existing
installations without replacing their history or overrides. A complete ordered mapping is
required before a new label-free artifact can be downloaded. Publish canonical generated
sidecars and unique model asset names; keep old release assets available for older applications.

For portable DINOv2, use `backend/scripts/export_dinov2_model.py` with the pinned upstream checkout,
reviewed E4a checkpoint and official iNat2021 validation annotations. The exporter checks the
checkpoint digest and its class-mapping fingerprint before creating two inputs: float32 NCHW RGB
`input` of shape `[1,3,336,336]`, and float32 `metadata` of shape `[1,8]`. It compares ONNX against
native PyTorch with missing and present synthetic locations. Site coordinates must never be
constants in a redistributed export. Date and uncertainty remain absent in the application.

NaFlex exports must accept rectangular patch-aligned inputs and preserve the reference 576-token
budget. Set `resize_mode: native_aspect_ratio`, `patch_size: 14` and `max_seq_len: 576`; do not
pad or stretch to 336 square. Test square, landscape and portrait tensors against the upstream
transform and native network. External tensor locations must be `model.onnx.data`, matching
Model Manager's local filename. Intel NPU is excluded for these variable-aspect exports.

BioCLIP 2.5 is an application-specific image encoder plus a fixed head of 9,025 normalized
species text prototypes in their recorded order. Its graph is not a substitute for the full
upstream vocabulary or an arbitrary prompt interface. Weights are shipped as two ordered parts
with separate digests and a complete-file digest; the downloader reconstructs the original
external-data file before committing the installation.

The [model additions reference](../features/model-catalogue-2026-10.md) links source revisions,
checkpoint hashes, output-source hashes, preprocessing, provider policy and mapping coverage.
