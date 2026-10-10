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
in `tests/test_model_openvino_gpu.py` GPU_NOT_SUPPORTED:

- `davit_tiny_il_all` — clean compile, NaN output on iGPU. CPU-only.
- `mvit_v2_t_il_all` — process crash (`CL_OUT_OF_RESOURCES`) on iGPU. CPU-only.

Both work fine on CPU. Validate any new candidate the same way before declaring
iGPU support in the registry.

## Procedure

The conversion runs in a sidecar Python container — never install PyTorch into
the production runtime. The sidecar inherits the live container's volume mounts
via `--volumes-from` so the resulting ONNX lands directly in `/data/models/`.

```bash
# /tmp/convert_birder.py — the conversion script
# (see backend/docs/conversions/birder-model-conversion.md for the full file
#  or copy from a recent commit; it accepts <birder_id> <yawamf_dir_name>)

cat /tmp/convert_birder.py | docker run --rm -i \
    --volumes-from yawamf-monalithic \
    python:3.12-slim bash -c '
set -e
pip install --quiet --no-cache-dir torch torchvision \
    --index-url https://download.pytorch.org/whl/cpu
pip install --quiet --no-cache-dir birder onnx onnxruntime
cat > /script.py
python /script.py <birder_model_id> <yawamf_dir_name>
'
```

The script writes `model.onnx`, `model.onnx.data` (external weights),
`labels.txt`, and `model_config.json` into `/data/models/<yawamf_dir_name>/`.

## Quick iGPU compatibility check

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

### Probe the provider

Before adding the model to the registry with `intel_gpu` enabled, probe it
directly through OpenVINO inside a full or `-intel` live container. A CPU,
CUDA, or Raspberry Pi image does not package OpenVINO and is not evidence that
the model is incompatible:

```bash
docker exec yawamf-monalithic python -c "
import openvino as ov, numpy as np
core = ov.Core()
model = core.read_model('/data/models/<your_model>/model.onnx')
for dev in ['CPU', 'GPU']:
    try:
        compiled = core.compile_model(model, dev)
        req = compiled.create_infer_request()
        x = np.random.RandomState(7).rand(1, 3, <input_size>, <input_size>).astype(np.float32)
        out = req.infer({0: x})
        logits = list(out.values())[0].squeeze()
        print(dev, 'finite=', bool(np.all(np.isfinite(logits))), 'range=', float(np.ptp(logits)))
    except Exception as e:
        print(dev, 'FAILED:', str(e)[:120])
"
```

This one-image smoke test can reject an obviously broken provider, but it cannot make that provider
globally safe. Use the varied-image compatibility sweep to choose between the two registry fields:

| Probe outcome | Registry action |
|---|---|
| Repeated hardware/runtime matrices pass across supported installations | List `intel_gpu` in `supported_inference_providers` |
| Current install passes but older/currently supported stacks disagree | Keep the global safe list unchanged and add `intel_gpu` to `candidate_inference_providers` |
| GPU compile but non-finite or near-zero range | Exclude `intel_gpu`. Document in GPU_NOT_SUPPORTED |
| GPU compile crashes (CL_OUT_OF_RESOURCES, terminate, etc.) | Exclude `intel_gpu` AND add to GPU_CRASH_RISK |

## Registry entry

Add a new dict to `REMOTE_REGISTRY` in
`backend/app/services/model_manager.py`. Mirror the structure of the existing
`davit_tiny_il_all` entry: include all the metadata fields (tier, taxonomy_scope,
recommended_for, sort_order, etc.), set `download_url`/`labels_url`/
`model_config_url` to `"pending"` if the artifacts aren't published yet, and
make sure the `preprocessing` block matches what the conversion script actually
wrote into `model_config.json`.

## Test fixture updates

If you exclude `intel_gpu` based on probe results, add the model to
`GPU_NOT_SUPPORTED` in `tests/test_model_openvino_gpu.py` with a current-dated
reason. If it crashes the process, also add it to `GPU_CRASH_RISK`. The
registry-vs-validation-matrix guard test will fail until both sides agree.

You'll also need to update `test_list_available_models_returns_models_sorted_by_sort_order`
in `tests/test_model_manager_download.py` to include the new id at its
`sort_order` position.

## Validation through the harness

After the registry entry lands and CI rebuilds the dev image, kick off a model
evaluation harness run from `Settings → Debug → Model evaluation harness` (the Debug tab needs
`SYSTEM__DEBUG_UI_ENABLED=true`). The new model
will appear in the results table; check the `runtime.json` file under
`/config/yawamf-eval/<run_id>/` for the per-model `gpu_diagnostic` block to
confirm the active provider, observed compile result, and preprocessing match
what the registry declared.

After provider and crop-policy review, generate release-ready sidecars from the registry rather than
editing JSON assets by hand:

```bash
python backend/scripts/generate_model_release_configs.py /tmp/yawamf-model-configs
```

The output is the canonical install contract for runtime, input size, preprocessing, checksums,
globally safe and host-gated candidate provider policy, and classifier crop policy. Crop-detector
metadata remains a separate artifact contract and does not acquire the classifier
`crop_generator` block. Upload only after the model asset digests and a real-image provider sweep
agree with the registry.
