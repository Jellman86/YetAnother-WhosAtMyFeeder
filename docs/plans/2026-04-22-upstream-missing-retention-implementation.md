# Upstream Missing Retention Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make YA-WAMF treat missing upstream Frigate events/media as a configurable policy-driven state transition instead of an implicit delete, with persisted detection state, UI controls, and diagnostics evidence.

**Architecture:** Add persisted upstream status fields to detections, migrate config to an explicit maintenance policy, route cleanup paths through one policy evaluator, and expose the new fields through the API and settings UI. Use Alembic for schema evolution and targeted pytest coverage for config migration, repository behavior, cleanup outcomes, and diagnostics.

**Tech Stack:** Python, FastAPI, Pydantic, SQLite, Alembic, Svelte, TypeScript, pytest

---

### Task 1: Add failing tests for config and schema

**Files:**
- Modify: `backend/tests/test_config_env_mapping.py`
- Modify: `backend/tests/test_sqlite_schema_sanity.py`

**Step 1: Write the failing tests**

- Add a config migration test asserting legacy `auto_delete_missing_clips=true`
  maps to the new policy `delete`.
- Add a config default test asserting fresh config defaults the new policy to
  `mark_missing`.
- Add a schema sanity test asserting new detection columns exist after Alembic
  upgrade.

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest backend/tests/test_config_env_mapping.py backend/tests/test_sqlite_schema_sanity.py -q`

**Step 3: Write minimal implementation**

- Add the new maintenance policy model and migration behavior.
- Add the Alembic migration and required column verification list.

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest backend/tests/test_config_env_mapping.py backend/tests/test_sqlite_schema_sanity.py -q`

### Task 2: Add failing repository tests for upstream status persistence

**Files:**
- Modify: `backend/tests/test_detection_repository.py`
- Modify: `backend/app/repositories/detection_repository.py`
- Modify: `backend/app/models/__init__.py`

**Step 1: Write the failing tests**

- Assert repository create/upsert sets `frigate_status='present'`.
- Assert repository can mark a detection missing with reason and timestamps.
- Assert repository can restore a detection to present and clear missing fields.

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest backend/tests/test_detection_repository.py -q`

**Step 3: Write minimal implementation**

- Extend repository dataclass/model mapping and SQL projections.
- Add repository helpers for marking and clearing upstream-missing state.

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest backend/tests/test_detection_repository.py -q`

### Task 3: Add failing settings and maintenance behavior tests

**Files:**
- Modify: `backend/tests/test_settings_api.py`
- Create: `backend/tests/test_upstream_missing_policy.py`
- Modify: `backend/app/routers/settings.py`
- Modify: `backend/app/services/auto_video_classifier_service.py`
- Modify: `backend/app/main.py`

**Step 1: Write the failing tests**

- Assert `/api/settings` round-trips the new policy value.
- Assert maintenance purge marks detections missing under `mark_missing`.
- Assert maintenance purge deletes only under explicit `delete`.
- Assert auto video cleanup marks instead of deletes under the safe default.
- Assert diagnostics history records policy/action context.

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest backend/tests/test_settings_api.py backend/tests/test_upstream_missing_policy.py backend/tests/test_auto_video_classifier_snapshot_upgrade.py -q`

**Step 3: Write minimal implementation**

- Add one maintenance policy evaluator used by scheduled cleanup and video
  cleanup.
- Return detailed counts such as `deleted_count`, `marked_missing_count`, and
  `kept_count`.
- Record diagnostics and structured logs for every policy action.

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest backend/tests/test_settings_api.py backend/tests/test_upstream_missing_policy.py backend/tests/test_auto_video_classifier_snapshot_upgrade.py -q`

### Task 4: Add UI settings support

**Files:**
- Modify: `apps/ui/src/lib/api/settings.ts`
- Modify: `apps/ui/src/lib/pages/Settings.svelte`
- Modify: `apps/ui/src/lib/components/settings/DataSettings.svelte`

**Step 1: Write the failing test or assertion target**

- Add compile-level coverage by updating types and bindings first so the build
  fails until all references are wired.

**Step 2: Run test to verify it fails**

Run: `npm --prefix apps/ui run build`

**Step 3: Write minimal implementation**

- Add the new policy field to the settings API type.
- Add UI state/load/save wiring.
- Replace destructive-only maintenance copy with policy-aware wording.

**Step 4: Run test to verify it passes**

Run: `npm --prefix apps/ui run build`

### Task 5: Verify end-to-end and review second-order effects

**Files:**
- Review: `backend/app/database.py`
- Review: `backend/app/routers/events.py`
- Review: `backend/app/services/error_diagnostics.py`

**Step 1: Run targeted backend verification**

Run: `python3 -m pytest backend/tests/test_config_env_mapping.py backend/tests/test_sqlite_schema_sanity.py backend/tests/test_detection_repository.py backend/tests/test_settings_api.py backend/tests/test_upstream_missing_policy.py backend/tests/test_auto_video_classifier_snapshot_upgrade.py -q`

**Step 2: Run broader regression verification**

Run: `python3 -m pytest backend/tests/test_event_classification_status_api.py backend/tests/test_auto_video_classifier_queueing.py -q`

**Step 3: Run frontend verification**

Run: `npm --prefix apps/ui run build`

**Step 4: Commit**

```bash
git add docs/plans backend apps/ui
git commit -m "fix: make missing frigate data retention policy explicit"
git push origin dev
```
