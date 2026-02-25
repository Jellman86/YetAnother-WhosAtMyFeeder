# BirdNET Source Name Mapping (nm) Hard Switch Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace unstable BirdNET ID-based camera mapping with source-name (`nm` / `Source.displayName`) mapping and add a helper endpoint/UI surface that shows recently observed BirdNET source names for easier setup.

**Architecture:** Keep the existing `sensor_id` storage field to avoid a migration, but change its ingest semantics to store the canonical BirdNET source name. Add a new `/api/audio/sources` endpoint to expose recently seen names (with debug metadata), then update the Settings UI and translations to guide users toward source-name mapping.

**Tech Stack:** FastAPI (Python), SQLite via repository layer, Svelte 5 + TypeScript, existing YA-WAMF audio services/routes/settings UI

---

### Task 1: Add Failing Tests for BirdNET Source Name Extraction (Audio Service)

**Files:**
- Modify: `backend/tests/test_audio_service.py`
- Modify (implementation later): `backend/app/services/audio/audio_service.py`

**Step 1: Write failing tests for `nm` precedence**

Add tests covering:
- payload with `nm` and `src` stores `sensor_id == nm`
- payload with nested `Source.displayName` and `Source.id` stores display name
- payload with missing name falls back to existing ID behavior

Example:
```python
@pytest.mark.asyncio
async def test_add_detection_prefers_birdnet_nm_for_mapping_key(audio_service):
    now = datetime.now(timezone.utc)
    ts = (now - timedelta(seconds=5)).isoformat().replace('+00:00', 'Z')
    data = {
        "src": "rtsp_abc123",
        "nm": "BirdCam",
        "CommonName": "Dunnock",
        "Confidence": 0.8,
        "BeginTime": ts,
    }
    await audio_service.add_detection(data)
    assert audio_service._buffer[0].sensor_id == "BirdCam"
```

**Step 2: Run tests to verify failure**

Run:
```bash
cd YA-WAMF/backend && python -m pytest tests/test_audio_service.py -k "birdnet_nm or displayname" -v
```

Expected:
- FAIL because current code stores `id`/`Source.id` only.

**Step 3: Commit**

No commit yet.

### Task 2: Implement Canonical BirdNET Source Name Ingest (Hard Switch)

**Files:**
- Modify: `backend/app/services/audio/audio_service.py`

**Step 1: Implement extraction helper (minimal, local to service)**

Add a small helper (private function/method) to derive the canonical mapping key:
- `nm`
- `Source.displayName`
- fallback: `id` / `sensor_id` / `Source.id`

Example shape:
```python
def _extract_mapping_key(data: dict) -> Optional[str]:
    source = data.get("Source") if isinstance(data.get("Source"), dict) else {}
    for value in (data.get("nm"), source.get("displayName"), data.get("id"), data.get("sensor_id"), source.get("id")):
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
```

**Step 2: Replace current `sensor_id` assignment in `add_detection()`**

Use the helper for `sensor_id` so the stored value becomes the source name in normal BirdNET-Go payloads.

**Step 3: Add debug logging fields (optional but useful)**

Log both:
- stored canonical key (`sensor_id`)
- raw ID-style source if present (for diagnosis)

**Step 4: Run targeted tests**

Run:
```bash
cd YA-WAMF/backend && python -m pytest tests/test_audio_service.py -v
```

Expected:
- existing tests still pass (update assertions where ID-based expectation changed)
- new extraction tests pass

**Step 5: Commit**

```bash
git add backend/app/services/audio/audio_service.py backend/tests/test_audio_service.py
git commit -m "fix(audio): use BirdNET source names for camera mapping"
```

### Task 3: Add Helper Endpoint for Recently Observed BirdNET Sources

**Files:**
- Modify: `backend/app/routers/audio.py`
- Modify (if needed): `backend/app/repositories/detection_repository.py`
- Create (if adding router tests): `backend/tests/test_audio_router.py`

