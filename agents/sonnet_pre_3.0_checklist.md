# YA-WAMF Pre-3.0 Fix Checklist
**Source:** `sonnet_codereview_2026-04-15.md`  
**Date:** 2026-04-15  
**Total items:** 27 across 12 domains  
**Last updated:** 2026-04-15 — 17 items fixed (14 in v2.9.7, 3 in v2.9.8)  
**Format:** Work top-to-bottom. Check off each item when merged to dev.

---

## P0 — Fix before release

### [x] 1. Model downloads have no checksum verification — **DONE v2.9.7** (verification infrastructure added; warns when sha256 absent, enforces when present)
**File:** `backend/app/services/model_manager.py:1171–1181`  
**Problem:** `_validate_download_payload()` only checks file existence. A truncated, corrupt, or MitM-substituted download is silently activated as the live ML model.  
**Action:**
1. Add a `sha256` field to every entry in the `REMOTE_REGISTRY` dict.
2. Add a `_verify_checksum(file_path, expected_sha256)` helper using `hashlib.sha256` with 64 KB chunk reads.
3. Call it from `_validate_download_payload()` after the existence check, for every file in `required_files`.
4. If checksum fails, raise `RuntimeError` and delete the staged directory so it cannot be partially activated.

---

## P1 — Fix soon

### [x] 2. Rate-limit IP spoofing via X-Forwarded-For — **DONE v2.9.7**
**File:** `backend/app/ratelimit.py:14–37`  
**Problem:** `get_real_client_ip()` reads `X-Forwarded-For` directly from raw headers before `ProxyHeadersMiddleware` has processed them. Any direct client can spoof `X-Forwarded-For: 1.2.3.4` and bypass the 5-per-minute login rate limit entirely.  
**Action:**
1. Delete the custom `get_real_client_ip()` function.
2. Replace all call sites with `request.client.host` — this is the IP that ProxyHeadersMiddleware has already validated and normalised.
3. If the deployment is behind a trusted reverse proxy and the real client IP is needed, use slowapi's `get_remote_address(request)` which correctly uses the post-middleware `client.host`.

