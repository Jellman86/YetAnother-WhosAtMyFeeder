# Model Picker Localization and Changelog Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Localize the new tiered model picker and adjacent settings UX, and add a concise changelog entry for the completed model-lineup work.

**Architecture:** Keep the existing settings/model UI intact and move user-visible copy into locale JSON files under existing settings namespaces. Add a small locale coverage test to enforce that the new keys exist in every bundled locale.

**Tech Stack:** Svelte 5, svelte-i18n, Vitest, JSON locale bundles, Markdown changelog

---

### Task 1: Add locale coverage for the new model/settings keys

**Files:**
- Create: `apps/ui/src/lib/i18n/locales.model-picker.test.ts`
- Test: `apps/ui/src/lib/i18n/locales.model-picker.test.ts`

**Step 1: Write the failing test**
Write a locale coverage test that asserts every supported locale has the new model picker and guidance keys.

**Step 2: Run test to verify it fails**
Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/i18n/locales.model-picker.test.ts`
Expected: FAIL because the new keys do not exist in all locale files yet.

**Step 3: Write minimal implementation**
Add the missing locale keys to all supported locale JSON files.

**Step 4: Run test to verify it passes**
Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/i18n/locales.model-picker.test.ts`
Expected: PASS

**Step 5: Commit**
```bash
git add apps/ui/src/lib/i18n/locales.model-picker.test.ts apps/ui/src/lib/i18n/locales/*.json
git commit -m "feat: localize model picker copy"
```

### Task 2: Wire the model/settings UI to translation keys

**Files:**
- Modify: `apps/ui/src/lib/pages/models/ModelManager.svelte`
- Modify: `apps/ui/src/lib/components/settings/DetectionSettings.svelte`
- Modify: `apps/ui/src/lib/components/settings/detection-model-guidance.ts`

**Step 1: Write the failing test**
Rely on Task 1 locale-coverage red state, then wire UI to use the new keys instead of hard-coded strings.

**Step 2: Run targeted verification**
Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui run check`
Expected: FAIL if translation references are malformed.

**Step 3: Write minimal implementation**
Replace hard-coded English in the new model picker / guidance flow with `$_(...)` lookups and reuse the new keys for labels, buttons, helper text, and provider-status text.

**Step 4: Run verification to pass**
Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui run check`
Expected: PASS

**Step 5: Commit**
```bash
git add apps/ui/src/lib/pages/models/ModelManager.svelte apps/ui/src/lib/components/settings/DetectionSettings.svelte apps/ui/src/lib/components/settings/detection-model-guidance.ts
git commit -m "feat: localize model settings copy"
```

### Task 3: Update the changelog

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Write the failing test**
No automated test; use review discipline.

**Step 2: Update the unreleased section**
Add concise `Added` / `Changed` / `Fixed` entries that summarize the tiered-model lineup, new downloadable models, download progress, Birder label normalization, and taxonomy backfill hardening.

**Step 3: Verify**
Review the diff for clarity and duplication.

**Step 4: Commit**
```bash
git add CHANGELOG.md
git commit -m "docs: update changelog for model lineup work"
```
