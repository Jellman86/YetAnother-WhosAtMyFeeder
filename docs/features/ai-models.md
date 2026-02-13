# AI Models & Performance

YA-WAMF supports multiple AI models, allowing you to balance speed, memory usage, and identification accuracy.

## The Model Market
You can manage models directly from the **Settings > Detection** page. The system supports two runtimes: **TensorFlow Lite** (Fast) and **ONNX** (High Accuracy).

> **Platform note:** Raspberry Pi compatibility is currently a best-effort ARM64 target and has not yet been validated on physical Pi hardware in this project environment.

### Available Tiers

#### 1. Fast (MobileNet V2)
- **Format:** TFLite
- **Accuracy:** ~70-80%
- **Speed:** Extremely Fast (~30ms)
- **Best for:** Low-power devices, ARM trials, or when you want instant results.

#### 2. High Accuracy (ConvNeXt Large)
- **Format:** ONNX
- **Accuracy:** ~90%
- **Speed:** Moderate (~500ms)
- **Memory:** Requires ~1GB RAM
- **Best for:** General use where accuracy is more important than raw speed.

#### 3. Elite Accuracy (EVA-02 Large)
- **Format:** ONNX
- **Accuracy:** ~91.6%
- **Speed:** Slow (~1s)
- **Memory:** Requires ~2GB RAM
- **Best for:** Identifying rare or similar-looking species.

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
