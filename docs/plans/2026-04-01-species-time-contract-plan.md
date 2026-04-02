# Species And Time Contract Alignment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Align downstream contracts with the recent species-normalization and UTC work so rolling-window counts, species thumbnails, and adjacent timestamp responses are correct and explicit.

**Architecture:** Keep the current rolling-24h summary model, then update dependent surfaces to match it. Fix summary aggregation at the repository/query layer, normalize touched non-`APIModel` timestamp endpoints onto the shared serializer, and adjust Home Assistant entity semantics to reflect a rolling measurement instead of a monotonic daily counter.

**Tech Stack:** FastAPI, Pydantic, aiosqlite, Home Assistant custom component tests, pytest.

---

### Task 1: Lock Daily Summary Latest-Event Semantics

**Files:**
- Modify: `backend/tests/test_stats_unknown_api.py`
- Modify: `backend/app/repositories/detection_repository.py`

**Step 1: Write the failing test**

Add a regression showing two detections in one normalized species bucket where the lexicographically larger `frigate_event` is not the latest by `detection_time`, and assert `/api/stats/daily-summary` returns the event from the newest detection.

**Step 2: Run test to verify it fails**

Run the focused pytest selection for the new summary test and confirm the current query returns the wrong event.

**Step 3: Write minimal implementation**

Change daily species aggregation to pick representative event ids by latest detection time rather than `MAX(frigate_event)`, including unknown-label rollups.

**Step 4: Run test to verify it passes**

Re-run the focused pytest selection and confirm the new test passes.

### Task 2: Lock Home Assistant Rolling-Window Semantics

**Files:**
- Modify: `backend/tests/test_home_assistant_sensor.py`
- Modify: `custom_components/yawamf/coordinator.py`
- Modify: `custom_components/yawamf/sensor.py`

**Step 1: Write the failing test**

Add a test asserting the count entity is modeled as a rolling-window measurement and does not advertise `TOTAL_INCREASING` semantics after the daily-summary UTC fix.

**Step 2: Run test to verify it fails**

Run the focused HA sensor test and confirm the current entity still exposes `TOTAL_INCREASING`.

**Step 3: Write minimal implementation**

Rename the internal coordinator field away from `total_today` if needed for clarity, remove the monotonic state class from the HA count sensor, and make the entity/attributes explicitly describe a rolling 24-hour window.

**Step 4: Run test to verify it passes**

Re-run the focused HA sensor test and confirm the entity semantics now match the rolling summary contract.

### Task 3: Normalize Touched Timestamp Responses

**Files:**
- Modify: `backend/tests/test_error_diagnostics_api.py` or create a focused API serialization test file if clearer
- Modify: `backend/app/routers/ai.py`
- Modify: `backend/app/routers/proxy.py`
- Reference: `backend/app/utils/api_datetime.py`

**Step 1: Write the failing tests**

Add focused API/unit tests for the touched AI/proxy responses to assert explicit UTC serialization rather than naive `.isoformat()` output.

**Step 2: Run tests to verify they fail**

Run the focused pytest selections and confirm the current responses still emit mixed timestamp formats.

**Step 3: Write minimal implementation**

Switch the touched response builders onto the shared datetime serializer.

**Step 4: Run tests to verify they pass**

Re-run the focused timestamp serialization tests and confirm the contract is explicit UTC.

### Task 4: Verify And Document

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Run focused verification**

Run the backend daily-summary tests, HA sensor tests, and timestamp serialization tests together.

**Step 2: Update changelog**

Add a concise note covering rolling-window HA semantics, daily summary representative event selection, and timestamp serialization cleanup.

**Step 3: Re-run verification**

Run the same focused commands again after docs changes if required.
