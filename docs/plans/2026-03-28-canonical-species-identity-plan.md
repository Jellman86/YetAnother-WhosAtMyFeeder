# Canonical Species Identity Normalization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make YA-WAMF treat species identity canonically (`taxa_id` -> `scientific_name` -> label fallback) across writes, queries, rollups, and historical repair.

**Architecture:** Centralize canonical identity SQL helpers in the detection repository, migrate rollups to canonical keys, harden all species-changing write paths to persist taxonomy fields together, and add an explicit repair command for historical rows. Keep `display_name` as presentation-only while preserving safe fallback behavior for unresolved rows like `Unknown Bird`.

**Tech Stack:** FastAPI, aiosqlite/SQLite, pytest, existing taxonomy service/cache, backend scripts

---

### Task 1: Add canonical-identity regression tests

**Files:**
- Modify: `backend/tests/test_detection_repository.py`
- Modify: `backend/tests/test_event_manual_update_api.py`
- Modify: `backend/tests/test_species_stats_api.py`
- Create: `backend/tests/test_canonical_identity_repair.py`

**Step 1: Write the failing repository tests**

Add tests that prove:
- `get_all()` and `get_count()` treat common/scientific display variants with the same `taxa_id` as one species when filtering by `species`
- rollup rebuild collapses rows with different `display_name` values but the same canonical identity
- unresolved labels like `Unknown Bird` remain separate

**Step 2: Run the targeted repository tests to verify failure**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_detection_repository.py backend/tests/test_species_stats_api.py -q -k "canonical or rollup or species_filter"
```

Expected: FAIL on display-name-based grouping/filter behavior and old rollup schema assumptions.

**Step 3: Write the failing write-path and repair tests**

Add tests that prove:
- manual rename preserves canonical identity when the new label is only an alias/localized variant of the same species
- historical repair fills missing `taxa_id` / `scientific_name` without changing already-canonical rows
- repair is idempotent on rerun

**Step 4: Run those tests to verify failure**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_event_manual_update_api.py backend/tests/test_canonical_identity_repair.py -q -k "canonical or repair"
```

Expected: FAIL because repair tooling and end-to-end canonical invariants do not exist yet.

### Task 2: Centralize canonical identity helpers in the repository

**Files:**
- Modify: `backend/app/repositories/detection_repository.py`
- Test: `backend/tests/test_detection_repository.py`

**Step 1: Add shared canonical SQL helpers**

Implement repository-private helpers for:
- canonical key SQL expression
- canonical join/filter conditions
- deterministic representative-row ranking

Use the canonical identity order:
- `taxa_id`
- `scientific_name`
- `display_name` fallback

**Step 2: Migrate filter/list methods**

Update:
- `get_all()`
- `get_count()`
- `get_unique_species()`
- `get_unique_species_with_taxonomy()`
- alias-resolution helpers as needed

So species filtering stops depending on raw `display_name` equality when the intent is canonical identity.

**Step 3: Run focused repository tests**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_detection_repository.py -q
```

Expected: PASS for repository canonicalization coverage.

### Task 3: Migrate rollups and leaderboard/stat queries to canonical keys

**Files:**
- Modify: `backend/app/db_schema.py`
- Modify: `backend/app/repositories/detection_repository.py`
- Modify: `backend/app/routers/species.py`
- Modify: `backend/app/routers/stats.py`
- Test: `backend/tests/test_detection_repository.py`
- Test: `backend/tests/test_species_stats_api.py`

**Step 1: Upgrade rollup schema support**

Change `species_daily_rollup` to store canonical identity fields:
- `canonical_key`
- `display_name`
- `scientific_name`
- `common_name`
- `taxa_id`

Keep display name for rendering, but make the primary key canonical.

**Step 2: Rebuild rollup-generation queries**

Update `ensure_recent_rollups()`, `get_rollup_metrics()`, and related helpers so they aggregate by canonical identity and emit one representative display row per species.

**Step 3: Update leaderboard/species read paths**

Make leaderboard/stat/species endpoints consume canonicalized repo results instead of display-name groups.

**Step 4: Run targeted stats tests**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_detection_repository.py backend/tests/test_species_stats_api.py -q
```

