# Issues Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix incorrect species statistics, audio mapping issues, and reclassification bugs.

**Architecture:** 
- Update SQL queries in `DetectionRepository` to use `scientific_name` for consistent species grouping.
- Enhance `AudioService` to resolve scientific names for audio detections to allow robust correlation across languages.
- Align `reclassify_event` and `AutoVideoClassifierService` logic.

**Tech Stack:** Python, FastAPI, SQLite, Svelte (UI)

---

### Task 1: Fix Species Statistics Grouping (#15)

**Files:**
- Modify: `backend/app/repositories/detection_repository.py`

**Step 1: Update `get_species_counts` to include `d.scientific_name` in `unified_id`**

Modify line 1157:
```python
COALESCE(t.scientific_name, LOWER(d.scientific_name), LOWER(d.display_name)) as unified_id,
```

**Step 2: Update `get_species_leaderboard_base`**

Modify line 1188:
```python
COALESCE(t.scientific_name, LOWER(d.scientific_name), LOWER(d.display_name)) as unified_id,
```

**Step 3: Update `get_species_leaderboard_window`**

Modify line 1242:
```python
COALESCE(t.scientific_name, LOWER(d.scientific_name), LOWER(d.display_name)) as unified_id,
```

**Step 4: Update `get_daily_species_counts`**

Modify line 1640:
```python
COALESCE(t.scientific_name, LOWER(d.scientific_name), LOWER(d.display_name)) as unified_id,
```

**Step 5: Verify with existing tests**

Run: `pytest backend/tests/test_detection_repository.py`

---

### Task 2: Enhance Audio Correlation across Languages (#16)

**Files:**
- Modify: `backend/app/services/audio/audio_service.py`
- Modify: `backend/app/repositories/detection_repository.py`

**Step 1: Update `AudioDetection` dataclass to include `scientific_name`**

Modify `backend/app/services/audio/audio_service.py`:
```python
@dataclass
class AudioDetection:
    timestamp: datetime
    species: str
    confidence: float
    sensor_id: Optional[str]
    raw_data: dict
    scientific_name: Optional[str] = None
```

**Step 2: Update `add_detection` to resolve scientific name**

In `backend/app/services/audio/audio_service.py`, use `taxonomy_service.get_names()` to find the scientific name for the incoming audio detection.

**Step 3: Update `correlate_species` to match on scientific name**

In `backend/app/services/audio/audio_service.py`, update the loop to check both `detection.species` and `detection.scientific_name` against the query.

**Step 4: Update `audio_detections` table schema (optional but recommended)**

Actually, we'll stick to resolving it at ingestion and keeping it in the memory buffer for now to avoid a migration if possible, OR add it to the DB if we want persistence. Given the project has many migrations, adding a column is better.

**Step 5: Add `scientific_name` to `audio_detections` table via migration**

Run: `alembic revision -m "add scientific_name to audio_detections"`
Implement the upgrade/downgrade.

**Step 6: Update `DetectionRepository.insert_audio_detection`**

Include `scientific_name` in the insert.

---

### Task 3: Fix Reclassification Audio Loss (#16)

**Files:**
- Modify: `backend/app/routers/events.py`

**Step 1: Ensure `correlate_species` is called with robust names**

In `reclassify_event`, we are already passing `sci_name`. Ensure `AudioService.correlate_species` can handle it.

---

### Task 4: Fix Batch Reclassify UI Inconsistency (#17)

**Files:**
- Modify: `backend/app/routers/events.py`
- Modify: `backend/app/services/detection_service.py`

**Step 1: Refactor `reclassify_event` to use `DetectionService.apply_video_result`**

Unify the logic so that "reclassify" button and "auto analysis" behave identically.

---

### Task 5: CUDA Support Feature (#18)

**Files:**
- Modify: `backend/requirements.txt` (or `pyproject.toml` if used)
- Modify: `backend/app/services/classifier_service.py`
- Modify: `backend/app/config.py`
- Modify: `apps/ui/src/lib/api.ts`
- Modify: `apps/ui/src/lib/components/settings/DetectionSettings.svelte`

**Step 1: Switch to `onnxruntime-gpu`**

**Step 2: Update `ClassifierService` to use CUDA provider**

**Step 3: Make reclassification frame count configurable**
