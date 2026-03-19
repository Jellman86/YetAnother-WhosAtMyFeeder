# Birds-Only Regional Model Resolver Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add regional birds-only model families for the small and medium tiers with `Auto | Europe | North America` selection, auto-resolution from configured location, manual override, and release-backed artifact metadata.

**Architecture:** Keep large and elite unchanged. Introduce backend model-family metadata for `small_birds` and `medium_birds`, each with regional variants such as `eu` and `na`. Add a resolver that chooses the effective variant from manual override first, then configured location, then fallback default. Expose that selection in settings without turning every regional variant into a separate top-level model card.

**Tech Stack:** Python, Pydantic, Svelte, Vitest, pytest, ONNX, OpenVINO, GitHub Releases, existing settings/config APIs

---

### Task 1: Add failing tests for the new settings and resolver metadata

**Files:**
- Modify: `backend/tests/test_model_registry_metadata.py`
- Create: `backend/tests/test_bird_model_region_resolver.py`
- Modify: `apps/ui/src/lib/api/classifier.test.ts`

**Step 1: Write the failing test**

Add backend expectations for model-family metadata:

```python
assert by_id["small_birds"].region_variants
assert by_id["medium_birds"].region_variants
assert {"eu", "na"} <= set(by_id["small_birds"].region_variants.keys())
```

Add resolver tests:

```python
def test_resolve_bird_model_region_prefers_manual_override():
    assert resolve_bird_model_region(country="GB", override="na") == "na"

def test_resolve_bird_model_region_uses_country_when_auto():
    assert resolve_bird_model_region(country="GB", override="auto") == "eu"
    assert resolve_bird_model_region(country="US", override="auto") == "na"
```

Add frontend fixture expectations that the settings payload now includes `bird_model_region_override`.

**Step 2: Run tests to verify they fail**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_model_registry_metadata.py /config/workspace/YA-WAMF/backend/tests/test_bird_model_region_resolver.py -q`
Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- classifier.test.ts`
Expected: FAIL because the family metadata and resolver do not exist yet.

**Step 3: Write minimal implementation**

No production code in this task. Only failing tests.

**Step 4: Re-run tests to confirm stable failures**

Run the same commands again.
Expected: targeted failures only.

**Step 5: Commit**

```bash
git add backend/tests/test_model_registry_metadata.py backend/tests/test_bird_model_region_resolver.py apps/ui/src/lib/api/classifier.test.ts
git commit -m "test: lock regional birds resolver contract"
```

### Task 2: Add backend settings support for bird region override

**Files:**
- Modify: `backend/app/config_models.py`
- Modify: `backend/app/config.py`
- Modify: `backend/tests/test_settings_api.py`

**Step 1: Write the failing test**

Add a settings API test that expects:

```python
assert payload["classification"]["bird_model_region_override"] == "auto"
```

and that non-supported values are normalized or rejected.

**Step 2: Run test to verify it fails**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_settings_api.py -q`
Expected: FAIL because the setting does not exist.

**Step 3: Write minimal implementation**

Add:

- `bird_model_region_override: str = "auto"`
- normalization to allowed values: `auto`, `eu`, `na`

Keep the default as `auto`.

**Step 4: Run test to verify it passes**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_settings_api.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/config_models.py backend/app/config.py backend/tests/test_settings_api.py
git commit -m "feat: add bird model region override setting"
```

### Task 3: Implement the backend region resolver

**Files:**
- Create: `backend/app/services/bird_model_region_resolver.py`
- Modify: `backend/tests/test_bird_model_region_resolver.py`

**Step 1: Write the failing test**

Cover:

- override wins
- `GB`, `FR`, `DE`, etc. resolve to `eu`
- `US`, `CA` resolve to `na`
- unknown or missing location falls back to default

**Step 2: Run test to verify it fails**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_bird_model_region_resolver.py -q`
Expected: FAIL because the module does not exist.

**Step 3: Write minimal implementation**

Implement a small deterministic resolver:

```python
def resolve_bird_model_region(*, country: str | None, override: str | None) -> str:
    ...
