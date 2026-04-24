# Issue 33 Fixture Replay Harness Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend the issue 33 harness so it can validate backfill and analyze-unknowns behavior without relying on live feeder detections.

**Architecture:** Add a harness-owned Frigate-compatible fixture server that serves local licensed bird fixture images as snapshots and a generated clip. Add an `issue33-fixture-replay` profile that publishes matching MQTT events, runs backfill, retags seeded detections as `Unknown Bird`, then triggers analyze-unknowns under MQTT stall pressure.

**Tech Stack:** Python standard library HTTP server, existing issue 33 harness, existing iNaturalist fixture downloader, existing backend owner APIs.

---

### Task 1: Add Fixture Frigate Helpers

**Files:**
- Modify: `scripts/run_issue33_harness.py`
- Test: `tests/unit/test_issue33_harness_script.py`

**Steps:**
1. Write tests for fixture image discovery and generated Frigate event metadata.
2. Run the new tests and verify they fail because helpers do not exist.
3. Implement helpers to discover local images and build Frigate-like event records.
4. Run the focused tests and verify they pass.

### Task 2: Add Fixture Server And Profile

**Files:**
- Modify: `scripts/run_issue33_harness.py`
- Test: `tests/unit/test_issue33_harness_script.py`

**Steps:**
1. Write tests proving `issue33-fixture-replay` applies fixture defaults and fixture load source is accepted.
2. Implement the profile, CLI args, and a local HTTP server for `/api/events`, `/api/events/{id}`, `/snapshot.jpg`, `/clip.mp4`, and `/api/config`.
3. Run focused unit tests.

### Task 3: Add Backfill And Analyze Assertions

**Files:**
- Modify: `scripts/run_issue33_harness.py`
- Test: `tests/unit/test_issue33_harness_script.py`

**Steps:**
1. Write tests for fixture replay evaluation: backfill must process seeded events and analyze-unknowns must accept or coalesce work without failures.
2. Add authenticated POST helpers for `/api/backfill` and `/api/events/bulk/manual-tag`.
3. Add summary fields and failure reasons for backfill/analyze gaps.
4. Run focused unit tests.

### Task 4: Verify In Container

**Files:**
- No code changes expected.

**Steps:**
1. Download a small fixture set using `backend/scripts/download_test_fixtures.py`.
2. Run an updated monolith canary with `FRIGATE__FRIGATE_URL=http://127.0.0.1:<fixture-port>`.
3. Execute `scripts/run_issue33_harness.py --stress-profile issue33-fixture-replay`.
4. Confirm summary proves MQTT liveness, inference health, backfill, and analyze-unknowns paths.

**Verification completed 2026-04-24:**
- Unit harness coverage: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest tests/unit/test_issue33_harness_script.py backend/tests/test_issue22_soak_harness.py -q`
- Isolated monolith canary: `issue33-fixture-replay` against fixture Great Tit images, isolated MQTT topics, shortened test-only MQTT stale thresholds.
- Canary result: PASS; backfill processed 6 fixture events with 0 errors, manual unknown tagging updated 5 events, analyze-unknowns accepted 1 candidate, topic-liveness reconnect delta was 3, BirdNET stayed fresh during the induced Frigate stall, and inference health remained `ok`.
