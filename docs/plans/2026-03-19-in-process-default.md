# In-Process Default Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Change YA-WAMF so fresh installs and unset configs default image inference to `in_process`, with matching UI messaging and tests.

**Architecture:** Update every default/fallback source for `image_execution_mode` together: config model, config loader, settings schema, and UI initial/fallback state. Keep persisted values untouched, and rewrite settings copy to describe the RAM/isolation tradeoff without implying the old default is still preferred.

**Tech Stack:** Python, Pydantic, Svelte, JSON locale files, pytest, Vitest, svelte-check

---

### Task 1: Update backend default-value tests

**Files:**
- Modify: `backend/tests/test_config_env_mapping.py`

**Step 1: Write the failing test**

Change the existing default assertion from `subprocess` to `in_process` and update any parametrized fallback expectations that should now resolve to `in_process`.

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=/config/workspace/YA-WAMF/backend python3 -m pytest --noconftest /config/workspace/YA-WAMF/backend/tests/test_config_env_mapping.py -q`
Expected: FAIL because backend defaults still resolve to `subprocess`

**Step 3: Write minimal implementation**

Update backend config defaults and validator fallbacks.

**Step 4: Run test to verify it passes**

Run the same pytest command.
Expected: PASS

### Task 2: Update UI default and copy

**Files:**
- Modify: `apps/ui/src/lib/pages/Settings.svelte`
- Modify: `apps/ui/src/lib/components/settings/DetectionSettings.svelte`
- Modify: `apps/ui/src/lib/i18n/locales/en.json`
- Modify: `apps/ui/src/lib/i18n/locales/de.json`
- Modify: `apps/ui/src/lib/i18n/locales/es.json`
- Modify: `apps/ui/src/lib/i18n/locales/fr.json`
- Modify: `apps/ui/src/lib/i18n/locales/it.json`
- Modify: `apps/ui/src/lib/i18n/locales/ja.json`
- Modify: `apps/ui/src/lib/i18n/locales/pt.json`
- Modify: `apps/ui/src/lib/i18n/locales/ru.json`
- Modify: `apps/ui/src/lib/i18n/locales/zh.json`

**Step 1: Write the failing expectation**

Add or update a small UI-facing assertion if needed, otherwise rely on `svelte-check` and targeted tests after the backend red-green cycle.

**Step 2: Write minimal implementation**

Switch UI fallback/default values to `in_process` and update the explanatory copy to describe RAM savings vs subprocess isolation without calling subprocess the recommended mode.

**Step 3: Run checks**

Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui run check`
Expected: PASS

### Task 3: Update settings API schema fallback

**Files:**
- Modify: `backend/app/routers/settings.py`

**Step 1: Write minimal implementation**

Update the request/update schema default for `image_execution_mode` to `in_process` so unset payload handling matches the config default.

**Step 2: Run verification**

Re-run the targeted backend config test and frontend check.

### Task 4: Document the change

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Add changelog entry**

Record that `in_process` is now the default image execution mode for unset configs/new installs because it materially reduces RAM usage with large models, while `subprocess` remains available for stronger isolation.

**Step 2: Review for consistency**

Ensure the wording matches actual behavior and does not imply existing saved settings are migrated automatically.
