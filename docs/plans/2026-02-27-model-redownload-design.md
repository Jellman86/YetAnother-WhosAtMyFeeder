# Model Re-download Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a model re-download action in the UI for installed models, with visible progress for all downloads/re-downloads, while making backend model replacement safe and non-destructive on failure.

**Architecture:** Keep the existing `/api/models/{model_id}/download` endpoint and extend backend download internals to use staged downloads plus validated swap into the final model directory. Update the Svelte `ModelManager` card actions to expose `Re-download` for installed models and reuse existing per-model progress polling for both initial downloads and re-downloads.

**Tech Stack:** FastAPI, Python (`httpx`, `aiofiles`, `pytest`), Svelte 5, TypeScript.

---

### Task 1: Backend safety tests (TDD RED)

**Files:**
- Create: `backend/tests/test_model_manager_download.py`
- Test: `backend/tests/test_model_manager_download.py`

**Step 1: Write failing tests**
- Add tests that validate:
- `_swap_model_dirs` restores prior model when second rename fails.
- `_download_required_assets` reports error when expected files are missing.

**Step 2: Run tests to verify failure**
- Run: `cd backend && pytest tests/test_model_manager_download.py -q`
- Expected: failing tests before implementation.

### Task 2: Backend model download hardening

**Files:**
- Modify: `backend/app/services/model_manager.py`
- Test: `backend/tests/test_model_manager_download.py`

**Step 1: Implement staged download helpers**
- Add helper to download into a temporary staging directory.
- Add helper to validate required files exist before swap.
- Add helper to atomically replace target directory with rollback.

**Step 2: Integrate helpers in `download_model`**
- Keep progress updates in `active_downloads`.
- For re-download, never write into current installed dir directly.
- On any failure, preserve existing installed model directory.

**Step 3: Run tests**
- Run: `cd backend && pytest tests/test_model_manager_download.py -q`
- Expected: PASS.

### Task 3: UI re-download controls and progress state

**Files:**
- Modify: `apps/ui/src/lib/pages/models/ModelManager.svelte`

**Step 1: Add re-download action for installed cards**
- Active model card: `Currently Active` status plus a `Re-download` button.
- Installed non-active card: `Activate` and `Re-download` buttons together.

**Step 2: Reuse progress polling for all model transfers**
- Keep per-model progress bar visible while status is `pending/downloading`.
- Ensure button labels and disabled states reflect `Re-downloading...`.

**Step 3: Guard against duplicate clicks**
- Prevent triggering another request while same model is already pending/downloading.

### Task 4: Verification

**Files:**
- Verify: `backend/tests/test_model_manager_download.py`
- Verify: `apps/ui/src/lib/pages/models/ModelManager.svelte`

**Step 1: Backend tests**
- Run: `cd backend && pytest tests/test_model_manager_download.py -q`

**Step 2: Frontend checks**
- Run: `cd apps/ui && npm run check`

**Step 3: Final sanity**
- Confirm `Re-download` is visible only for installed models.
- Confirm progress appears for both download and re-download flows.
