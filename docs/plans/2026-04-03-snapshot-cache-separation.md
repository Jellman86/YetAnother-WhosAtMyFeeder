# Snapshot Cache Separation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Separate thumbnail and full snapshot cache behavior so low-resolution thumbnail requests cannot poison canonical event snapshots, and switch the detection modal to use the full snapshot route.

**Architecture:** Add a dedicated thumbnail cache path beside the existing snapshot cache path in the media-cache service. Update the proxy routes so `/thumbnail.jpg` only reads/writes thumbnail cache, `/snapshot.jpg` only reads/writes canonical snapshot cache with poisoned-cache self-heal, and detail UI consumes the snapshot route while cards keep using thumbnails.

**Tech Stack:** FastAPI, Svelte 5, Python media cache service, pytest, Vitest source-layout tests

---

### Task 1: Document the split cache contract in tests

**Files:**
- Modify: `backend/tests/test_media_cache.py`
- Modify: `backend/tests/test_proxy.py`
- Test: `apps/ui/src/lib/components/detection-modal-full-visit.layout.test.ts`

**Step 1: Write the failing backend test for thumbnail/snapshot separation**

Add a test that:
- caches a thumbnail-sized image through the thumbnail path
- caches a larger snapshot through the snapshot path
- asserts the two cached artifacts are independent

**Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_media_cache.py backend/tests/test_proxy.py -k 'thumbnail or snapshot' -q`
Expected: FAIL because the cache still shares one snapshot entry

**Step 3: Write the failing backend self-heal test**

Add a proxy test that:
- seeds a thumbnail-sized cached "snapshot"
- calls `/api/frigate/{event_id}/snapshot.jpg`
- expects the route to evict/refetch instead of serving the tiny cached bytes

**Step 4: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_proxy.py -k 'poisoned or thumbnail' -q`
Expected: FAIL because `/snapshot.jpg` still trusts the poisoned cache

**Step 5: Write the failing UI test**

Update the modal layout test to assert the modal image uses `getSnapshotUrl(...)`.

**Step 6: Run UI test to verify it fails**

Run: `npm --prefix apps/ui test -- src/lib/components/detection-modal-full-visit.layout.test.ts`
Expected: FAIL because the modal still uses `getThumbnailUrl(...)`

### Task 2: Implement dedicated thumbnail cache behavior

**Files:**
- Modify: `backend/app/services/media_cache.py`
- Test: `backend/tests/test_media_cache.py`

**Step 1: Add dedicated thumbnail cache path/helpers**

Implement:
- thumbnail cache file path
- `cache_thumbnail(...)`
- `get_thumbnail(...)`
- any needed invalidation helpers

Do not disturb canonical snapshot cache behavior.

**Step 2: Run targeted media-cache tests**

Run: `python -m pytest backend/tests/test_media_cache.py -q`
Expected: PASS

### Task 3: Fix proxy route cache contracts and self-heal

**Files:**
- Modify: `backend/app/routers/proxy.py`
- Test: `backend/tests/test_proxy.py`

**Step 1: Update `/snapshot.jpg`**

Implement:
- read canonical snapshot cache only
- detect clearly thumbnail-sized cached "snapshots"
- evict/refetch instead of serving poisoned bytes

**Step 2: Update `/thumbnail.jpg`**

Implement:
- read/write dedicated thumbnail cache only
- stop writing thumbnail responses into snapshot cache

**Step 3: Run proxy regression tests**

Run: `python -m pytest backend/tests/test_proxy.py -k 'thumbnail or snapshot' -q`
Expected: PASS

### Task 4: Switch modal detail image to canonical snapshot

**Files:**
- Modify: `apps/ui/src/lib/components/DetectionModal.svelte`
- Test: `apps/ui/src/lib/components/detection-modal-full-visit.layout.test.ts`

**Step 1: Replace modal image route**

Change the modal image from `getThumbnailUrl(...)` to `getSnapshotUrl(...)`.

**Step 2: Run UI regression test**

Run: `npm --prefix apps/ui test -- src/lib/components/detection-modal-full-visit.layout.test.ts`
Expected: PASS

### Task 5: Verify the full fix set

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Update changelog**

Document:
- thumbnail/snapshot cache split
- poisoned snapshot self-heal
- modal snapshot route change

**Step 2: Run focused verification**

Run: `python -m pytest backend/tests/test_media_cache.py backend/tests/test_proxy.py -q`
Expected: PASS

Run: `npm --prefix apps/ui test -- src/lib/components/detection-modal-full-visit.layout.test.ts`
Expected: PASS

Run: `npm --prefix apps/ui run check`
Expected: PASS

**Step 3: Review second-order effects**

Specifically verify:
- cards still use thumbnails
- modal uses snapshot
- thumbnail cache cannot affect snapshot cache
- snapshot self-heal only applies to canonical snapshot path
