# Accurate Crop Selection Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve selected crop recall for the `accurate` detector tier without changing `fast` tier behavior.

**Architecture:** Add per-tier effective crop-policy helpers to `BirdCropService`, then route selection and downstream crop-policy consumers through those helpers. Keep detector inference unchanged and verify the behavior with focused regression tests plus the existing crop-evaluation harness.

**Tech Stack:** Python, pytest, Pillow, YA-WAMF crop detector harness

---

### Task 1: Add failing tests for tier-aware crop selection

**Files:**
- Modify: `backend/tests/test_bird_crop_service_tiers.py`
- Modify: `backend/tests/test_bird_crop_service.py`

**Step 1: Write the failing tests**

Add tests covering:
- `accurate` accepts a `0.22` confidence candidate that would fail the legacy `0.35` threshold
- `accurate` accepts a valid `64x64` bird candidate that would fail the legacy `96x96` minimum
- `fast` still rejects those same candidates

**Step 2: Run tests to verify they fail**

Run: `cd /config/workspace/YA-WAMF && /config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_bird_crop_service_tiers.py backend/tests/test_bird_crop_service.py -q`

Expected: failures showing the current global crop policy still rejects the accurate-tier cases.

**Step 3: Commit**

Do not commit yet; continue to implementation after the red phase is confirmed.

### Task 2: Implement tier-aware effective crop-policy helpers

**Files:**
- Modify: `backend/app/services/bird_crop_service.py`

**Step 1: Write minimal implementation**

Add helper methods that compute effective crop policy from the detector tier, such as:
- effective confidence threshold
- effective minimum crop size
- optional compact policy dict for downstream callers

Use those helpers inside candidate selection and any downstream crop-policy paths that currently read `self.confidence_threshold` or `self.min_crop_size` directly.

**Step 2: Run focused tests to verify they pass**

Run: `cd /config/workspace/YA-WAMF && /config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_bird_crop_service_tiers.py backend/tests/test_bird_crop_service.py -q`

Expected: PASS

**Step 3: Refactor lightly**

Keep helper names clear and avoid duplicating tier checks across the service.

### Task 3: Verify downstream behavior and harness improvement

**Files:**
- No required code changes unless verification reveals a missed consumer

**Step 1: Run broader crop-detector tests**

Run: `cd /config/workspace/YA-WAMF && /config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_bird_crop_service.py backend/tests/test_bird_crop_service_tiers.py backend/tests/test_bird_crop_yolox_adapter.py backend/tests/test_crop_detector_eval_harness.py tests/unit/test_crop_detector_registry.py -q`

Expected: PASS

**Step 2: Run the crop harness in the live container**

Run the existing container harness flow and compare selected metrics for `accurate` before/after the change.

Expected:
- selected `accurate` recall improves materially
- no detector-load or inference regressions

**Step 3: Commit**

```bash
git -C /config/workspace/YA-WAMF add \
  backend/app/services/bird_crop_service.py \
  backend/tests/test_bird_crop_service.py \
  backend/tests/test_bird_crop_service_tiers.py \
  docs/plans/2026-04-17-accurate-crop-selection-design.md \
  docs/plans/2026-04-17-accurate-crop-selection.md
git -C /config/workspace/YA-WAMF commit -m "Improve accurate crop selection recall"
```