### [x] 3. Unbounded lock dictionaries in proxy.py — memory leak — **DONE v2.9.7**
**File:** `backend/app/routers/proxy.py:49–51, 150–171`  
**Problem:** `_preview_locks`, `_recording_clip_fetch_locks`, and `_snapshot_generation_locks` are module-level `dict[str, asyncio.Lock]`. A new entry is inserted per unique `event_id` and never removed. On a busy feeder with thousands of daily detections, these grow forever.  
**Action:**
1. Replace all three plain dicts with `weakref.WeakValueDictionary[str, asyncio.Lock]`.
2. Update the three `_*_lock(event_id)` helpers to store the lock in a strong local variable before returning it (so the caller's reference keeps the lock alive while it's held, but it is GC'd once no coroutine holds it).
3. Verify no other module holds long-lived references to these locks by name.

### [x] 4. MQTT in-flight task dicts may accumulate stale entries — **DONE v2.9.8** (_sweep_stale_event_task_entries() added; called from _connection_watchdog)
**File:** `backend/app/services/mqtt_service.py:46–49`  
**Problem:** `_event_task_tails`, `_event_tail_depths`, `_event_pending_tasks`, `_event_pending_payloads` are all keyed by Frigate event UUID. If a task completion path is missed (e.g. unexpected exception before the `del` call), entries persist for the lifetime of the service.  
**Action:**
1. Audit all code paths that insert into these dicts and confirm a corresponding `del` or `.pop()` exists in every exit path (including exception paths).
2. Add a periodic sweep (e.g. in `_connection_watchdog`) that removes entries whose task has `.done()` and whose depth is 0 and which are older than `LIVE_EVENT_STALE_SECONDS`.

### [x] 5. Partial video download not cleaned up on task cancellation — **DONE v2.9.7**
**File:** `backend/app/services/auto_video_classifier_service.py:152–175`  
**Problem:** When `stop()` cancels in-flight tasks, a task mid-download may leave a partial temp file in the OS temp directory because `CancelledError` can interrupt async context managers before `__aexit__` runs.  
**Action:**
1. Capture the temp file path into a local variable before entering the `async with` block.
2. Wrap the entire download-and-classify block in `try/finally` that calls `os.unlink(tmp_path)` (suppressing `FileNotFoundError`) — this runs even on `CancelledError`.

---

## P2 — Fix this sprint

### [x] 6. SSE token not revalidated after expiry mid-session — **DONE v2.9.8** (expiry checked every 60 heartbeats; session_expired event sent then stream closed)
**File:** `backend/app/main.py:779–806` (SSE `event_generator` loop)  
**Problem:** Token is validated once at connection time. A user whose token expires or is revoked can keep receiving SSE events indefinitely until they disconnect.  
**Action:**
1. Inside `event_generator()`, after each heartbeat yield, check `token_data.exp` against `datetime.now(timezone.utc)`.
2. If expired, `break` out of the loop — the client's SSE connection will close and it will re-authenticate on reconnect.
3. Only check every 60 iterations (not every message) to avoid per-message overhead.

### [x] 7. `location_temperature_unit` silently dropped in settings PUT — **DONE v2.9.7**
**File:** `backend/app/routers/settings.py:994–999`  
**Problem:** The condition `"location_weather_unit_system" not in fields_set` causes `location_temperature_unit` to be silently ignored when both fields are submitted together (which `saveSettings()` always does). The UI then shows the value as unsaved.  
**Action:**
1. Remove the `and "location_weather_unit_system" not in fields_set` guard entirely.
2. Apply both fields independently — set `temperature_unit` from the request and set the derived unit from `weather_unit_system` separately.
3. Add a regression test: submit both fields in one PUT, confirm both are persisted.

### [ ] 8. `GET /api/settings` missing response_model
**File:** `backend/app/routers/settings.py:626`  
**Problem:** No `response_model=` declared. FastAPI does not strip undeclared fields, so any future internal field added to the returned dict will be exposed to the client without a schema-level guard.  
**Action:**
1. Define a `SettingsResponse` Pydantic model mirroring the current dict structure.
2. Add `response_model=SettingsResponse` to the `@router.get("/settings")` decorator.
3. This is a large model — can be done incrementally with a permissive base model that explicitly lists all current keys.

### [x] 9. `GET /api/version` exposes git hash and branch without auth — **DONE v2.9.7**
**File:** `backend/app/main.py:809–817`  
**Problem:** `git_hash` and `branch` are useful attacker reconnaissance (identify exact commit, find known CVEs). They are returned to unauthenticated callers.  
**Action:**
1. Remove `git_hash` and `branch` from the unauthenticated `/api/version` response.
2. Keep them in the authenticated `/api/health` response (already there).
3. The frontend version display only needs `version` and `base_version` — confirm no UI breakage.

### [x] 10. Notification test endpoints return HTTP 200 for errors — **DONE v2.9.8** (502 for external failures, 400 for config errors; JSONResponse used throughout)
**File:** `backend/app/routers/settings.py:162–275`  
**Problem:** Notification send-test endpoints return `{"status": "error", "message": "..."}` with HTTP 200, which makes monitoring tooling unable to detect failures by status code.  
**Action:**
1. For external service failures (Discord, Telegram, Pushover, etc.), return `JSONResponse(status_code=502, content={"status": "error", "message": ...})`.
2. For bad-request errors (missing config), return `400`.
3. Update any frontend callers that check `response.status === "error"` to also handle non-200 HTTP status codes.

### [x] 11. `PRAGMA table_info()` uses unsafe f-string interpolation — **DONE v2.9.7**
**File:** `backend/app/repositories/detection_repository.py:395`  
**Problem:** `f"PRAGMA table_info({table_name})"` — PRAGMA does not support bind parameters. Currently only called with hardcoded literals, but the function signature accepts any string.  
**Action:**
1. Add a whitelist at the top of `_table_columns()`:
   ```python
   _ALLOWED_PRAGMA_TABLES = frozenset({"detections", "taxonomy_cache", "species_daily_rollup", "species_info_cache"})
   if table_name not in _ALLOWED_PRAGMA_TABLES:
       raise ValueError(f"Unexpected table name: {table_name!r}")
   ```
2. Apply the same pattern to the identical pattern in `debug.py:51–58`.

### [ ] 12. `$effect` in Dashboard.svelte reads and writes `selectedEvent` — loop risk
**File:** `apps/ui/src/lib/pages/Dashboard.svelte:227–242`  
**Problem:** An `$effect` that conditionally writes back to a `$state` it reads is safe only as long as `detectionSyncSignature()` covers every field of `Detection`. Any new field added to the `Detection` interface that is not added to `detectionSyncSignature()` will cause an infinite re-run loop.  
**Action:**
1. Add a comment above the effect explicitly listing the contract: "All fields of Detection must be represented in detectionSyncSignature() or this effect will loop."
2. Consider refactoring to `$derived` for `selectedEvent` sync — compute `mergedSelectedEvent` as a derived value from `detectionsStore.detections` and `selectedEvent`, removing the write-back pattern entirely.

### [ ] 13. Species rollup date range not bounded
**File:** `backend/app/repositories/detection_repository.py` (rollup query paths), `backend/app/routers/species.py` and `backend/app/routers/stats.py`  
**Problem:** No server-side cap on the date range span for species/stats aggregation queries. A caller requesting `start_date=2020-01-01` triggers a full-table aggregate scan.  
**Action:**
1. In the species and stats routers, add a guard: if `end_date - start_date > timedelta(days=365)`, return `HTTP 400` with message `"Date range must not exceed 365 days"`.
2. The frontend date picker already limits ranges visually — this is a server-side enforcement backstop.

### [ ] 14. CI coverage gate too low (20%)
**File:** `.github/workflows/build-and-push.yml:215`  
**Problem:** The 20% coverage minimum is too low to catch regressions in core pipeline code.  
**Action:**
1. Raise `--fail-under=20` to `--fail-under=40` as a first step.
2. Add unit tests for the most critical untested paths:
   - `event_processor.py`: stage timeout/fallback logic, `_classify_snapshot()` path
   - `classifier_service.py`: shape validation, non-finite output handling
3. Each test file added should bring coverage up; re-evaluate gate at 60% for v3.0.

### [ ] 15. No SAST or dependency audit in CI
**File:** `.github/workflows/build-and-push.yml` (missing steps)  
**Problem:** No `pip audit`, `npm audit`, Bandit, or Semgrep step. Known-vulnerable dependencies would not be flagged.  
**Action:**
1. Add after `pip install -r requirements.txt`:
   ```yaml
   - name: Audit Python dependencies
     run: pip install pip-audit && pip-audit -r requirements.txt
   ```
2. Add to the frontend job:
   ```yaml
   - name: Audit npm dependencies
     run: npm audit --audit-level=high
     continue-on-error: true   # warn only until baseline is clean
   ```
3. Once baseline is clean, remove `continue-on-error`.

---

## P3 — Fix when touching the file

### [x] 16. JWT timezone strip is unnecessary — **DONE v2.9.7**
**File:** `backend/app/auth.py:121–123`  
**Problem:** `token_data.exp.replace(tzinfo=None)` deliberately strips timezone after PyJWT has already enforced expiry. Unnecessary and could hide bugs if validation logic changes.  
**Action:** Remove the timezone strip. Keep `exp` as timezone-aware (`datetime` with `UTC`). Confirm no downstream comparison uses naive `datetime.now()`.

### [ ] 17. OAuth tokens stored as plaintext in SQLite
**File:** `backend/migrations/versions/10b7668f28ac_add_oauth_tokens_table.py:44–57`  
**Problem:** `access_token` and `refresh_token` are plain `String` columns. Filesystem access to `speciesid.db` gives live OAuth tokens for Gmail/Outlook.  
**Action:**
1. Add a Fernet encryption helper that derives a key from `settings.auth.session_secret`.
2. Encrypt on write (INSERT/UPDATE), decrypt on read (SELECT).
3. Create an Alembic migration to re-encrypt existing rows at startup (one-time migration).

### [ ] 18. OAuth tokens not cleaned up on logout
**File:** `backend/app/routers/auth.py:325–332`  
**Problem:** The logout endpoint does not delete OAuth tokens from the `oauth_tokens` table. Stale tokens persist until natural expiry.  
**Action:**
1. Add `DELETE FROM oauth_tokens WHERE user_id = ?` (or equivalent) in the logout handler.
2. Optionally accept a `?revoke_all_oauth=true` query param for explicit revocation vs. just session logout.

### [ ] 19. `taxonomy_cache` has no TTL or size bound
**File:** `backend/app/services/taxonomy/taxonomy_service.py`  
**Problem:** Cache rows accumulate indefinitely — one per unique species ever seen.  
**Action:**
1. Add `last_accessed_at TIMESTAMP` column to `taxonomy_cache` via Alembic migration.
2. Update the cache-write path to also write `last_accessed_at = now()`.
3. Include in the existing data-retention cleanup job: prune rows where `last_accessed_at < now() - retention_days * 2`.

### [ ] 20. Global notification cooldown suppresses all species
**File:** `backend/app/services/notification_service.py:21, 57–65`  
**Problem:** `last_notification_time` is a single global timer. A common-sparrow detection can suppress a rare-species notification that arrives 30 seconds later.  
**Action:**
1. Document the current global-cooldown behaviour explicitly in settings and the notification UI so users understand it.
2. As a follow-up enhancement, replace with a `dict[str, datetime]` per-species cooldown. This is a behaviour change and should be opt-in or defaulted to match current behaviour.

### [x] 21. Discord error log may include webhook URL — **DONE v2.9.7**
**File:** `backend/app/services/notification_service.py:220–228`  
**Problem:** `log.error(..., error=str(e))` — if `httpx.HTTPStatusError.__str__()` includes the request URL, the Discord webhook URL appears in logs.  
**Action:**
1. Replace `error=str(e)` with `error=type(e).__name__, status_code=e.response.status_code, response_body=e.response.text[:200]`.
2. Never pass the full exception string where a URL could be embedded.

### [x] 22. `taxonomyPollInterval` typed as `any` — **DONE v2.9.7**
**File:** `apps/ui/src/lib/pages/Settings.svelte:166`  
**Problem:** `let taxonomyPollInterval: any` — weak typing, potential timer leak if not cleared.  
**Action:**
1. Change to `let taxonomyPollInterval: ReturnType<typeof setInterval> | undefined`.
2. Confirm `clearInterval(taxonomyPollInterval)` is called in `onDestroy` (it is at line ~1983, but verify the variable name matches).

### [ ] 23. `logger.warn`/`logger.error` emit stack traces to browser console in production
**File:** `apps/ui/src/lib/utils/logger.ts:43–65`  
**Problem:** Stack traces from internal errors are emitted to `console.error` with no production guard.  
**Action:**
1. Strip `stack` from `errorContext` in production builds:
   ```typescript
   const isDev = import.meta.env.DEV;
   const errorContext = { message: ..., ...(isDev ? { stack: ... } : {}) };
   ```

### [x] 24. `GET /api/debug/db/stats` uses f-string table names — **DONE v2.9.7**
**File:** `backend/app/routers/debug.py:51–58`  
**Problem:** Pattern mirrors the PRAGMA issue — hardcoded now but unsafe if extended.  
**Action:** Apply same whitelist guard pattern as item 11.

### [ ] 25. SSE token mid-session validation (P2 listed here for reference)
Already listed as item 6 above.

### [x] 26. UNIQUE constraint on `frigate_event` not cleanly handled — **DONE v2.9.7**
**File:** `backend/app/repositories/detection_repository.py` (upsert path)  
**Problem:** Duplicate MQTT event IDs (rare but possible after restart) hit the UNIQUE constraint and are recorded as critical failures instead of benign duplicates.  
**Action:**
1. In the upsert/insert path, catch `aiosqlite.IntegrityError` before the generic `except Exception`.
2. On `IntegrityError` for `frigate_event`, log at `DEBUG` and return the existing detection row instead of recording a stage failure.

### [x] 27. Taxonomy sync redundant is_running pre-check — **DONE v2.9.7**
**File:** `backend/app/routers/settings.py:97–127`  
**Problem:** The `is_running` pre-check before `maintenance_coordinator.try_acquire()` is redundant and could give a misleading result if two requests are in-flight simultaneously.  
**Action:**
1. Remove the `if status["is_running"]` early-return.
2. Rely solely on `maintenance_coordinator.try_acquire()` to serialise access — it is already atomic and is the correct single source of truth.

---

## Summary by priority

| Priority | Count | Items |
|----------|-------|-------|
| P0 | 1 | #1 |
| P1 | 4 | #2, #3, #4, #5 |
| P2 | 10 | #6–#15 |
| P3 | 12 | #16–#27 |

## Progress tracker

- [x] P0 complete (v2.9.7 — checksum infrastructure in place)
- [ ] P1 complete (3/4 done — #4 MQTT task dict audit pending)
- [ ] P2 complete (#6 SSE re-validation, #8 SettingsResponse model, #10 notification 200→5xx, #13 date range cap, #14 coverage gate, #15 pip/npm audit pending)
- [ ] P3 complete (#17 OAuth encryption, #18 OAuth logout cleanup, #19 taxonomy cache TTL, #20 per-species cooldown, #23 console stack traces pending)