**Step 1: Define response model(s) in router**

Add a lightweight response shape for discovered sources, e.g.:
```python
class AudioSourceResponse(BaseModel):
    source_name: str
    last_seen: datetime
    sample_source_id: str | None = None
    seen_count: int = 1
```

**Step 2: Implement `/audio/sources` endpoint**

Behavior:
- Return recent distinct source names
- Include last-seen timestamp
- Parse `raw_data` JSON to extract sample `src` / `Source.id` if available
- Exclude blank/unknown names

Prefer DB-backed query for persistence (recommended), with in-memory fallback if faster to ship.

**Step 3: Add failing/then passing tests**

If router tests are practical in this repo, add focused tests for:
- dedup by source name
- `last_seen` ordering desc
- helper handles rows without `nm` gracefully

If router test scaffolding is heavy, add repository-level tests or document manual verification and keep unit coverage in `test_audio_service.py`.

**Step 4: Run tests**

Run:
```bash
cd YA-WAMF/backend && python -m pytest tests/test_audio_service.py tests/test_audio_router.py -v
```

Expected:
- PASS (or run only the implemented test file set)

**Step 5: Commit**

```bash
git add backend/app/routers/audio.py backend/app/repositories/detection_repository.py backend/tests/test_audio_router.py
git commit -m "feat(audio): expose recent BirdNET source names"
```

### Task 4: Add Frontend API Client for Audio Source Helper

**Files:**
- Modify: `apps/ui/src/lib/api.ts`

**Step 1: Add types**

Add TS interface:
```ts
export interface AudioSourceOption {
  source_name: string;
  last_seen: string;
  sample_source_id?: string | null;
  seen_count?: number;
}
```

**Step 2: Add fetch function**

```ts
export async function fetchAudioSources(limit = 20): Promise<AudioSourceOption[]> {
  const response = await apiFetch(`${API_BASE}/audio/sources?limit=${limit}`);
  return handleResponse<AudioSourceOption[]>(response);
}
```

**Step 3: Run type check (targeted/full UI check)**

Run:
```bash
cd YA-WAMF/apps/ui && npm run check
```

Expected:
- PASS or type errors only in touched code to fix before continuing.

**Step 4: Commit**

```bash
git add apps/ui/src/lib/api.ts
git commit -m "feat(ui): add BirdNET audio source helper API client"
```

### Task 5: Update Settings UI for “BirdNET Source Name” Mapping + Helper List

**Files:**
- Modify: `apps/ui/src/lib/components/settings/IntegrationSettings.svelte`
- Modify: `apps/ui/src/lib/pages/Settings.svelte`
- Modify: `apps/ui/src/lib/i18n/locales/en.json`
- Modify (follow-up same task): `apps/ui/src/lib/i18n/locales/*.json`

**Step 1: Replace ID-oriented UI copy in English**

Rename:
- “Sensor Mapping” -> “BirdNET Source Mapping” (or similar)
- “Sensor ID” -> “BirdNET Source Name”
- remove `*` dynamic-ID guidance
- add helper text explaining source names come from BirdNET (`nm`)

**Step 2: Fetch and store helper data in Settings page**

In `Settings.svelte`:
- fetch `fetchAudioSources()` on settings load (or when BirdNET section mounts)
- keep state for source options + loading/error
- pass source options to `IntegrationSettings.svelte`

**Step 3: Surface source options in `IntegrationSettings.svelte`**

UI behavior:
- show a compact “Recently detected BirdNET sources” list
- per camera row: keep text input, add optional quick-select (dropdown or buttons)
- selecting a helper option writes the source name into `cameraAudioMapping[camera]`
- optionally show sample current ID as secondary/debug text

**Step 4: Update non-English locale strings (minimum safe fallback)**

At minimum:
- add new keys in all locale files or keep old keys but update EN + fallback-safe usage
- avoid breaking missing-key lookups

**Step 5: Run UI checks**

