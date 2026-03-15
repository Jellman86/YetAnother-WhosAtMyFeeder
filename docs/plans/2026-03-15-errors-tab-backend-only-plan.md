# Errors Tab Backend-Only Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Limit the live Notifications Errors tab to backend-recorded failures while preserving frontend diagnostics in captured bundles.

**Architecture:** Keep backend APIs unchanged and tighten the UI data flow. `incidentWorkspaceStore` will expose backend-only diagnostic groups for live rendering, and `Errors.svelte` will consume that path instead of raw local diagnostics groups from `jobDiagnosticsStore`.

**Tech Stack:** Svelte 5, TypeScript, Vitest

---

### Task 1: Add failing store tests

**Files:**
- Modify: `apps/ui/src/lib/stores/incident_workspace.test.ts`

1. Add a failing test proving local-only diagnostics are excluded from live incident diagnostic groups.
2. Add a failing test proving backend diagnostic groups still appear for backend-only incidents.
3. Run the focused Vitest file and confirm the new behavior fails before implementation.

### Task 2: Implement backend-only live grouping

**Files:**
- Modify: `apps/ui/src/lib/stores/incident_workspace.svelte.ts`

1. Add a backend-only diagnostic-group selector for live incident rendering.
2. Keep existing bundle and local diagnostic ingestion intact.
3. Run the focused store tests and confirm they pass.

### Task 3: Wire the Errors page

**Files:**
- Modify: `apps/ui/src/lib/pages/Errors.svelte`

1. Remove direct dependence on `jobDiagnosticsStore.groups` for the live grouped diagnostics area.
2. Use backend-only incident groups from `incidentWorkspaceStore`.
3. Keep bundle capture/export behavior unchanged.
4. Run focused Errors/incident tests and confirm the page stays consistent.

### Task 4: Verification and docs

**Files:**
- Modify: `CHANGELOG.md`

1. Add an unreleased note explaining the Errors tab now surfaces backend errors only.
2. Run focused Vitest coverage for `incident_workspace` and diagnostics-related stores.
3. Run `npm --prefix apps/ui run check`.
4. Run `git diff --check`.
