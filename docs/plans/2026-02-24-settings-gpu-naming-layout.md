# Settings GPU/Naming Layout Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move bird naming preferences into Appearance settings and promote GPU/inference provider controls into a top-level Detection settings section with linked setup/troubleshooting docs.

**Architecture:** Reuse existing naming state bindings and i18n strings, but relocate the naming UI from `DetectionSettings` to `AppearanceSettings` via prop plumbing in the parent settings page. Keep inference provider logic in `DetectionSettings`, extracting it from the Auto Video subsection into its own card so it is visible regardless of auto-video status. Add a docs link using translated keys across locales.

**Tech Stack:** Svelte/SvelteKit UI components, `svelte-i18n` locale JSON files.

---

### Task 1: Move Bird Naming UI to Appearance

**Files:**
- Modify: `apps/ui/src/lib/components/settings/DetectionSettings.svelte`
- Modify: `apps/ui/src/lib/components/settings/AppearanceSettings.svelte`
- Modify: `apps/ui/src/lib/pages/Settings.svelte`

**Steps:**
1. Remove the naming section from `DetectionSettings`.
2. Add equivalent naming controls to `AppearanceSettings` using existing styles and bindings.
3. Pass `displayCommonNames` and `scientificNamePrimary` bindable props from `Settings.svelte` into `AppearanceSettings`.
4. Run `npm --prefix apps/ui run check` to confirm no binding/type regressions.

### Task 2: Promote GPU Provider Controls and Add Docs Link

**Files:**
- Modify: `apps/ui/src/lib/components/settings/DetectionSettings.svelte`
- Modify: `apps/ui/src/lib/i18n/locales/*.json`
- Modify: `CHANGELOG.md`

**Steps:**
1. Extract the inference provider UI/status/diagnostics block from the `autoVideoClassification` conditional and place it in a standalone Detection section/card.
2. Add a docs link (repo docs setup + diagnostics) near the provider selector/status.
3. Add any new i18n keys to all locales with translated values.
4. Update `CHANGELOG.md` (`Unreleased`) to mention the settings reorganization and GPU docs link.

### Task 3: Verify and Ship

**Files:**
- None (verification only)

**Steps:**
1. Run `npm --prefix apps/ui run check`.
2. Run `npm --prefix apps/ui run build`.
3. Review diff for scope/consistency.
4. Commit and push to `dev`.
