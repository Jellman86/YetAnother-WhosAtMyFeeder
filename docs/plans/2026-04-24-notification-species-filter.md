# Notification Species Filter Mode Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a notification species filter mode selector with taxonomy-aware blacklist/whitelist picking.

**Architecture:** Add a `notifications_filter_species_mode` setting that makes one species filter list authoritative at a time: none, blacklist, or whitelist. Reuse the existing taxonomy-aware species search and `BlockedSpeciesEntry` object shape so notification filtering matches by `taxa_id`, scientific name, or common name rather than raw labels. Keep legacy raw whitelist support for compatibility.

**Tech Stack:** FastAPI/Pydantic backend settings models, YA-WAMF config loader, Svelte 5 settings UI, Vitest/frontend tests, pytest backend tests.

---

### Task 1: Backend Setting And Semantics

**Files:**
- Modify: `backend/app/config_models.py`
- Modify: `backend/app/config_loader.py`
- Modify: `backend/app/routers/settings.py`
- Modify: `backend/app/services/notification_service.py`
- Test: `backend/tests/test_notification_service.py`
- Test: `backend/tests/test_settings_api.py`

**Step 1: Write failing notification service tests**

Add tests covering:

```python
async def test_should_notify_none_mode_ignores_stale_structured_lists(notification_service):
    mock_settings.notifications.filters.species_mode = "none"
    mock_settings.notifications.filters.species_whitelist_structured = [{"taxa_id": 1, "common_name": "Robin"}]
    mock_settings.notifications.filters.species_blacklist_structured = [{"taxa_id": 2, "common_name": "Blue Jay"}]

    assert await notification_service._should_notify(
        "Robin", 0.9, False, "front", taxa_id=1, common_name="Robin"
    ) is True
    assert await notification_service._should_notify(
        "Blue Jay", 0.9, False, "front", taxa_id=2, common_name="Blue Jay"
    ) is True
```

```python
async def test_should_notify_blacklist_mode_ignores_stale_whitelist(notification_service):
    mock_settings.notifications.filters.species_mode = "blacklist"
    mock_settings.notifications.filters.species_whitelist_structured = [{"taxa_id": 1, "common_name": "Robin"}]
    mock_settings.notifications.filters.species_blacklist_structured = [{"taxa_id": 2, "common_name": "Blue Jay"}]

    assert await notification_service._should_notify(
        "Robin", 0.9, False, "front", taxa_id=1, common_name="Robin"
    ) is True
    assert await notification_service._should_notify(
        "Blue Jay", 0.9, False, "front", taxa_id=2, common_name="Blue Jay"
    ) is False
```

```python
async def test_should_notify_whitelist_mode_ignores_stale_blacklist(notification_service):
    mock_settings.notifications.filters.species_mode = "whitelist"
    mock_settings.notifications.filters.species_whitelist_structured = [{"taxa_id": 1, "common_name": "Robin"}]
    mock_settings.notifications.filters.species_blacklist_structured = [{"taxa_id": 2, "common_name": "Blue Jay"}]

    assert await notification_service._should_notify(
        "Robin", 0.9, False, "front", taxa_id=1, common_name="Robin"
    ) is True
    assert await notification_service._should_notify(
        "Blue Jay", 0.9, False, "front", taxa_id=2, common_name="Blue Jay"
    ) is False
```

Keep the existing legacy whitelist test passing when `species_mode` is absent or defaulted from legacy data.

**Step 2: Run tests to verify failure**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_notification_service.py -q
```

Expected: new tests fail because `species_mode` does not exist or is ignored.

**Step 3: Add backend model/config fields**

In `backend/app/config_models.py`, add a literal-style string field to notification filters:

```python
species_mode: str = Field(
    default="none",
    description="Species notification filter mode: none, blacklist, or whitelist",
)
```

Add a validator that only accepts `none`, `blacklist`, or `whitelist`.

In `backend/app/config_loader.py`, add default config:

```python
'species_mode': 'none',
```

In `backend/app/routers/settings.py`, add:

```python
notifications_filter_species_mode: Optional[str] = None
```

Include it in GET settings payload and apply it on PUT after validation.

**Step 4: Implement service semantics**

In `backend/app/services/notification_service.py`, read:

```python
species_mode = getattr(filters, "species_mode", None)
if species_mode not in {"none", "blacklist", "whitelist"}:
    species_mode = "whitelist" if filters.species_whitelist else "none"
```

Then:

- only evaluate structured blacklist when `species_mode == "blacklist"`
- only evaluate structured whitelist when `species_mode == "whitelist"`
- preserve legacy raw whitelist behavior when mode is absent/legacy and `filters.species_whitelist` has values

**Step 5: Add settings API test**

Extend `backend/tests/test_settings_api.py` to assert `notifications_filter_species_mode` round-trips with structured blacklist and whitelist arrays.

**Step 6: Run focused backend tests**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_notification_service.py backend/tests/test_settings_api.py -q
```

Expected: PASS.

**Step 7: Commit backend task**

```bash
git add backend/app/config_models.py backend/app/config_loader.py backend/app/routers/settings.py backend/app/services/notification_service.py backend/tests/test_notification_service.py backend/tests/test_settings_api.py
git commit -m "feat(notifications): add species filter mode"
```

### Task 2: Shared Species Filter Helper

**Files:**
- Modify or move: `apps/ui/src/lib/settings/blocked-species.ts`
- Modify: `apps/ui/src/lib/settings/blocked-species.test.ts`
- Modify: `apps/ui/src/lib/api/settings.ts`

**Step 1: Write or update helper tests**

Add tests that prove `BlockedSpeciesEntry` helpers are neutral enough for notification filters:

