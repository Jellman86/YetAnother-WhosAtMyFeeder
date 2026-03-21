# AI Models & Performance

YA-WAMF supports multiple AI models, allowing you to balance speed, memory usage, and identification accuracy.

## The Model Market
You can manage models directly from the **Settings > Detection** page. The system supports two runtimes: **TensorFlow Lite** (Fast) and **ONNX** (High Accuracy).

> **Platform note:** Raspberry Pi compatibility is currently a best-effort ARM64 target and has not yet been validated on physical Pi hardware in this project environment.

## Inference Providers (CPU / CUDA / Intel OpenVINO)

For ONNX models (ConvNeXt / EVA-02), YA-WAMF supports a provider selector in **Settings > Detection**:

- `Auto` (recommended): prefers **Intel GPU (OpenVINO)**, then **NVIDIA CUDA**, then CPU.
- `CPU`: ONNX Runtime CPU execution.
- `NVIDIA CUDA`: ONNX Runtime with CUDA (falls back to CPU if CUDA is not actually usable).
- `Intel GPU (OpenVINO)`: OpenVINO GPU plugin (falls back to OpenVINO CPU if the Intel GPU is unavailable).
- `Intel CPU (OpenVINO)`: OpenVINO CPU execution.

### Important behavior (robust fallback)

YA-WAMF intentionally fails soft when acceleration is misconfigured:

- If a provider is selected but unavailable, the backend falls back to a working provider.
- The UI shows:
  - **Selected provider**
  - **Active provider**
  - **Backend** (`onnxruntime` or `openvino`)
  - **Fallback reason**
- CUDA and OpenVINO availability are probed separately from model loading, then validated again during runtime initialization.

### What counts as "available"

- **CUDA available** means:
  - ONNX Runtime CUDA provider is present in the installed wheel, and
  - an NVIDIA CUDA device is actually accessible (not just CUDA-enabled packages installed).
- **OpenVINO available** means:
  - OpenVINO imports successfully, and
  - OpenVINO runtime can initialize.
- **Intel GPU auto-detected** means:
  - OpenVINO enumerated a GPU device (or `GPU.*`) and can expose it to YA-WAMF.

If you only see `OpenVINO: Available` + `Intel GPU: Not detected`, YA-WAMF can still use **OpenVINO CPU**.

### Available Tiers

> **See [Model Accuracy & Benchmarks](model-accuracy.md)** for full benchmark results, GPU support details, and how to run the accuracy tests yourself.

#### Recommended: RoPE ViT-B14 (Default)
- **Format:** ONNX, 375MB
- **Accuracy:** ~70% top-1, 87% top-5 (10,000 species)
- **Speed:** ~474ms on Intel CPU
- **Best for:** General-purpose wildlife identification — best balance of accuracy and speed.

#### Large: ConvNeXt Large
- **Format:** ONNX, 760MB
- **Accuracy:** ~70% top-1, 87% top-5 (10,000 species)
- **Speed:** ~832ms on Intel CPU
- **Best for:** Alternative to RoPE ViT with similar accuracy but higher memory usage.

#### Advanced: EVA-02 Large
- **Format:** ONNX, 1.2GB
- **Accuracy:** ~75% top-1, 88% top-5 (10,000 species)
- **Speed:** ~1.6s on Intel CPU
- **Memory:** Requires ~3GB RAM
- **Best for:** Highest available accuracy — worth the extra cost for rare or difficult species.

#### Small: HieraDeT / FlexiViT
- Compact models for lower-memory systems or quick checks.
- HieraDeT DINOv2: 70% top-1, 159MB
- HieraDeT ViT Small: 62% top-1, 167MB

#### Regional Birds-Only (Small/Medium)
- Dedicated EU or NA models with higher confidence scores within their region.
- Smaller label space (707 species) — use when you want cleaner confidence scores for feeder birds.

#### Legacy TFLite (MobileNet V2 / EfficientNet Lite4)
- **Format:** TFLite — runs on CPU-only systems without ONNX Runtime
- **Accuracy:** ~67% top-1, ~73% top-5 (965 species)
- **Speed:** ~13ms
- Hidden by default in the UI. Use only for very constrained hardware.

## Automatic Video Analysis (Deep Analysis)
In addition to snapshot classification, YA-WAMF can perform **Deep Video Analysis**. This background task scans the full video clip frame-by-frame (temporal ensemble) to verify the identification.

![Deep Video Analysis](../images/event_details_modal.png)

This provides significantly higher confidence by seeing the bird from multiple angles and in motion.


## Fast Path Efficiency
If **"Trust Frigate Sublabels"** is enabled, the system will bypass its own AI classification if Frigate has already identified the species. This saves CPU cycles and is recommended if you have already tuned Frigate's own classification models.

## Behavioral Analysis (LLMs)
For advanced insights, YA-WAMF can send high-confidence snapshots to a Large Language Model (LLM) to generate a "Naturalist Note".

- **Default Provider:** Google Gemini
- **Default Model:** `gemini-2.0-flash-exp` (High speed, multimodal)
- **Alternative:** OpenAI `gpt-4o`

The LLM analyzes the image context (weather, behavior, plumage) and provides a short, educational summary of what the bird is doing. This feature requires an API key.