Expected: PASS with no duplicate alias rows in leaderboard/stat coverage.

### Task 4: Harden write/update paths for canonical invariants

**Files:**
- Modify: `backend/app/services/detection_service.py`
- Modify: `backend/app/routers/events.py`
- Modify: `backend/app/services/auto_video_classifier_service.py`
- Test: `backend/tests/test_detection_service.py`
- Test: `backend/tests/test_event_manual_update_api.py`

**Step 1: Audit species-changing write paths**

Ensure ingest, manual rename, and reclassification all update:
- `display_name`
- `category_name`
- `scientific_name`
- `common_name`
- `taxa_id`

in one coherent operation.

**Step 2: Prevent identity regression**

When a write path encounters partial taxonomy, prefer existing stronger canonical identity or cached taxonomy enrichment rather than degrading an already-canonical row.

**Step 3: Run targeted write-path tests**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_detection_service.py backend/tests/test_event_manual_update_api.py -q
```

Expected: PASS for manual-tag and ingest canonical invariants.

### Task 5: Add explicit historical repair tooling

**Files:**
- Create: `backend/scripts/repair_canonical_species_identity.py`
- Modify: `backend/app/services/taxonomy/taxonomy_service.py`
- Modify: `backend/app/repositories/detection_repository.py`
- Test: `backend/tests/test_canonical_identity_repair.py`

**Step 1: Add repair primitives**

Implement batchable repository support for selecting detections missing canonical fields and updating them safely.

**Step 2: Add the repair script**

Create an explicit script that:
- scans in batches
- resolves taxonomy from cache first, then service
- updates only missing/weaker canonical fields
- logs progress
- is safe to rerun

**Step 3: Reuse existing taxonomy behavior where sensible**

Avoid creating a second conflicting taxonomy-sync model. Share lookup/normalization logic with `taxonomy_service` where practical.

**Step 4: Run repair tests**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_canonical_identity_repair.py -q
```

Expected: PASS for idempotent repair behavior.

### Task 6: Final verification and documentation

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `ROADMAP.md`
- Optional docs touch: any backend docs that describe species grouping behavior

**Step 1: Run the focused end-to-end backend suite**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest \
  backend/tests/test_detection_repository.py \
  backend/tests/test_species_stats_api.py \
  backend/tests/test_event_manual_update_api.py \
  backend/tests/test_detection_service.py \
  backend/tests/test_canonical_identity_repair.py -q
```

Expected: PASS

**Step 2: Run schema/style safety checks**

Run:

```bash
git -C /config/workspace/YA-WAMF diff --check
```

Expected: no whitespace or merge-marker issues.

**Step 3: Update roadmap/changelog**

Document that canonical identity normalization is shipped end to end, including historical repair tooling.

**Step 4: Commit**

```bash
git -C /config/workspace/YA-WAMF add \
  backend/app/db_schema.py \
  backend/app/repositories/detection_repository.py \
  backend/app/routers/events.py \
  backend/app/routers/species.py \
  backend/app/routers/stats.py \
  backend/app/services/detection_service.py \
  backend/app/services/taxonomy/taxonomy_service.py \
  backend/scripts/repair_canonical_species_identity.py \
  backend/tests/test_detection_repository.py \
  backend/tests/test_species_stats_api.py \
  backend/tests/test_event_manual_update_api.py \
  backend/tests/test_detection_service.py \
  backend/tests/test_canonical_identity_repair.py \
  CHANGELOG.md \
  ROADMAP.md
git -C /config/workspace/YA-WAMF commit -m "feat(taxonomy): normalize canonical species identity"
```