```typescript
it('formats taxonomy filter entries with common and scientific names', () => {
    expect(formatBlockedSpeciesLabel({
        common_name: 'House Sparrow',
        scientific_name: 'Passer domesticus',
        taxa_id: 123
    })).toBe('House Sparrow (Passer domesticus)');
});
```

If renaming the helper file, keep re-export compatibility from `blocked-species.ts` to avoid broad churn.

**Step 2: Run helper tests**

Run:

```bash
npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/settings/blocked-species.test.ts
```

Expected: PASS after any rename/re-export adjustments.

**Step 3: Update settings API type**

Add:

```typescript
notifications_filter_species_mode?: 'none' | 'blacklist' | 'whitelist';
```

to the settings response/update type in `apps/ui/src/lib/api/settings.ts`.

**Step 4: Commit helper task**

```bash
git add apps/ui/src/lib/settings/blocked-species.ts apps/ui/src/lib/settings/blocked-species.test.ts apps/ui/src/lib/api/settings.ts
git commit -m "refactor(ui): share taxonomy species filter helpers"
```

### Task 3: Notification Settings UI

**Files:**
- Modify: `apps/ui/src/lib/pages/Settings.svelte`
- Modify: `apps/ui/src/lib/components/settings/NotificationSettings.svelte`
- Modify: `apps/ui/src/lib/i18n/locales/en.json`
- Test: add or modify relevant frontend settings tests if present

**Step 1: Add UI state in Settings.svelte**

Add:

```typescript
let filterSpeciesMode = $state<'none' | 'blacklist' | 'whitelist'>('none');
let filterSpeciesEntries = $state<BlockedSpeciesEntry[]>([]);
```

On settings load:

```typescript
filterSpeciesMode = settings.notifications_filter_species_mode ?? inferNotificationSpeciesMode(settings);
filterSpeciesEntries = filterSpeciesMode === 'blacklist'
    ? settings.notifications_filter_species_blacklist_structured || []
    : filterSpeciesMode === 'whitelist'
        ? settings.notifications_filter_species_whitelist_structured || []
        : [];
```

On save:

```typescript
notifications_filter_species_mode: filterSpeciesMode,
notifications_filter_species_whitelist_structured: filterSpeciesMode === 'whitelist' ? filterSpeciesEntries : [],
notifications_filter_species_blacklist_structured: filterSpeciesMode === 'blacklist' ? filterSpeciesEntries : [],
```

**Step 2: Update NotificationSettings props**

Replace the raw whitelist-only prop shape with:

```typescript
filterSpeciesMode: 'none' | 'blacklist' | 'whitelist';
filterSpeciesEntries: BlockedSpeciesEntry[];
```

Keep legacy raw whitelist rendering only as a small compatibility section if unresolved raw labels still exist.

**Step 3: Add radio group**

Add three radio choices:

- No species filter
- Block selected species
- Only selected species

When `filterSpeciesMode !== 'none'`, show the taxonomy search picker. Use `/api/species/search` with `hydrate_missing=true`, `buildBlockedSpeciesEntry`, `mergeBlockedSpeciesEntries`, and `formatBlockedSpeciesLabel`.

**Step 4: Add English locale strings**

Add keys under `settings.notifications`:

```json
"species_filter": "Species filter",
"species_filter_none": "No species filter",
"species_filter_none_desc": "Notify for all species that pass the other filters.",
"species_filter_blacklist": "Block selected species",
"species_filter_blacklist_desc": "Notify for everything except the species below.",
"species_filter_whitelist": "Only selected species",
"species_filter_whitelist_desc": "Notify only for the species below.",
"species_filter_blacklist_list": "Do not notify for these species",
"species_filter_whitelist_list": "Only notify for these species",
"species_filter_search_placeholder": "Search birds by common or scientific name",
"species_filter_no_results": "No matching birds found.",
"species_filter_legacy": "Legacy raw labels"
```

**Step 5: Run frontend checks/tests**

Run:

```bash
npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/settings/blocked-species.test.ts
npm --prefix /config/workspace/YA-WAMF/apps/ui run check
```

Expected: PASS.

**Step 6: Commit UI task**

```bash
git add apps/ui/src/lib/pages/Settings.svelte apps/ui/src/lib/components/settings/NotificationSettings.svelte apps/ui/src/lib/i18n/locales/en.json apps/ui/src/lib/api/settings.ts apps/ui/src/lib/settings/blocked-species.ts apps/ui/src/lib/settings/blocked-species.test.ts
git commit -m "feat(ui): add notification species filter picker"
```

### Task 4: Changelog And Issue Update

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Add changelog entry**

Under `## [Unreleased]`, add:

```markdown
- **Notifications (#48):** Settings now expose a species filter mode with "No species filter", "Block selected species", and "Only selected species" options. The filter uses the taxonomy-aware species picker so users can select birds by common name, scientific name, or taxonomy ID instead of maintaining raw text labels.
```

**Step 2: Run final focused verification**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_notification_service.py backend/tests/test_settings_api.py -q
npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/settings/blocked-species.test.ts
npm --prefix /config/workspace/YA-WAMF/apps/ui run check
```

Expected: PASS.

**Step 3: Commit changelog**

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): note notification species filter mode"
```

**Step 4: Prepare GitHub issue comment**

Only after implementation is pushed to `dev`, post a short comment to issue `#48` using `agents/GITHUB_API_WORKFLOW.md`:

```markdown
Implemented on `dev`: notification settings now have a species filter mode with:

- No species filter
- Block selected species
- Only selected species

The picker uses taxonomy-aware search, so selections match by common name, scientific name, and taxonomy ID rather than raw text labels.

Please test with `ghcr.io/jellman86/yawamf-monalithic:dev`.
```

Read the comment back after posting.
