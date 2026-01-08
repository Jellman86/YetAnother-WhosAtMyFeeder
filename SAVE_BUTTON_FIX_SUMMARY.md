# Save Button Fix - Summary

## Issue Found ✅
The "Apply Settings" button is not appearing because the settings API request is being cancelled due to a race condition.

## Root Cause
**File:** `apps/ui/src/lib/api.ts` (line 447-450)

The `fetchSettings()` function uses an abort mechanism that cancels duplicate requests:
```typescript
export async function fetchSettings(): Promise<Settings> {
    // Settings are global, cancel any pending fetch
    return fetchWithAbort<Settings>('settings', `${API_BASE}/settings`);
}
```

**Problem:** Two calls happen simultaneously:
1. `loadSettings()` in Settings.svelte calls `fetchSettings()`
2. `settingsStore.load()` also calls `fetchSettings()`

Both use the same abort key `"settings"`, so they cancel each other. This results in:
- Console log: "Request cancelled: settings"
- `settingsStore.settings` remains `null`
- `isDirty` returns `false` (because it checks `if (!s) return false;`)
- Save button never appears

## Fix Applied ✅
**File:** `apps/ui/src/lib/api.ts`

Changed `fetchSettings()` to use regular fetch without abort mechanism:

```typescript
export async function fetchSettings(): Promise<Settings> {
    // Don't use abort mechanism to avoid race conditions between
    // loadSettings() and settingsStore.load() that cancel each other
    const response = await apiFetch(`${API_BASE}/settings`);
    return handleResponse<Settings>(response);
}
```

## Next Steps

### 1. Commit and Push Changes
```bash
cd /config/workspace/YA-WAMF
git add apps/ui/src/lib/api.ts
git commit -m "Fix: Remove abort mechanism from fetchSettings to prevent race condition

The settings API request was being cancelled due to competing calls from
loadSettings() and settingsStore.load() using the same abort key. This
caused settingsStore.settings to remain null, making isDirty always return
false, which hid the save button.

Fixes: Save button not appearing in Settings UI"

git push
```

### 2. Wait for GitHub Actions
- GitHub Actions will build the new frontend image
- Once complete, pull and restart the container

### 3. Test the Fix
After the new image is deployed:

1. Navigate to https://yawamf.pownet.uk/settings
2. Open browser console (F12)
3. You should see: `Calculating isDirty` logs
4. Modify any setting (e.g., change classification threshold)
5. You should see: `Dirty Setting: [field]` log
6. Save button should appear at bottom center with "Apply Settings" label

### 4. Verify with Test Suite
```bash
cd /config/workspace/YA-WAMF
python3 tests/e2e/test_console_logs.py
```

Expected output:
- ✅ Console logs show "Calculating isDirty"
- ✅ settingsStore.settings is loaded
- ✅ No "Request cancelled" messages
- ✅ Save button appears after modifying settings

## Technical Details

### Why This Fix Works
- Removes the abort mechanism that was cancelling requests
- Both `loadSettings()` and `settingsStore.load()` can call `fetchSettings()` without interference
- `settingsStore` still has deduplication via `_loadPromise` (line 11 in settings.svelte.ts)
- Settings load successfully and `isDirty` can properly detect changes

### Alternative Considered
We could have refactored Settings.svelte to only use `settingsStore.load()`, but removing the abort mechanism is simpler and fixes the immediate issue without changing component logic.

## Files Changed
- ✅ `apps/ui/src/lib/api.ts` - Fixed fetchSettings() race condition

## Testing Artifacts
Available in `/config/workspace/`:
- `save_button_missing.png` - Screenshot showing missing button (before fix)
- `console_test.png` - Console log test output
- `SETTINGS_BUTTON_DIAGNOSIS.md` - Detailed diagnostic report
- `FIX_SAVE_BUTTON.patch` - Detailed patch documentation
