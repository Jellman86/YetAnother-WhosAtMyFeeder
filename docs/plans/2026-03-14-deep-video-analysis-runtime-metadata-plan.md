# Deep Video Analysis Runtime Metadata Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Persist video-classification model metadata and surface friendly provider/model chips in the completed Deep Video Analysis card in the detection modal.

**Architecture:** Add one nullable `detections.video_classification_model_id` column through an idempotent Alembic migration, thread that field through repository and event payloads, and derive a friendly model name from the backend model registry. Keep the UI dumb by consuming stored detection metadata only, and limit the visual change to the completed-result card in `DetectionModal`.

**Tech Stack:** Python, FastAPI, Alembic, SQLite, pytest, Svelte 5, TypeScript

---

### Task 1: Add the Failing Schema Test

**Files:**
- Modify: `backend/tests/test_sqlite_schema_sanity.py`
- Reference: `backend/app/db_schema.py`

**Step 1: Write the failing test**

Extend `test_sqlite_schema_sanity.py` with a new assertion that upgraded databases contain `video_classification_model_id` on `detections`.

```python
def test_detections_schema_includes_video_classification_model_id(tmp_path):
    db_path = tmp_path / "schema_video_runtime.db"
    _upgrade_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        cols = conn.execute("PRAGMA table_info(detections);").fetchall()
        col_names = [c[1] for c in cols]
        assert "video_classification_model_id" in col_names
    finally:
        conn.close()
```