Run:
```bash
cd YA-WAMF/apps/ui && npm run check
cd YA-WAMF/apps/ui && npm run build
```

Expected:
- PASS

**Step 6: Commit**

```bash
git add apps/ui/src/lib/components/settings/IntegrationSettings.svelte apps/ui/src/lib/pages/Settings.svelte apps/ui/src/lib/api.ts apps/ui/src/lib/i18n/locales/*.json
git commit -m "feat(ui): guide BirdNET mapping with source-name helper"
```

### Task 6: Manual Runtime Verification in Containers (Critical)

**Files:**
- Runtime only (logs/endpoints/UI)

**Step 1: Verify helper endpoint returns observed source names**

Run:
```bash
curl -sS http://yawamf-backend:8000/api/audio/sources | jq .
```

Expected:
- includes `BirdCam`
- includes `last_seen`
- may include sample current `src` value for debugging

**Step 2: Configure mapping to source name**

Set:
- `camera_audio_mapping["BirdCam"] = "BirdCam"`

Use UI or settings API.

**Step 3: Verify correlation before restart**

Confirm:
- recent visual detections can get audio correlation (when timing/species align)
- dashboard `audio_confirmations` becomes non-zero (if matching events present)

**Step 4: Restart BirdNET-Go**

Run:
```bash
docker restart birdnet-go
```

**Step 5: Reconfirm `src` changed but `nm` stable**

Capture:
```bash
docker exec mosquitto sh -lc 'mosquitto_sub -h localhost -u <user> -P <pass> -t "birdnet/#" -v -C 6'
```

Expected:
- ID-style field may rotate (`rtsp_*`)
- source name remains `BirdCam`

**Step 6: Verify mapping still works after restart**

Confirm:
- audio detections continue ingesting
- correlation still works with unchanged `BirdCam` mapping
- dashboard `audio_confirmations` continues to update for matching detections

**Step 7: Commit**

No commit (verification only).

### Task 7: Documentation and Changelog Update

**Files:**
- Modify: `CHANGELOG.md`
- Optional modify: `docs/` user-facing setup docs if BirdNET mapping instructions exist

**Step 1: Add changelog entry**

Mention:
- BirdNET camera mapping now uses source names (`nm`) instead of dynamic IDs
- helper list of recently observed BirdNET sources added
- users may need to update existing mappings

**Step 2: Update setup docs if BirdNET mapping instructions mention IDs or `*`**

Search:
```bash
rg -n "BirdNET|sensor ID|audio mapping|\\*" docs apps/ui/src/lib/i18n/locales/en.json
```

**Step 3: Run final checks**

Run:
```bash
cd YA-WAMF/backend && python -m pytest tests/test_audio_service.py -v
cd YA-WAMF/apps/ui && npm run check && npm run build
```

Expected:
- PASS

**Step 4: Commit**

```bash
git add CHANGELOG.md docs apps/ui/src/lib/i18n/locales/*.json
git commit -m "docs: document BirdNET source-name mapping change"
```

## Open Questions to Resolve During Implementation

- Should `/api/audio/sources` be DB-backed only, buffer-only, or merged?
- Should helper endpoint be owner-only or available under current guest/public rules?
- How many recent sources to retain/show by default (10/20)?
- Do we display sample dynamic ID (`src`) in the UI, or keep it backend/debug only?

## Verification Checklist

- [ ] `audio_service` stores `nm` / `Source.displayName` as canonical mapping key
- [ ] Existing unit tests updated for new semantics
- [ ] New tests cover name extraction precedence and fallback
- [ ] `/api/audio/sources` returns recent distinct source names
- [ ] Settings UI uses “source name” wording (not “sensor ID”)
- [ ] UI shows recently observed BirdNET source names and supports quick selection
- [ ] Mapping with `BirdCam` survives BirdNET-Go restart where `src` changes
- [ ] Dashboard `audio_confirmations` behavior verified with source-name mapping
- [ ] Changelog/docs updated

