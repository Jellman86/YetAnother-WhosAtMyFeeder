# Canonical Species Identity Normalization Design

## Goal

Finish the migration from display-name-based species identity to canonical taxonomy identity across YA-WAMF so detections, filters, rollups, leaderboards, and manual edits consistently treat the same species as the same entity.

## Problem

YA-WAMF already stores `scientific_name`, `common_name`, and `taxa_id` on detections, but the system still mixes presentation labels with identity:

- new detections persist taxonomy fields, but many queries still group and filter by `display_name`
- historical rows are inconsistent because earlier data may be missing canonical fields
- derived tables such as `species_daily_rollup` still key by display name
- manual tag and reclassification paths update visible labels, but canonical identity is not treated as the single source of truth everywhere

That creates duplicate species rows, localization mismatches, and inconsistent statistics.

## Canonical Identity Model

Species identity should be defined in this order:

1. `taxa_id`
2. `scientific_name`
3. unresolved label fallback

`display_name` remains a presentation field only. It can still reflect common-name display preference or localization, but it must not define species identity for grouping, rollups, or correlation.

## Scope

This migration covers:

- detection write/update paths
- manual tag and reclassification paths
- historical repair/backfill of existing detections
- species and leaderboard repository queries
- species rollup storage and rebuild
- regression tests for canonical grouping and alias handling

This migration does not attempt to localize stored names or redesign UI copy.

## Architecture

### 1. Centralized Canonical Key Semantics

Add shared repository helpers that express canonical identity in SQL:

- canonical key expression: `COALESCE(CAST(taxa_id AS TEXT), LOWER(scientific_name), LOWER(display_name))`
- canonical display ranking: prefer rows with `taxa_id`, then `scientific_name`, then stable display fallback

All species grouping and filter paths should use the same helper instead of handwritten `display_name` comparisons.

### 2. Write-Path Hardening

All write paths that create or change species identity must update:

- `display_name`
- `scientific_name`
- `common_name`
- `taxa_id`

This includes:

- detection ingest via `DetectionService.save_detection`
- manual renames in the events router
- reclassification result application
- any repair/backfill path that fills in missing taxonomy

If taxonomy lookup fails, the row remains valid via unresolved label fallback. The migration must not make canonical fields mandatory for unknown or unresolved rows.

### 3. Historical Repair

Add an idempotent repair path that scans existing detections and fills missing canonical fields from:

1. taxonomy cache
2. taxonomy service lookup when needed

The repair should:

- run in batches
- log progress
- be safe to rerun
- avoid degrading rows that already have stronger canonical identity

This should be an explicit maintenance command/script, not hidden in startup.

### 4. Rollup Migration

`species_daily_rollup` should store canonical identity instead of using `display_name` as its primary key.

Recommended rollup shape:

- `rollup_date`
- `canonical_key`
- `display_name`
- `scientific_name`
- `common_name`
- `taxa_id`
- counters/timestamps already present

The table should preserve a display label for convenience, but canonical identity should define uniqueness. After the schema change, rebuild rollups from detections so historical stats align with the repaired rows.

### 5. Query Migration

Repository methods should move from display-name identity to canonical identity:

- species list endpoints
- recent species pages
- leaderboard base/window queries
- species filters where the intent is “same species”

Label fallback remains valid for unresolved rows, including `Unknown Bird`.

## Safety Rules

- `Unknown Bird` and other unresolved labels stay distinct until taxonomy resolves to a real species
- manual edits must not wipe stronger canonical identity accidentally
- historical repair must be idempotent
- queries must preserve deterministic display-name choice when multiple rows share a canonical identity
- localized rendering remains a response-layer concern, not a storage key

## Verification Strategy

Add regression coverage for:

- grouping two detections with different `display_name` values but the same `taxa_id`
- scientific-name fallback grouping when `taxa_id` is absent
- manual tag updates writing canonical fields consistently
- rollup rebuild collapsing alias duplicates into one canonical species entry
- unresolved labels remaining safely separate
- repair command updating historical rows without changing already-canonical rows incorrectly

## Rollout

1. Add failing tests for canonical grouping, filtering, write paths, and rollups.
2. Migrate rollup schema and rebuild path.
3. Refactor repository queries onto centralized canonical helpers.
4. Harden manual-update/write paths.
5. Add repair command and tests.
6. Update roadmap/changelog once behavior is shipped.
