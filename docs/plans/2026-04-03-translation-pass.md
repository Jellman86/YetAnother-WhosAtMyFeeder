# Full Translation Pass Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve YA-WAMF’s supported UI locales by closing locale-file gaps, reducing visible English fallback leakage on key screens, and normalizing terminology across all shipped languages.

**Architecture:** Treat the translation pass as two layers: locale-file coverage and code-surface cleanup. First make locale files complete relative to `en.json`, then replace high-visibility inline fallback/default usage on key screens with locale-backed strings, and finally run a consistency pass across the touched keys.

**Tech Stack:** Svelte 5, `svelte-i18n`, JSON locale files, Vitest locale audits, `svelte-check`

---

### Task 1: Lock in locale completeness

**Files:**
- Modify: `apps/ui/src/lib/i18n/locales/*.json`
- Modify: `apps/ui/src/lib/i18n/locales.audit.test.ts`

**Step 1: Add the missing locale keys**

Add:
- `about.feature_list.full_visit_clip.title`
- `about.feature_list.full_visit_clip.desc`

to all non-English locale files.

**Step 2: Expand locale completeness coverage**

Strengthen audit coverage so these keys, plus other touched keys from this pass, are asserted in all non-English locales.

**Step 3: Run locale audit tests**

Run: `npm --prefix apps/ui test -- src/lib/i18n/locales.audit.test.ts src/lib/i18n/locales.settings-data.test.ts src/lib/i18n/locales.jobs-errors.test.ts src/lib/i18n/locales.model-picker.test.ts`
Expected: PASS

### Task 2: Clean high-visibility active UI surfaces

**Files:**
- Modify: `apps/ui/src/lib/components/DetectionModal.svelte`
- Modify: `apps/ui/src/lib/components/VideoPlayer.svelte`
- Modify: `apps/ui/src/lib/components/ReclassificationOverlay.svelte`
- Modify: `apps/ui/src/lib/components/GlobalProgress.svelte`
- Modify: `apps/ui/src/lib/pages/Events.svelte`
- Modify: `apps/ui/src/lib/pages/Species.svelte`
- Modify: `apps/ui/src/lib/pages/Jobs.svelte`
- Modify: `apps/ui/src/lib/pages/Errors.svelte`
- Modify: `apps/ui/src/lib/pages/models/ModelManager.svelte`
- Modify: locale JSON files as needed

**Step 1: Replace visible inline English defaults on touched surfaces**

For each touched file:
- reuse existing translation keys where they already exist
- only add new keys when no stable key exists
- avoid introducing redundant aliases

**Step 2: Keep fallback usage only where truly defensive**

If a fallback remains, it should be because the string is diagnostic or transitional, not because a visible user-facing string never made it into locale JSON.

**Step 3: Run focused UI/source tests**

Run the relevant touched tests plus any source-layout tests affected by key changes.

### Task 3: Normalize terminology across locales

**Files:**
- Modify: `apps/ui/src/lib/i18n/locales/en.json`
- Modify: `apps/ui/src/lib/i18n/locales/de.json`
- Modify: `apps/ui/src/lib/i18n/locales/es.json`
- Modify: `apps/ui/src/lib/i18n/locales/fr.json`
- Modify: `apps/ui/src/lib/i18n/locales/it.json`
- Modify: `apps/ui/src/lib/i18n/locales/ja.json`
- Modify: `apps/ui/src/lib/i18n/locales/pt.json`
- Modify: `apps/ui/src/lib/i18n/locales/ru.json`
- Modify: `apps/ui/src/lib/i18n/locales/zh.json`

**Step 1: Review touched terminology as a set**

Normalize the product-language rendering for:
- full visit
- leaderboard/species leaderboard
- batch analysis
- circuit breaker
- queue/pending/active/stale
- reclassification/auto video

**Step 2: Prefer product clarity over literal wording**

For each locale, keep wording natural and consistent even if phrasing differs slightly from English.

### Task 4: Verify and document

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Update changelog**

Document that the UI translation coverage and terminology were improved across all shipped locales.

**Step 2: Run verification**

Run:
- `npm --prefix apps/ui test -- src/lib/i18n/locales.audit.test.ts src/lib/i18n/locales.settings-data.test.ts src/lib/i18n/locales.jobs-errors.test.ts src/lib/i18n/locales.model-picker.test.ts`
- `npm --prefix apps/ui run check`

Add any focused component tests required by touched source.

**Step 3: Summarize residual gaps honestly**

If any code-level fallback-heavy areas remain untouched, call them out explicitly instead of implying a total repo-wide purge.
