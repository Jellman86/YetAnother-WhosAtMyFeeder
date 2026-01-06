# Deep Video Analysis

While real-time detection uses a single snapshot, YA-WAMF provides a "Deep Video Analysis" tool for the most accurate identification possible.

## How it works
When you click **"Reclassify > Deep Video Analysis"** on a detection:
1. The backend fetches the full video clip from Frigate.
2. It extracts **15 frames** using a Normal Distribution sampling (focusing on the middle of the clip).
3. Each frame is classified individually.
4. The system uses a **Soft-Voting Ensemble** logic to average the top predictions.
5. This multi-frame approach significantly reduces "glitch" identifications caused by motion blur or bad angles in a single snapshot.

## Visual Feedback
During the analysis, you will see a real-time progress overlay on the detection card. This shows exactly how many frames have been processed and the "winning" species for the last analyzed frame.