```

Start with explicit country sets only. Do not overbuild coordinate heuristics in the first pass.

**Step 4: Run test to verify it passes**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_bird_model_region_resolver.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/services/bird_model_region_resolver.py backend/tests/test_bird_model_region_resolver.py
git commit -m "feat: add bird model region resolver"
```

### Task 4: Add model-family metadata for small and medium birds

**Files:**
- Modify: `backend/app/models/ai_models.py`
- Modify: `backend/app/services/model_manager.py`
- Modify: `backend/tests/test_model_registry_metadata.py`

**Step 1: Write the failing test**

Add expectations for two family entries:

```python
assert by_id["small_birds"].tier == "small"
assert by_id["small_birds"].taxonomy_scope == "birds_only"
assert by_id["small_birds"].region_variants["eu"]["region_scope"] == "eu"
assert by_id["medium_birds"].region_variants["na"]["region_scope"] == "na"
```

**Step 2: Run test to verify it fails**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_model_registry_metadata.py -q`
Expected: FAIL because family metadata does not exist.

**Step 3: Write minimal implementation**

Add optional family metadata fields to `ModelMetadata`, such as:

- `family_id`
- `region_variants`
- `default_region`

Create family entries:

- `small_birds`
- `medium_birds`

Do not remove existing large/elite entries.

**Step 4: Run test to verify it passes**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_model_registry_metadata.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/models/ai_models.py backend/app/services/model_manager.py backend/tests/test_model_registry_metadata.py
git commit -m "feat: add regional birds family metadata"
```

### Task 5: Add API support for effective family resolution

**Files:**
- Modify: `backend/app/services/model_manager.py`
- Modify: `backend/app/routers/models.py`
- Create: `backend/tests/test_model_family_resolution_api.py`

**Step 1: Write the failing test**

Add an API test that verifies the backend returns the effective region and selected variant for `small_birds` and `medium_birds`.

```python
assert payload["small_birds"]["effective_region"] == "eu"
assert payload["small_birds"]["selection_source"] == "auto"
```

**Step 2: Run test to verify it fails**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_model_family_resolution_api.py -q`
Expected: FAIL because the API does not expose this yet.

**Step 3: Write minimal implementation**

Expose:

- effective region
- selection source (`auto` or `manual`)
- resolved download metadata for the selected regional variant

Keep the response compact.

**Step 4: Run test to verify it passes**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_model_family_resolution_api.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/services/model_manager.py backend/app/routers/models.py backend/tests/test_model_family_resolution_api.py
git commit -m "feat: expose effective regional bird model resolution"
```

### Task 6: Add settings UI for region override

**Files:**
- Modify: `apps/ui/src/lib/components/settings/DetectionSettings.svelte`
- Modify: `apps/ui/src/lib/i18n/locales/en.json`
- Modify: `apps/ui/src/lib/api/classifier.ts`
- Create: `apps/ui/src/lib/components/settings/detection-region-override.test.ts`

**Step 1: Write the failing test**

Add a UI/settings test that expects:

- `Auto`
- `Europe`
- `North America`

and that selected values round-trip through the settings payload.

