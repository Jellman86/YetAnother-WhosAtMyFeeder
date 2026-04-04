# Desktop Nav Simplification Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove the desktop horizontal navigation/layout mode while preserving the existing mobile menu and mobile navigation behavior.

**Architecture:** Collapse the app shell to a single desktop layout model built around the existing sidebar. Remove only the desktop header route nav, migrate persisted horizontal layout preferences to vertical, and delete the settings/UI affordances that expose horizontal mode. Keep mobile header/menu behavior unchanged.

**Tech Stack:** Svelte 5, TypeScript, Tailwind CSS, Vitest, svelte-check

---

### Task 1: Add layout-store migration coverage

**Files:**
- Modify: `apps/ui/src/lib/stores/layout.svelte.ts`
- Test: `apps/ui/src/lib/stores/layout.test.ts` or create if missing

**Step 1: Write the failing test**

Add a test that seeds `localStorage.layout = "horizontal"` and asserts the store resolves to `vertical`.

**Step 2: Run test to verify it fails**

Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/stores/layout.test.ts`

**Step 3: Write minimal implementation**

Update the layout store so horizontal is migrated/normalized to vertical and the store only exposes vertical behavior.

**Step 4: Run test to verify it passes**

Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/stores/layout.test.ts`

**Step 5: Commit**

```bash
git add apps/ui/src/lib/stores/layout.svelte.ts apps/ui/src/lib/stores/layout.test.ts
git commit -m "refactor(ui): collapse layout state to vertical only"
```

### Task 2: Remove the desktop header nav

**Files:**
- Modify: `apps/ui/src/lib/components/Header.svelte`
- Test: `apps/ui/src/lib/components/header.layout.test.ts` or existing layout test file if present

**Step 1: Write the failing test**

Add/update a test asserting desktop route-tab nav is absent while the mobile menu block is still present.

**Step 2: Run test to verify it fails**

Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/components/header.layout.test.ts`

**Step 3: Write minimal implementation**

Remove the desktop `<nav>` route tabs from the header and keep the mobile menu unchanged.

**Step 4: Run test to verify it passes**

Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/components/header.layout.test.ts`

**Step 5: Commit**

```bash
git add apps/ui/src/lib/components/Header.svelte apps/ui/src/lib/components/header.layout.test.ts
git commit -m "refactor(ui): remove desktop header nav"
```

### Task 3: Simplify the app shell to the single desktop layout

**Files:**
- Modify: `apps/ui/src/App.svelte`
- Test: `apps/ui/src/App.layout.test.ts` or an existing shell/layout test file

**Step 1: Write the failing test**

Add/update a test asserting the desktop shell always renders the sidebar path and no longer branches on horizontal layout.

**Step 2: Run test to verify it fails**

Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/App.layout.test.ts`

**Step 3: Write minimal implementation**

Remove horizontal-layout conditionals from the shell, simplify padding/chrome calculations, and preserve mobile behavior.

**Step 4: Run test to verify it passes**

Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/App.layout.test.ts`

**Step 5: Commit**

```bash
git add apps/ui/src/App.svelte src/App.layout.test.ts
git commit -m "refactor(ui): simplify app shell to sidebar layout"
```

### Task 4: Remove layout-choice UI from settings

**Files:**
- Modify: `apps/ui/src/lib/components/settings/AppearanceSettings.svelte`
- Modify: `apps/ui/src/lib/pages/Settings.svelte`
- Test: existing appearance/settings layout tests

**Step 1: Write the failing test**

Add/update a test asserting the appearance/settings UI no longer offers horizontal vs vertical layout selection.

**Step 2: Run test to verify it fails**

Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/pages/Settings.layout.test.ts`

**Step 3: Write minimal implementation**

Remove the layout picker state and any references to horizontal/vertical selection from settings.

**Step 4: Run test to verify it passes**

Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/pages/Settings.layout.test.ts`

**Step 5: Commit**

```bash
git add apps/ui/src/lib/components/settings/AppearanceSettings.svelte apps/ui/src/lib/pages/Settings.svelte src/lib/pages/Settings.layout.test.ts
git commit -m "refactor(ui): remove layout selection settings"
```

### Task 5: Clean up copy, locales, and verification

**Files:**
- Modify: `apps/ui/src/lib/i18n/locales/*.json` as needed
- Modify: `CHANGELOG.md`
- Test: relevant locale/layout tests

**Step 1: Write/update the failing checks**

Adjust any locale/layout tests that still expect horizontal layout strings or layout-choice UI.

**Step 2: Run tests to verify failures or stale assumptions**

Run targeted layout/i18n tests.

**Step 3: Write minimal implementation**

Remove or repurpose obsolete layout copy and update the changelog.

**Step 4: Run full verification**

Run:
- `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- <targeted files>`
- `npm --prefix /config/workspace/YA-WAMF/apps/ui run check`

**Step 5: Commit**

```bash
git add CHANGELOG.md apps/ui/src/lib/i18n/locales
git commit -m "refactor(ui): remove horizontal layout product surface"
```
