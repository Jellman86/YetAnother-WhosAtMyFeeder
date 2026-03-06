# Owner-Only Jobs And Errors Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Keep public Notifications accessible while making Jobs and Errors owner-only, and stop guest sessions from generating owner-auth poll noise.

**Architecture:** Centralize notification-tab access rules in the route helper so route canonicalization, keyboard shortcuts, and deep links all agree on guest behavior. Then apply the same owner check in the Notifications and Jobs pages so guest sessions neither render owner tabs nor poll owner-only endpoints.

**Tech Stack:** Svelte 5, TypeScript, Vitest

---

### Task 1: Route access rules

**Files:**
- Modify: `apps/ui/src/lib/app/notifications_route.ts`
- Test: `apps/ui/src/lib/app/notifications_route.test.ts`

**Step 1: Write the failing test**

Add tests that assert guest/public access is canonicalized to `/notifications` for `/jobs`, `/notifications/jobs`, and `/notifications/errors`, while owners keep the existing routes.

**Step 2: Run test to verify it fails**

Run: `npm --prefix apps/ui test -- src/lib/app/notifications_route.test.ts`

**Step 3: Write minimal implementation**

Add auth-aware helpers for:
- determining whether a tab is owner-only
- resolving a requested notification path to the correct canonical path for owner vs guest access

**Step 4: Run test to verify it passes**

Run: `npm --prefix apps/ui test -- src/lib/app/notifications_route.test.ts`

**Step 5: Commit**

Skip commit in this session unless requested.

### Task 2: UI tab visibility and guest-safe jobs polling

**Files:**
- Modify: `apps/ui/src/App.svelte`
- Modify: `apps/ui/src/lib/pages/Notifications.svelte`
- Modify: `apps/ui/src/lib/pages/Jobs.svelte`
- Modify: `apps/ui/src/lib/components/GlobalProgress.svelte`
- Test: `apps/ui/src/lib/app/notifications_route.test.ts`

**Step 1: Write the failing test**

Extend the route-helper test to cover owner-tab path generation for guests vs owners so the UI entry points can reuse one tested helper.

**Step 2: Run test to verify it fails**

Run: `npm --prefix apps/ui test -- src/lib/app/notifications_route.test.ts`

**Step 3: Write minimal implementation**

- Make `App.svelte` canonicalize notification routes using owner/public access.
- Hide Jobs/Errors tabs for guests in `Notifications.svelte`.
- Make `Jobs.svelte` skip queue polling for guests.
- Make `GlobalProgress` open the public Notifications tab for guests.

**Step 4: Run test to verify it passes**

Run: `npm --prefix apps/ui test -- src/lib/app/notifications_route.test.ts`

**Step 5: Commit**

Skip commit in this session unless requested.

### Task 3: Regression verification

**Files:**
- Verify: `apps/ui/src/lib/app/notifications_route.test.ts`
- Verify: `apps/ui/src/lib/stores/job_diagnostics.test.ts`

**Step 1: Run targeted tests**

Run: `npm --prefix apps/ui test -- src/lib/app/notifications_route.test.ts src/lib/stores/job_diagnostics.test.ts`

**Step 2: Run UI type checks**

Run: `npm --prefix apps/ui check`

**Step 3: Confirm expected result**

Expected:
- notification route tests pass
- diagnostics tests still pass
- Svelte type check passes

**Step 4: Commit**

Skip commit in this session unless requested.