**Step 2: Run test to verify it fails**

Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- detection-region-override.test.ts`
Expected: FAIL because the control does not exist.

**Step 3: Write minimal implementation**

Add a simple selector for `bird_model_region_override`.

Display current effective region when `Auto` is selected.

**Step 4: Run test to verify it passes**

Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- detection-region-override.test.ts`
Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui run check`
Expected: PASS

**Step 5: Commit**

```bash
git add apps/ui/src/lib/components/settings/DetectionSettings.svelte apps/ui/src/lib/i18n/locales/en.json apps/ui/src/lib/api/classifier.ts apps/ui/src/lib/components/settings/detection-region-override.test.ts
git commit -m "feat: add bird model region override UI"
```

### Task 7: Record available checkpoints and choose actual regional candidates

**Files:**
- Create: `docs/plans/2026-03-19-birds-only-model-validation-matrix.md`
- Create: `docs/plans/2026-03-19-regional-checkpoint-selection.md`
- Modify: `CHANGELOG.md`

**Step 1: Write the failing documentation checklist**

Create a checkpoint-selection note that records:

- family
- region
- candidate checkpoint
- source availability
- export feasibility
- validation status

**Step 2: Verify the doc is readable**

Run: `sed -n '1,260p' /config/workspace/YA-WAMF/docs/plans/2026-03-19-regional-checkpoint-selection.md`
Expected: clear decision record.

**Step 3: Write minimal implementation**

Populate the initial matrix with actual available regional checkpoints, even if they are not the original ideal architectures.

**Step 4: Verify references**

Run: `rg -n "regional-checkpoint-selection|birds-only-model-validation-matrix" /config/workspace/YA-WAMF/docs/plans /config/workspace/YA-WAMF/CHANGELOG.md`
Expected: all references resolve.

**Step 5: Commit**

```bash
git add docs/plans/2026-03-19-birds-only-model-validation-matrix.md docs/plans/2026-03-19-regional-checkpoint-selection.md CHANGELOG.md
git commit -m "docs: record regional birds checkpoint selection"
```

### Task 8: Add exporter support for actual regional checkpoints

**Files:**
- Modify: `backend/scripts/export_birds_only_model.py`
- Modify: `backend/tests/test_export_birds_only_model.py`

**Step 1: Write the failing test**

Add a test for the chosen checkpoint source format if needed, for example family-specific labels or external-data export behavior.

**Step 2: Run test to verify it fails**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_export_birds_only_model.py -q`
Expected: FAIL if the chosen checkpoint source requires exporter changes.

**Step 3: Write minimal implementation**

Adjust the exporter only enough to support the chosen regional checkpoints.

**Step 4: Run test to verify it passes**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_export_birds_only_model.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/scripts/export_birds_only_model.py backend/tests/test_export_birds_only_model.py
git commit -m "feat: support regional birds checkpoint export"
```

### Task 9: Export, validate, and publish one regional variant at a time

**Files:**
- Modify: `backend/app/services/model_manager.py`
- Create: `docs/plans/2026-03-19-small-eu-validation.md`
- Create: `docs/plans/2026-03-19-small-na-validation.md`
- Create: `docs/plans/2026-03-19-medium-eu-validation.md`
- Create: `docs/plans/2026-03-19-medium-na-validation.md`

**Step 1: Export one selected variant**

Run the exporter for the chosen family/region checkpoint.

**Step 2: Validate on this host**

Required:

- ONNX Runtime CPU
- OpenVINO CPU
- OpenVINO Intel GPU

Record CUDA as `not validated in this environment`.

**Step 3: Upload the artifacts**

Use GitHub Releases to upload:

- `model.onnx`
- `model.onnx.data` if needed
- `labels.txt`

**Step 4: Update family metadata**

Point the matching family variant URLs at the uploaded release assets.

**Step 5: Run tests**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_model_registry_metadata.py /config/workspace/YA-WAMF/backend/tests/test_model_family_resolution_api.py -q`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/app/services/model_manager.py docs/plans/2026-03-19-small-eu-validation.md docs/plans/2026-03-19-small-na-validation.md docs/plans/2026-03-19-medium-eu-validation.md docs/plans/2026-03-19-medium-na-validation.md
git commit -m "feat: publish regional birds family variants"
```

### Task 10: Final verification

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Finalize changelog entries**

Describe:

- regional small/medium birds families
- auto location selection
- manual override
- release-backed regional assets

**Step 2: Run full verification**

Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui run check`
Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_model_registry_metadata.py /config/workspace/YA-WAMF/backend/tests/test_bird_model_region_resolver.py /config/workspace/YA-WAMF/backend/tests/test_model_family_resolution_api.py -q`
Expected: PASS

**Step 3: Verify release metadata**

Run: `gh release view <tag>`
Expected: regional asset files are visible.

**Step 4: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: record regional birds resolver rollout"
```
