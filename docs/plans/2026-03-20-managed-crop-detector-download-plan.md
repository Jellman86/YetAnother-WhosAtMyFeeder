# Managed Crop Detector Download Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the bird crop detector a first-class managed artifact that can be downloaded through YA-WAMF, surfaced in the UI with global progress, and used only when installed and healthy.

**Architecture:** Add a single global crop-detector artifact to the backend model-management layer, expose detector install/health status through the API, and gate crop-enabled classifier behavior on detector readiness rather than local file placement. Extend the model manager UI with a detector status card and disable crop activation affordances until the detector has been downloaded.

**Tech Stack:** FastAPI, Python, Pydantic, Svelte, Vitest, pytest

---

### Task 1: Add failing backend tests for detector registry and status

**Files:**
- Modify: `backend/tests/test_model_registry_metadata.py`
- Modify: `backend/tests/test_model_manager_download.py`
- Modify: `backend/tests/test_classifier_service.py`

**Step 1: Write the failing tests**

Add tests that assert:
- model manager exposes a global crop-detector metadata/status object
- crop detector install status is separate from classifier model lineup
- crop-enabled classifier specs are treated as unavailable for cropping when detector status is missing or unhealthy

**Step 2: Run tests to verify they fail**

Run:
```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest \
  backend/tests/test_model_registry_metadata.py \
  backend/tests/test_model_manager_download.py \
  backend/tests/test_classifier_service.py -q
```

Expected: FAIL because no detector metadata/status contract exists yet.

**Step 3: Write minimal implementation**

Implement the smallest backend contract needed for:
- one global crop-detector artifact definition
- detector install/health lookup
- runtime crop gating against detector readiness

**Step 4: Run tests to verify they pass**

Run the same pytest command and confirm the new tests pass.

**Step 5: Commit**

```bash
git add backend/tests/test_model_registry_metadata.py backend/tests/test_model_manager_download.py backend/tests/test_classifier_service.py backend/app/services/model_manager.py backend/app/services/classifier_service.py backend/app/services/bird_crop_service.py
git commit -m "feat(classifier): add managed crop detector backend contract"
```

### Task 2: Add failing backend tests for detector download/install flow

**Files:**
- Modify: `backend/tests/test_model_manager_download.py`
- Modify: `backend/tests/test_health_readiness.py`

**Step 1: Write the failing tests**

Add tests that assert:
- the crop detector can be downloaded through model-manager-style download plumbing
- detector downloads emit normal progress/status updates
- health or status endpoints expose detector readiness clearly

**Step 2: Run tests to verify they fail**

Run:
```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest \
  backend/tests/test_model_manager_download.py \
  backend/tests/test_health_readiness.py -q
```

Expected: FAIL because detector downloads are not yet managed as first-class artifacts.

**Step 3: Write minimal implementation**

Implement:
- detector artifact metadata and install path
- detector download/validation path using existing progress plumbing
- detector readiness exposure in status/health responses

**Step 4: Run tests to verify they pass**

Run the same pytest command and confirm the new tests pass.

**Step 5: Commit**

```bash
git add backend/tests/test_model_manager_download.py backend/tests/test_health_readiness.py backend/app/services/model_manager.py backend/app/routers/models.py backend/app/routers/health.py
git commit -m "feat(models): manage crop detector downloads"
```

### Task 3: Add failing UI tests for detector status and gated controls

**Files:**
- Modify: `apps/ui/src/lib/api/classifier.test.ts`
- Create or modify: `apps/ui/src/lib/components/settings/detection-crop-overrides.layout.test.ts`
- Create or modify: `apps/ui/src/lib/pages/models/ModelManager.svelte`

**Step 1: Write the failing tests**

Add tests that assert:
- UI metadata supports a detector status block
- detector missing state disables or constrains crop controls
- detector installed state re-enables those controls
- detector download state is represented through existing progress semantics

**Step 2: Run tests to verify they fail**

Run:
```bash
npm test -- --run src/lib/api/classifier.test.ts src/lib/components/settings/detection-crop-overrides.layout.test.ts
```

Expected: FAIL because the UI has no detector block or gating behavior yet.

**Step 3: Write minimal implementation**

Implement the smallest UI/API support for:
- detector status data
- disabled crop controls with explanatory messaging
- detector download action using existing progress flows

**Step 4: Run tests to verify they pass**

Run the same Vitest command and confirm the tests pass.

**Step 5: Commit**

```bash
git add apps/ui/src/lib/api/classifier.test.ts apps/ui/src/lib/components/settings/detection-crop-overrides.layout.test.ts apps/ui/src/lib/pages/models/ModelManager.svelte apps/ui/src/lib/api/classifier.ts
git commit -m "feat(ui): gate crop controls on detector availability"
```

### Task 4: Wire detector runtime selection and remove local-file assumption

**Files:**
- Modify: `backend/app/services/bird_crop_service.py`
- Modify: `backend/app/services/model_manager.py`
- Modify: `backend/app/services/classifier_service.py`
- Test: `backend/tests/test_bird_crop_service.py`
- Test: `backend/tests/test_classifier_service.py`

**Step 1: Write the failing tests**

Add tests that assert:
- bird crop service resolves its model path from the managed detector install, not an ad hoc manual drop path
- env var override remains optional, not required
- missing detector install disables crop application cleanly

**Step 2: Run tests to verify they fail**

Run:
```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest \
  backend/tests/test_bird_crop_service.py \
  backend/tests/test_classifier_service.py -q
```

Expected: FAIL because detector resolution still assumes local path discovery rather than a managed detector install contract.

**Step 3: Write minimal implementation**

Implement:
- detector path resolution through managed install metadata
- graceful fallback when detector is absent/unhealthy
- removal of the assumption that the operator manually places detector files

**Step 4: Run tests to verify they pass**

Run the same pytest command and confirm the tests pass.

**Step 5: Commit**

```bash
git add backend/tests/test_bird_crop_service.py backend/tests/test_classifier_service.py backend/app/services/bird_crop_service.py backend/app/services/model_manager.py backend/app/services/classifier_service.py
git commit -m "fix(classifier): resolve crop detector from managed install"
```

### Task 5: Document and verify end-to-end

**Files:**
- Modify: `CHANGELOG.md`
- Optionally modify: `docs/plans/2026-03-20-local-bird-crop-detector-design.md`
- Optionally modify: `docs/plans/2026-03-20-crop-override-ui-design.md`

**Step 1: Update docs**

Document:
- that the crop detector is now managed/downloadable
- that crop-enabled behavior is blocked until detector install succeeds
- that detector progress appears in the existing global progress system

**Step 2: Run focused verification**

Run:
```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest \
  backend/tests/test_model_registry_metadata.py \
  backend/tests/test_model_manager_download.py \
  backend/tests/test_bird_crop_service.py \
  backend/tests/test_classifier_service.py \
  backend/tests/test_health_readiness.py -q

npm test -- --run src/lib/api/classifier.test.ts src/lib/components/settings/detection-crop-overrides.layout.test.ts
```

Expected: PASS.

**Step 3: Commit**

```bash
git add CHANGELOG.md docs/plans/2026-03-20-local-bird-crop-detector-design.md docs/plans/2026-03-20-crop-override-ui-design.md
git commit -m "docs: record managed crop detector flow"
```
