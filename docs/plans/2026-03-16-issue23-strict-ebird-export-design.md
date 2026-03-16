# Issue 23 Strict eBird Export Design

## Goal

Close the remaining issue-23 gaps by making YA-WAMF's eBird export a single strict, importer-safe path that always emits eBird-safe rows only.

## Problem

The latest reporter comment shows two categories of failure:

1. They still saw the old split date/time format in their exported CSV.
2. They still saw mixed-language common names and `Unknown Bird` rows.

The current `dev` code already formats single `Date` and `Time` columns, so the split-column report most likely came from a stale deployed backend or stale build. However, the mixed-language-name report is a real remaining logic gap because the exporter still falls back to localized `common_name` / `display_name` if English taxonomy resolution fails.

## Decision

Treat `/api/ebird/export` as a strict exporter, not a best-effort dump.

Rules:
- always exclude hidden detections
- always exclude `Unknown Bird`
- always exclude rows without a valid English common name
- always emit exactly 19 columns in eBird Record Format
- always use single `Date` and `Time` columns
- keep `Stationary`, per-day duration, configured `state/country`, and submission comments

If a detection cannot be rendered as an importer-safe eBird row, it is skipped.

## Why This Fixes The Issue

- Mixed-language names disappear because localized fallbacks are removed.
- `Unknown Bird` rows disappear because they are explicitly suppressed.
- Split date/time risk is constrained to a single backend route with direct regression coverage.
- Any future stale deployment confusion becomes easier to identify because the code path is now unambiguous and strongly tested.

## Scope

### Backend

- tighten row filtering in `backend/app/routers/ebird.py`
- enforce strict English-name requirement
- suppress unknown rows
- keep current date-range filtering behavior

### Frontend

- no new export options for unknown rows
- keep current range UI and `Export everything` toggle

### Docs

- update changelog to document strict suppression of `Unknown Bird` and non-English rows

## Verification

- regression tests for:
  - `Unknown Bird` excluded
  - localized names excluded when no English taxonomy name exists
  - strict 19-column shape with single `Date` and `Time`
  - range filtering still works after suppression
- direct local route verification after tests
