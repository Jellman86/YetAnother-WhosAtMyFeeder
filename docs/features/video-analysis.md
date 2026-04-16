# Deep Video Analysis

While real-time detection uses a single snapshot, YA-WAMF provides a **Deep Video Analysis** mode for the most accurate identification possible. By sampling many frames from the full clip and combining their predictions, it significantly reduces errors from motion blur, partial occlusion, or a bad angle in a single frame.

## How It Works

1. The backend fetches the full video clip from Frigate.
2. It samples frames across the full clip using **deterministic stratified sampling** — the clip is divided into equal segments and one frame is taken from each. The default is **15 frames**, configurable in **Settings > Detection**.
3. Each frame is classified individually by the active model.
4. A **soft-voting ensemble** averages the top-N predictions across all frames, weighting by per-frame confidence.
5. The result replaces the single-snapshot identification for that detection.

## Running an Analysis

Click **Reclassify → Deep Video Analysis** on any detection card. This works for any detection that has an associated clip in Frigate (or a locally cached full-visit clip).

## Visual Feedback

During analysis, a real-time **progress overlay** appears on the detection card. It shows:

- How many frames have been processed so far
- The current leading species based on frames analyzed so far
- A progress bar counting toward the total frame count

Once complete, the detection card updates with the new result.

## Settings

| Setting | Location | Description |
|---------|----------|-------------|
| **Frame count** | Settings > Detection | Number of frames sampled per clip (default: 15). Higher values improve accuracy on long clips but take longer. |
| **Max concurrent jobs** | Settings > Detection | How many video analysis jobs can run in parallel (default: 1). Raise this if you have spare CPU/GPU headroom. |

## Requirements

- `record: enabled: True` must be set in your Frigate config, with `continuous.days` set to at least `1` so the recording exists when analysis runs.
- The active model must be downloaded. Deep Video Analysis uses the same model as real-time detection.

See the [Recommended Frigate Config](../setup/frigate-config.md) for the exact recording settings needed.
