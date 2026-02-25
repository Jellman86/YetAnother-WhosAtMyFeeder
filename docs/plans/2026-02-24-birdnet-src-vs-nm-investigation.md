# BirdNET-Go src vs nm Audio Mapping Investigation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reproduce and isolate the BirdNET-Go camera/audio mapping failure in issue `#16`, specifically whether dynamic MQTT `src` values break correlation and whether stable `nm` values should be supported for mapping.

**Architecture:** This is an investigation-first plan, not an immediate fix. We will observe real MQTT payloads and YA-WAMF behavior end-to-end in the running dev environment, confirm which payload fields are stable across BirdNET-Go restarts, and only then choose a backward-compatible mapping strategy. The dashboard metric and event badges will be validated separately because they depend on audio correlation (`audio_confirmed`) rather than raw audio ingest.

**Tech Stack:** Docker containers (devEnvSJP), MQTT broker, BirdNET-Go MQTT payloads, YA-WAMF backend (FastAPI/Python), Svelte UI, GitHub issue triage notes

---

## Important Environment Note

This plan assumes execution in the current dev environment where the agent has direct access to all running containers, including the MQTT broker/container, and can observe traffic/logs directly (not just via user screenshots).

## Scope

- Investigate issue `#16` only (special case)
- Validate `src` vs `nm` field stability and suitability for mapping
- Confirm impact on:
  - Explorer event audio tags
  - Dashboard audio confirmation count
- Produce evidence and a recommended implementation direction
- Do **not** ship a code change until evidence is collected

## Out of Scope (for this plan)

- Final code implementation
- DB migrations (unless the chosen solution later requires schema changes)
- UI polish beyond wording changes required by the chosen mapping strategy

### Task 1: Baseline Code Path Confirmation

**Files:**
- Read: `backend/app/services/audio/audio_service.py`
- Read: `backend/app/repositories/detection_repository.py`
- Read: `backend/app/routers/stats.py`
- Read: `apps/ui/src/lib/components/settings/IntegrationSettings.svelte`
- Read: `apps/ui/src/lib/i18n/locales/en.json`

**Step 1: Reconfirm current ingest/matching fields**

Check:
- audio ingest source fields (`id`, `sensor_id`, `Source.id`)
- correlation filter path (`camera_audio_mapping` compared to `detection.sensor_id`)
- dashboard metric source (`detections.audio_confirmed`)

**Step 2: Record exact references in investigation notes**

Capture file references/line numbers for:
- ingest field extraction
- matching logic
- dashboard count query
- settings UI wording (“Sensor ID”)

**Step 3: Commit**

No commit (investigation notes only).

### Task 2: Identify Container Names and MQTT Access Method

**Files:**
- None (runtime inspection)

**Step 1: List containers**

Run:
```bash
docker ps --format '{{.Names}}\t{{.Image}}'
```

Expected:
- YA-WAMF backend/frontend containers
- BirdNET-Go container (or equivalent source)
- MQTT broker container

**Step 2: Determine available MQTT tools**

Check whether `mosquitto_sub` is available in:
- the MQTT broker container
- backend container
- current workspace container

Examples:
```bash
docker exec <mqtt-container> sh -lc 'command -v mosquitto_sub || command -v mqtt sub || true'
docker exec <backend-container> sh -lc 'command -v mosquitto_sub || true'
```

**Step 3: Document the final subscription command pattern**

Save the exact command used for repeatable payload capture in the investigation notes.

**Step 4: Commit**

No commit.

### Task 3: Capture Real BirdNET-Go MQTT Payload Samples (Pre-Restart)

**Files:**
- Create (temp evidence): `/tmp/birdnet-payloads-pre-restart.log`

**Step 1: Subscribe to BirdNET-Go topic**

Use the configured topic (default likely `birdnet/text`) and capture several messages:
```bash
docker exec <mqtt-container> sh -lc 'mosquitto_sub -h <broker-host> -t "birdnet/text" -v -C 10' | tee /tmp/birdnet-payloads-pre-restart.log
```

**Step 2: Extract candidate mapping fields**

For each payload, record presence/value of:
- `src`
- `nm`
- `id`
- `sensor_id`
- nested `Source.id`
- nested `Source.name` (if present)

**Step 3: Note camera mapping expectations**

For at least one camera, map:
- Frigate camera name
- current YA-WAMF `camera_audio_mapping` value
- observed BirdNET payload fields

**Step 4: Commit**

No commit.

### Task 4: Capture Samples After BirdNET-Go Restart (Stability Test)

**Files:**
- Create (temp evidence): `/tmp/birdnet-payloads-post-restart.log`

**Step 1: Restart BirdNET-Go container**

Run:
```bash
docker restart <birdnet-go-container>
```

**Step 2: Re-capture payloads**

Use the same subscription command and collect comparable samples.

**Step 3: Compare field stability**

Create a small comparison table in notes:
- `src`: stable or changed?
- `nm`: stable or changed?
- `id`/`Source.id`: stable or changed?

**Step 4: Commit**

No commit.

### Task 5: Reproduce YA-WAMF Correlation Behavior End-to-End

**Files:**
- Read: `backend/app/services/audio/audio_service.py`
- Read: `backend/app/services/event_processor.py`

**Step 1: Confirm raw ingest is working**

Verify one or more of:
- backend logs show “Audio detection added to buffer”
- `Recent Audio` UI panel updates
- `/api/audio/recent` (or equivalent endpoint) returns detections

**Step 2: Test with mapping using current `src`/ID value**

