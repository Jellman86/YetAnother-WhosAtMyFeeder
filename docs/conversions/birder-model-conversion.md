# Converting Birder PyTorch models to YA-WAMF ONNX

The [Birder project](https://huggingface.co/birder-project) publishes pretrained
bird classifiers as PyTorch checkpoints. YA-WAMF runs ONNX, so adding a Birder
model means a one-time PyTorch → ONNX conversion.

## When to use this

You want a wider bird vocabulary than the existing `medium_birds` family or a
different architecture profile (DaViT, MViT, PVT, etc.). You're willing to do
empirical iGPU validation through the model evaluation harness afterward — the
historical pattern on this hardware is that anything bigger than ConvNeXt-V2-Tiny /
FocalNet-B fails on Intel iGPU (NaN logits, wrong predictions, or process crash).
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

Before adding the model to the registry with `intel_gpu` enabled, probe it
directly through OpenVINO inside the live container:

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

Use the result to decide what `supported_inference_providers` to declare:

| Probe outcome | Registry action |
|---|---|
| GPU compile + finite output + reasonable range | List `intel_gpu` |
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
evaluation harness run from `Settings → Debug → Model Evaluation`. The new model
will appear in the results table; check the `runtime.json` file under
`/config/yawamf-eval/<run_id>/` for the per-model `gpu_diagnostic` block to
confirm the active provider, observed compile result, and preprocessing match
what the registry declared.
