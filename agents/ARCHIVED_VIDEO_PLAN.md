# Implementation Plan: Deep Video Reclassification

## 1. Overview
Enhance the classification accuracy by analyzing multiple frames from the associated Frigate video clip instead of relying on a single snapshot. This "Temporal Ensemble" approach reduces noise and leverages multiple viewing angles.

## 2. Technical Architecture

### Backend
- **Dependencies**: Add `opencv-python-headless` for efficient frame extraction.
- **Classifier Service**:
  - New method `classify_video(video_bytes, stride=5, max_frames=10)`.
  - Logic: Extract frames -> Classify each -> Aggregate scores (Soft Voting).
- **API Router**:
  - Update `POST /events/{id}/reclassify`.
  - Logic: Check `has_clip` -> Fetch clip if available -> Run Video Classification -> Fallback to Snapshot if fail/unavailable.

### Frontend
- **Detection Card**:
  - Update "Reclassify" button logic.
  - If `has_clip` is true, trigger "Deep Analysis" (Video).
  - Show explicit loading state ("Analyzing video frames...").
  - Provide visual feedback on success (e.g., "Confirmed by 8 frames").

## 3. Aggregation Strategy
**Soft Voting**:
Instead of just counting "votes" (hard voting), we sum the confidence scores for each species across all frames and normalize. This rewards species that are consistently detected with reasonable confidence, even if they aren't always the top-1 result in every single blurry frame.

## 4. Work Phases
1. **Infrastructure**: Add OpenCV dependencies.
2. **Backend Logic**: Implement frame extraction and ensemble scoring.
3. **API Integration**: Connect Frigate clip fetching to the classifier.
4. **UI UX**: Update the reclassify button to be "smart" and context-aware.
