# HQ Snapshot Repair Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Persist bounded HQ snapshot candidates per detection, improve automatic HQ snapshot selection, and add an owner-facing detection-modal workflow to repair or revert snapshots.

**Architecture:** Extend the existing high-quality snapshot service to generate and rank a small candidate set, persist candidate metadata in SQLite plus small thumbnails in the media cache, and expose owner-only APIs for inspecting and applying candidates. The detection modal then becomes a thin client over that backend state.

**Tech Stack:** FastAPI, aiosqlite repository layer, existing media cache, Svelte UI, pytest, vitest.

---

### Task 1: Add snapshot candidate persistence

**Files:**
- Modify: `backend/app/database.py`
- Modify: `backend/app/repositories/detection_repository.py`
- Create: `backend/tests/test_snapshot_candidate_repository.py`

**Step 1: Write the failing test**

Add repository tests for:
- insert candidate rows for an event
- replace prior candidate set for the same event
- mark one candidate selected
- fetch candidates ordered by ranking score

**Step 2: Run test to verify it fails**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_snapshot_candidate_repository.py -q`

Expected: fail because the table / repository methods do not exist.

**Step 3: Write minimal implementation**

- Add a new SQLite table for snapshot candidates.
- Add repository helpers to:
  - replace candidate set
  - list candidates for an event
  - fetch selected candidate
  - clear candidates

**Step 4: Run test to verify it passes**

Run the same pytest command and confirm green.

**Step 5: Commit**

```bash
git add backend/app/database.py backend/app/repositories/detection_repository.py backend/tests/test_snapshot_candidate_repository.py
git commit -m "Add HQ snapshot candidate persistence"
```

### Task 2: Add candidate generation and ranking in HQ snapshot service

**Files:**
- Modify: `backend/app/services/high_quality_snapshot_service.py`
- Modify: `backend/app/services/classifier_service.py`
- Create: `backend/tests/test_high_quality_snapshot_candidates.py`

**Step 1: Write the failing test**

Add service tests for:
- generating bounded candidates from sampled frames
- ranking crop candidates above empty full-frame candidates
- persisting top-N candidates and selecting one
- keeping full frame when no candidate clears quality

**Step 2: Run test to verify it fails**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_high_quality_snapshot_candidates.py -q`

Expected: fail because candidate generation and persistence hooks do not exist.

**Step 3: Write minimal implementation**

- Add candidate evaluation helpers in `HighQualitySnapshotService`.
- Use existing bounded frame sampling.
- Score candidate variants:
  - full frame
  - Frigate hint crop
  - model crop
- Persist top candidates through the repository.
- Replace snapshot from the selected candidate and record provenance.

**Step 4: Run test to verify it passes**

Run the same pytest command and confirm green.

**Step 5: Commit**

```bash
git add backend/app/services/high_quality_snapshot_service.py backend/app/services/classifier_service.py backend/tests/test_high_quality_snapshot_candidates.py
git commit -m "Add HQ snapshot candidate generation and ranking"
```

### Task 3: Add snapshot-management API surface

**Files:**
- Modify: `backend/app/routers/proxy.py`
- Modify: `backend/app/config_models.py`
- Create: `backend/tests/test_snapshot_candidate_api.py`

**Step 1: Write the failing test**

Add API tests for:
- getting snapshot candidate status / provenance
- listing candidate thumbnails / metadata
- applying source actions:
  - auto best
  - full frame
  - Frigate hint crop
  - model crop
- applying a specific candidate
- reverting to the original Frigate snapshot

**Step 2: Run test to verify it fails**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_snapshot_candidate_api.py -q`

Expected: fail because routes and response models do not exist.

**Step 3: Write minimal implementation**

- Add owner-only endpoints in `proxy.py`.
- Reuse existing snapshot status endpoint patterns.
- Return compact metadata plus thumbnail URLs / refs.

**Step 4: Run test to verify it passes**

Run the same pytest command and confirm green.

**Step 5: Commit**

```bash
git add backend/app/routers/proxy.py backend/app/config_models.py backend/tests/test_snapshot_candidate_api.py
git commit -m "Add HQ snapshot candidate APIs"
```

### Task 4: Add detection modal snapshot repair UI

**Files:**
- Modify: `apps/ui/src/lib/api/media.ts`
- Modify: `apps/ui/src/lib/components/DetectionModal.svelte`
- Create: `apps/ui/src/lib/components/detection-modal-snapshot-repair.test.ts`

**Step 1: Write the failing test**

Add UI tests for:
- rendering current snapshot provenance
- opening the change-snapshot flow
- showing quick source actions
- showing candidate thumbnails
- applying a candidate and refreshing the snapshot URL

**Step 2: Run test to verify it fails**

Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- detection-modal-snapshot-repair.test.ts`

Expected: fail because the API types and modal UI do not exist.

**Step 3: Write minimal implementation**

- Add media API helpers for candidate listing and apply/revert actions.
- Add a modal section for snapshot repair.
- Keep the existing manual HQ bird crop action only if it still maps cleanly onto `model crop`; otherwise replace it with the new unified controls.

**Step 4: Run test to verify it passes**

Run the same UI test command and confirm green.

**Step 5: Commit**

```bash
git add apps/ui/src/lib/api/media.ts apps/ui/src/lib/components/DetectionModal.svelte apps/ui/src/lib/components/detection-modal-snapshot-repair.test.ts
git commit -m "Add detection snapshot repair workflow"
```

### Task 5: Final integration verification and docs

**Files:**
- Modify: `CHANGELOG.md`
- Optionally modify: `docs/features/model-accuracy.md`

**Step 1: Run focused backend tests**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest \
  backend/tests/test_snapshot_candidate_repository.py \
  backend/tests/test_high_quality_snapshot_candidates.py \
  backend/tests/test_snapshot_candidate_api.py \
  backend/tests/test_high_quality_snapshot_service.py -q
```

Expected: all pass.

**Step 2: Run focused UI tests**

Run:

```bash
npm --prefix /config/workspace/YA-WAMF/apps/ui test -- detection-modal-snapshot-repair.test.ts
npm --prefix /config/workspace/YA-WAMF/apps/ui run check
```

Expected: pass with no type/lint errors.

**Step 3: Update changelog**

Document:
- automatic HQ snapshot candidate selection
- persisted candidate metadata
- owner snapshot repair workflow

**Step 4: Commit**

```bash
git add CHANGELOG.md docs/features/model-accuracy.md
git commit -m "Document HQ snapshot repair workflow"
```