Set `camera_audio_mapping` to the currently observed ID field and verify:
- Explorer event gets audio tag / audio confirmed state (when timing/species align)
- dashboard `audio_confirmations` moves above zero for the test window

**Step 3: Restart BirdNET-Go and retest without changing mapping**

Expected (hypothesis):
- raw audio ingest still works
- correlation fails if ID changed
- dashboard count remains zero or drops unexpectedly

**Step 4: Test with mapping using `nm` value (if present)**

Repeat the same checks using `nm` as the mapping value.

**Step 5: Commit**

No commit.

### Task 6: Evaluate Uniqueness / Collision Risk of `nm`

**Files:**
- None (runtime evidence + notes)

**Step 1: Inventory all cameras/audio streams**

For each configured camera stream, capture:
- Frigate camera name
- BirdNET payload `src`
- BirdNET payload `nm`
- any nested source metadata

**Step 2: Check collision scenarios**

Verify whether any of these occur:
- multiple BirdNET streams share the same `nm`
- `nm` missing for some payloads
- `nm` differs only by case/spacing

**Step 3: Decide acceptance criteria for using `nm`**

Document whether `nm` is:
- safe as primary mapping key
- safe as optional fallback only
- unsafe without additional disambiguation

**Step 4: Commit**

No commit.

### Task 7: Choose Fix Strategy (Design Decision Only)

**Files:**
- Potential future touchpoints (do not edit yet):
  - `backend/app/services/audio/audio_service.py`
  - `backend/app/repositories/detection_repository.py`
  - `apps/ui/src/lib/components/settings/IntegrationSettings.svelte`
  - `apps/ui/src/lib/i18n/locales/en.json`

**Step 1: Compare approaches**

Evaluate at least these options:
1. `nm` replaces `src`/ID matching completely
2. Backward-compatible dual matching (ID first, then `nm`)
3. Explicit mapping mode (user chooses ID vs Name)
4. Store both `sensor_id` and `sensor_name` and match against either

**Step 2: Recommend one approach**

Recommendation should include:
- backward compatibility impact
- false-positive risk
- UI clarity impact
- migration/testing cost

**Step 3: Write a short design decision summary**

Add a summary section at the bottom of this file with:
- evidence collected
- chosen direction
- why alternatives were rejected

**Step 4: Commit**

Optional commit (docs only) if the plan file is updated with completed evidence.

### Task 8: Prepare Follow-Up Implementation Plan (Only After Evidence)

**Files:**
- Create: `docs/plans/YYYY-MM-DD-birdnet-mapping-fix.md` (future)

**Step 1: Convert evidence into implementation tasks**

Only after Task 7 is complete, create a separate implementation plan covering:
- backend ingest/matching changes
- UI copy/help text changes (if needed)
- tests
- verification steps

**Step 2: Include direct regression tests**

Required scenarios:
- stable ID mapping works
- dynamic ID changes after restart
- `nm` mapping works across restart
- missing `nm` payload fallback behavior
- dashboard count reflects confirmed audio correlations

**Step 3: Commit**

Optional docs-only commit.

## Verification Checklist (Investigation Completion)

- [ ] Real MQTT payloads captured before restart
- [ ] Real MQTT payloads captured after restart
- [ ] `src`/`nm` stability compared with evidence
- [ ] YA-WAMF correlation behavior reproduced end-to-end
- [ ] Dashboard count behavior explained with evidence
- [ ] Collision risk of `nm` evaluated
- [ ] Fix strategy recommendation documented
- [ ] Separate implementation plan created (optional, after evidence)

## Notes for Future Execution

- Prefer direct observation over screenshots for this issue.
- Preserve raw payload examples (redact sensitive network identifiers if sharing externally).
- Keep `#16` open until the mapping-key behavior is validated against real restarts.

## Initial Live Test Results (2026-02-25)

Completed a real restart test against the running containers (`birdnet-go`, `mosquitto`, `yawamf-backend`).

### Evidence observed directly

- BirdNET-Go MQTT payloads on `birdnet/#` include both:
  - dynamic ID-style field: `src` / `Source.id`
  - stable name field: `nm` / `Source.displayName`
- YA-WAMF backend currently ingests/stores `sensor_id` from the ID-style field (matches code path and logs).

### Before/After restart comparison (same camera)

- Before restart:
  - `src` / `Source.id`: `rtsp_46d334cf`
  - `nm` / `Source.displayName`: `BirdCam`
- After restart:
  - `src` / `Source.id`: `rtsp_3b6c6363`
  - `nm` / `Source.displayName`: `BirdCam`

### Conclusion from this test

- `src` / `Source.id` is not stable across BirdNET-Go restarts in this environment.
- `nm` / `Source.displayName` remained stable across the same restart in this environment.
- The reporter's `nm` hypothesis is validated as a real and plausible mapping key (pending multi-stream collision checks).

### Additional local context

- This instance currently has `camera_audio_mapping` set to wildcard (`"BirdCam": "*"`) so it does not reproduce the exact "mapping breaks after restart" symptom until a fixed non-wildcard mapping is configured.

### Step 2 follow-on (current-build limitation)

- The current backend cannot actually validate `nm` mapping end-to-end yet, because all correlation/context filtering is performed against `sensor_id` only.
- Live `/api/audio/context` responses for `camera=BirdCam` (with wildcard mapping in place) show detections with `sensor_id=rtsp_3b6c6363`, not `BirdCam`.
- If `camera_audio_mapping["BirdCam"]` were set to `BirdCam` in the current implementation, it would not match these rows because `nm`/`Source.displayName` is not stored or matched as a first-class field.

Implication:
- We have enough evidence to proceed to a fix design/implementation plan for `id + nm` support.
