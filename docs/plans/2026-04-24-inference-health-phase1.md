# Inference Health Phase 1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add additive classifier inference-health telemetry for issue `#33` without changing routing, fallback, or admission behavior.

**Architecture:** Introduce `backend/app/services/inference_health.py` as a small state holder keyed by `(backend, provider, model_id)`. `ClassifierService` records outcomes at the coordinated inference boundary and exposes a new top-level `inference_health` status field; existing fallback fields remain unchanged.

**Tech Stack:** Python, pytest, existing classifier admission/status code.

---

### Task 1: InferenceHealth Module

**Files:**
- Create: `backend/app/services/inference_health.py`
- Test: `backend/tests/test_inference_health.py`

**Steps:**
1. Write tests for rolling latency/error windows, verdict transitions, cooldown, and snapshot shape.
2. Run the tests and verify they fail because the module does not exist.
3. Implement `RuntimeKey`, `InferenceHealth.record()`, `verdict()`, `cooldown_remaining()`, and `snapshot()`.
4. Run the module tests and verify they pass.

### Task 2: ClassifierService Additive Wiring

**Files:**
- Modify: `backend/app/services/classifier_service.py`
- Test: `backend/tests/test_classifier_service.py`

**Steps:**
1. Write tests proving `get_status()` exposes `inference_health` and successful inference records `ok` without changing legacy recovery fields.
2. Run the targeted tests and verify they fail before wiring.
3. Initialize `self._inference_health`, record outcomes in `_run_coordinated_inference()`, and include `inference_health` in `get_status()`.
4. Run targeted tests and a focused classifier suite.

### Task 3: Docs And Verification

**Files:**
- Modify: `CHANGELOG.md`

**Steps:**
1. Add a changelog entry noting additive inference-health telemetry for issue `#33`.
2. Run focused backend tests.
3. Review `git diff`, commit, and push `dev`.