**Step 2: Run test to verify it fails**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_sqlite_schema_sanity.py -q`

Expected: FAIL because `video_classification_model_id` is not yet present in migrated schema.

**Step 3: Write minimal implementation**

Do not implement yet. This task stays red until the migration and schema mirror are added.

**Step 4: Run test to verify it passes**

Run the same command after Task 2.

Expected: PASS.

**Step 5: Commit**

```bash
git add backend/tests/test_sqlite_schema_sanity.py backend/migrations/versions/*.py backend/app/db_schema.py
git commit -m "feat: add video classification model schema"
```

### Task 2: Add the Schema Column Safely

**Files:**
- Create: `backend/migrations/versions/<new_revision>_add_video_classification_model_id.py`
- Modify: `backend/app/db_schema.py`
- Reference: `backend/migrations/versions/c4d2a1f7e9b3_add_video_classification_runtime_columns.py`

**Step 1: Write the failing schema implementation target**

Create a migration using the repo’s existing idempotent pattern:

```python
def _get_columns(conn, table: str) -> set[str]:
    rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    return {row[1] for row in rows}


def upgrade() -> None:
    conn = op.get_bind()
    cols = _get_columns(conn, "detections")
    if "video_classification_model_id" not in cols:
        op.add_column(
            "detections",
            sa.Column("video_classification_model_id", sa.String(), nullable=True),
        )
```

Mirror the column in `backend/app/db_schema.py` next to the existing video-classification runtime columns.

**Step 2: Run test to verify it fails correctly before completing all changes**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_sqlite_schema_sanity.py::test_detections_schema_includes_video_classification_model_id -q`

Expected: FAIL before the migration file and schema mirror are both in place.

**Step 3: Write minimal implementation**

Implement:
- Alembic migration with existence guards in both `upgrade()` and `downgrade()`
- `db_schema.py` mirror column

Keep the migration narrow:
- one nullable column only
- no data rewrite
- no index

**Step 4: Run test to verify it passes**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_sqlite_schema_sanity.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add backend/migrations/versions/*.py backend/app/db_schema.py backend/tests/test_sqlite_schema_sanity.py
git commit -m "feat: add video classification model id column"
```

### Task 3: Persist Model Id in Repository Results

**Files:**
- Modify: `backend/app/repositories/detection_repository.py`
- Modify: `backend/tests/test_detection_repository.py`

**Step 1: Write the failing test**

Extend the in-memory detections schema in `test_detection_repository.py` with `video_classification_model_id TEXT`, then strengthen the existing runtime metadata test:

```python
async def test_update_video_classification_persists_runtime_provider_backend_and_model():
    ...
    await repo.update_video_classification(
        frigate_event="evt_video_runtime",
        label="Blue Jay",
        score=0.88,
        index=123,
        status="completed",
        provider="intel_gpu",
        backend="openvino",
        model_id="convnext_large_inat21",
    )

    updated = await repo.get_by_frigate_event("evt_video_runtime")
    assert updated.video_classification_provider == "intel_gpu"
    assert updated.video_classification_backend == "openvino"
    assert updated.video_classification_model_id == "convnext_large_inat21"
```

**Step 2: Run test to verify it fails**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_detection_repository.py::test_update_video_classification_persists_runtime_provider_backend_and_model -q`

Expected: FAIL because the `Detection` model, row mapping, or update method does not yet include `video_classification_model_id`.

**Step 3: Write minimal implementation**

Update `detection_repository.py` to:
- add `video_classification_model_id: Optional[str] = None` to `Detection`
- include the column in relevant `SELECT` lists
- map it in `_row_to_detection`
- accept `model_id` in `update_video_classification()`
- write `video_classification_model_id = ?` in the update statement

Keep the change limited to paths already returning video-classification runtime fields.

**Step 4: Run test to verify it passes**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_detection_repository.py::test_update_video_classification_persists_runtime_provider_backend_and_model -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/repositories/detection_repository.py backend/tests/test_detection_repository.py
git commit -m "feat: persist video classification model metadata"
```

### Task 4: Thread Model Id Through Video Classification Writes

**Files:**
- Modify: `backend/app/services/detection_service.py`
- Modify: `backend/app/routers/events.py`
- Reference: `backend/app/services/auto_video_classifier_service.py`
- Reference: `backend/app/services/model_manager.py`

**Step 1: Write the failing API test**

Extend `backend/tests/test_event_classification_status_api.py` so the inserted row includes:
- `video_classification_provider`
- `video_classification_backend`
- `video_classification_model_id`

Then assert the response exposes both raw and friendly model fields:

```python
assert payload["video_classification_provider"] == "intel_gpu"
assert payload["video_classification_backend"] == "openvino"
assert payload["video_classification_model_id"] == "convnext_large_inat21"
assert payload["video_classification_model_name"] == "ConvNeXt Large (High Accuracy)"
```

**Step 2: Run test to verify it fails**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_event_classification_status_api.py -q`

Expected: FAIL because the response model and route do not yet include model fields or friendly-name derivation.

**Step 3: Write minimal implementation**

Implement the smallest backend plumbing needed:

1. In the video-classification write path, pass the resolved effective model id into `repo.update_video_classification(...)`.
2. In `backend/app/routers/events.py`, add a helper that maps stored model ids to friendly names via `REMOTE_REGISTRY`.
3. Extend `_detection_updated_payload()` with:

```python
"video_classification_model_id": detection.video_classification_model_id,
"video_classification_model_name": _video_classification_model_name(detection.video_classification_model_id),
```

4. Extend `ClassificationStatusResponse` with:

```python
video_classification_model_id: str | None = None
video_classification_model_name: str | None = None
```

5. Populate those fields in the `/classification-status` route.

Prefer one backend helper for friendly-name derivation rather than duplicating lookups.

**Step 4: Run test to verify it passes**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_event_classification_status_api.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/services/detection_service.py backend/app/routers/events.py backend/tests/test_event_classification_status_api.py
git commit -m "feat: expose video classification model metadata"
```

### Task 5: Extend Shared API Types

**Files:**
- Modify: `apps/ui/src/lib/api/types.ts`
- Modify: `apps/ui/src/lib/api/events.ts`

**Step 1: Write the failing type target**

Add the new fields to the shared TS interfaces:

```ts
video_classification_model_id?: string | null;
video_classification_model_name?: string | null;
```

in both:
- `Detection`
- `EventClassificationStatusResponse`

**Step 2: Run typecheck to verify failure if UI uses fields before types are added**

Run: `npm --prefix /config/workspace/YA-WAMF/.worktrees/issue22-subprocess-admission/apps/ui run check`

Expected: FAIL once Task 6 starts referencing the new fields before these types are updated.

**Step 3: Write minimal implementation**

Update the TS interfaces only. Do not add frontend-side model-name mapping logic.

**Step 4: Run typecheck to verify it passes**

Run the same command after Task 6.

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/ui/src/lib/api/types.ts apps/ui/src/lib/api/events.ts
git commit -m "feat: add video classification model fields to ui types"
```

### Task 6: Render Provider and Model Chips in the Detection Modal

**Files:**
- Modify: `apps/ui/src/lib/components/DetectionModal.svelte`
- Reference: `apps/ui/src/lib/i18n/locales/en.json`

**Step 1: Write the failing UI assertion target**

If there is existing UI/component test coverage for `DetectionModal`, extend it. If not, use build/typecheck as the executable safety net and keep the markup change narrow.

Target markup shape:

```svelte
{#if detection.video_classification_provider}
  <div class="...">
    <!-- CPU/GPU icon + label -->
  </div>
{/if}
{#if detection.video_classification_model_name}
  <div class="...">
    <span class="...">{detection.video_classification_model_name}</span>
  </div>
{/if}
```

**Step 2: Run UI check to verify failure if fields are referenced before types are ready**

Run: `npm --prefix /config/workspace/YA-WAMF/.worktrees/issue22-subprocess-admission/apps/ui run check`

Expected: FAIL until Tasks 5 and 6 are complete together.

**Step 3: Write minimal implementation**

Update only the completed-result card in `DetectionModal.svelte`:
- keep the existing provider chip semantics
- extract the provider chip markup into a slightly cleaner reusable block inside the component if helpful
- add a second neutral model chip using `detection.video_classification_model_name`
- preserve layout when neither field exists

Do not:
- change the in-progress media-slot header
- add new i18n copy unless the chip text needs a new label
- fall back to current classifier status for completed rows

**Step 4: Run UI checks to verify it passes**

Run:
- `npm --prefix /config/workspace/YA-WAMF/.worktrees/issue22-subprocess-admission/apps/ui run check`
- `npm --prefix /config/workspace/YA-WAMF/.worktrees/issue22-subprocess-admission/apps/ui run build`

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/ui/src/lib/components/DetectionModal.svelte apps/ui/src/lib/api/types.ts apps/ui/src/lib/api/events.ts
git commit -m "feat: show provider and model on video analysis card"
```

### Task 7: Run End-to-End Verification

**Files:**
- Modify: `CHANGELOG.md`
- Verify: `backend/tests/test_sqlite_schema_sanity.py`
- Verify: `backend/tests/test_detection_repository.py`
- Verify: `backend/tests/test_event_classification_status_api.py`
- Verify: `apps/ui/src/lib/components/DetectionModal.svelte`

**Step 1: Update changelog**

Add one unreleased note describing:
- persisted video-classification model metadata
- Deep Video Analysis card now showing provider/model runtime context

**Step 2: Run backend targeted verification**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest \
  backend/tests/test_sqlite_schema_sanity.py \
  backend/tests/test_detection_repository.py \
  backend/tests/test_event_classification_status_api.py -q
```

Expected: PASS.

**Step 3: Run UI verification**

Run:

```bash
npm --prefix /config/workspace/YA-WAMF/.worktrees/issue22-subprocess-admission/apps/ui run check
npm --prefix /config/workspace/YA-WAMF/.worktrees/issue22-subprocess-admission/apps/ui run build
```

Expected: PASS.

**Step 4: Run migration path and whitespace verification**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python backend/scripts/ci_migration_path_check.py
git diff --check
```

Expected: PASS.

**Step 5: Final commit**

```bash
git add CHANGELOG.md backend apps/ui
git commit -m "feat: surface video analysis runtime metadata"
```
