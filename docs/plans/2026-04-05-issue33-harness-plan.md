# Issue 33 Harness Refresh Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refresh the `#33` soak harness so it evaluates BirdNET liveness correctly on current builds and stops failing on stale counter semantics.

**Architecture:** Leave the shared issue-22 soak evaluator intact and add issue-33-specific post-processing in `run_issue33_harness.py`. Replace BirdNET count-growth failure with synthetic-publisher success plus BirdNET freshness across the induced Frigate-stall window, and expose those facts in the summary.

**Tech Stack:** Python, pytest, harness script, health-payload sampling

---

### Task 1: Lock the new issue-33 evaluation contract with tests

**Files:**
- Modify: `tests/unit/test_issue33_harness_script.py`

**Step 1: Write failing tests**

Add tests for:
- stripping the stale BirdNET delta failure when induced stall mode is active and BirdNET remained fresh
- failing when the BirdNET publisher did not publish
- failing when BirdNET goes stale during the induced stall window

**Step 2: Run focused test**

Run:
`python3 -m pytest /config/workspace/YA-WAMF/tests/unit/test_issue33_harness_script.py -q`

Expected: FAIL before implementation.

### Task 2: Implement issue-33-specific BirdNET liveness evaluation

**Files:**
- Modify: `scripts/run_issue33_harness.py`

**Step 1: Add BirdNET stall-window analysis helper**

Compute whether BirdNET stayed fresh during the induced Frigate-stall window using sampled health data.

**Step 2: Normalize issue-33 evaluation**

Remove the stale BirdNET-delta failure and replace it with:
- publisher-success validation
- stall-window freshness validation

**Step 3: Extend summary**

Add BirdNET liveness facts to the `evaluation` payload so red runs are interpretable without opening raw samples.

### Task 3: Verify and rerun the live harness

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Run focused tests**

Run:
`python3 -m pytest /config/workspace/YA-WAMF/tests/unit/test_issue33_harness_script.py -q`

Expected: PASS.

**Step 2: Rerun the full issue-33 soak**

Use the live monolith endpoint and current owner credentials.

**Step 3: Review summary**

Confirm the new pass/fail result reflects real `#33` signals rather than BirdNET counter drift.
