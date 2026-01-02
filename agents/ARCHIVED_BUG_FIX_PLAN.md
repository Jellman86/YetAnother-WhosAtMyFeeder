# Bug Fix Plan

## 1. Fix Model Downloader (Critical)
- **Issue**: The download URL for `EfficientNet-Lite4` returns 404.
- **Fix**: Update `backend/app/services/model_manager.py` with valid URLs.
    - Use `https://storage.googleapis.com/cloud-tpu-checkpoints/efficientnet/lite/efficientnet-lite4-int8.tflite` (or similar valid quant model).
    - Ensure `MobileNetV2` URL is also valid.
- **Verification**: Trigger download from UI and check logs for 200 OK.

## 2. Fix Dashboard Navigation (Critical)
- **Issue**: Clicking a species in "Top Visitors" leads to a blank screen.
- **Root Cause**: `Events.svelte` might not be correctly parsing the `date=today` URL parameter or the filter logic is crashing.
- **Fix**:
    - Audit `apps/ui/src/lib/pages/Events.svelte`'s `parseUrlParams` function.
    - Ensure `datePreset = 'today'` is set correctly when `date=today` is in the URL.
    - Add error boundaries or safe defaults if parsing fails.

## 3. Fix BirdNET-Go UI (High)
- **Issue**: "Audio Analysis" UI is missing.
- **Fix**:
    - Check `Settings.svelte`. The section might be wrapped in an `if` block that evaluates to false (e.g., waiting for `birdnet-go` discovery which might not be implemented).
    - Ensure the "Listening" indicator in `App.svelte` header correctly reflects the state.
    - Force the Audio Settings section to be visible if it's meant to be user-configurable.

## 4. Polish & Cleanup
- **Issue**: Default model not showing as downloaded.
- **Fix**:
    - Update `ModelManager.list_installed_models` to check the `assets/` folder for bundled models if they aren't in `/data/models`.
    - Ensure the UI reflects "Installed" state for bundled models.
