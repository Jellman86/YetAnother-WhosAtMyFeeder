import { test, expect, type Page } from '@playwright/test';
import { openDetectionSettings, type RangeMock } from './detection-settings-mock';

// The range filter card in Settings → Detection (#696): every state names what the filter is
// doing in words, never claims to filter when it is not, and points at the one next step.

const card = (page: Page) => page.locator('[data-range-filter]');
const panel = (page: Page) => page.locator('[data-range-filter-status]');
const daysAgo = (days: number) => new Date(Date.now() - days * 86_400_000 - 60_000).toISOString();

const KENT = { code: 'GB-ENG-KEN', codes: ['GB-ENG-KEN'], name: 'Kent, England, GB', level: 'county', note: null };
const ready = {
    reason: 'ready', ebird_configured: true, region: KENT, species_in_range: 412, region_species_total: 415,
    refreshed_at: daysAgo(2), model: { bird_species: 1486, out_of_range: 803, unmatched: 0 }
};

async function open(page: Page, range: RangeMock) {
    const state = await openDetectionSettings(page, { range });
    await expect(card(page)).toBeVisible();
    await card(page).scrollIntoViewIfNeeded();
    return state;
}

test('an active filter states its list, source and freshness in words', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    await open(page, { status: { ...ready, enabled: true, filtering: true, reason: 'active', heard_species: 3 } });

    await expect(panel(page)).toHaveAttribute('data-state', 'active');
    await expect(panel(page)).toContainText('Filtering');
    await expect(panel(page)).toContainText('Filtering to 412 species recorded in Kent, England, GB (eBird, refreshed 2 days ago).');
    await expect(card(page).locator('[data-range-filter-region]')).toContainText('Kent, England, GB');
    await expect(card(page).locator('[data-range-filter-region]')).toContainText('County');
    await expect(card(page)).toContainText('eBird regional species list');
    await expect(card(page).locator('[data-range-filter-heard]')).toContainText('3 species BirdNET-Go heard here in the last year also count as present.');
    await expect(card(page).getByRole('button', { name: 'Refresh list' })).toBeEnabled();
    await expect(card(page)).toContainText('so a summer visitor counts as present all year');
    expect(errors).toEqual([]);
});

test('before it is switched on, the preview shows what would be set aside and the switch saves with the form', async ({ page }) => {
    const state = await open(page, {
        status: ready,
        preview: {
            available: true, window_days: 90, model_out_of_range_total: 803,
            recently_seen: [{ species_id: 4, scientific_name: 'Turdus merula', common_name: 'Eurasian Blackbird', detections: 6, last_seen: daysAgo(1) }],
            examples: [{ species_id: 9, scientific_name: 'Cardinalis cardinalis', common_name: 'Northern Cardinal' }]
        }
    });

    await expect(panel(page)).toContainText('Off. Turning it on would filter to 412 species recorded in Kent, England, GB.');
    const preview = card(page).locator('[data-range-filter-preview]');
    await expect(preview).toContainText('Recorded here in the last 90 days');
    await expect(preview.locator('[data-range-filter-preview-seen]')).toContainText('Eurasian Blackbird');
    await expect(preview.locator('[data-range-filter-preview-seen]')).toContainText('6 detections');
    await expect(preview.locator('[data-range-filter-preview-total]')).toContainText('The current model can name 803 species');
    await expect(preview).toContainText('Northern Cardinal');
    await expect(card(page)).toContainText('its next answer that has been recorded');

    const toggle = card(page).getByRole('switch', { name: 'Check new detections against your region' });
    await toggle.click();
    await expect(toggle).toHaveAttribute('aria-checked', 'true');
    await expect(card(page).locator('[data-range-filter-unsaved]')).toHaveText('Apply settings to turn the filter on.');
    await page.getByRole('button', { name: 'Apply Settings', exact: true }).click();
    await expect.poll(() => state.saves.length).toBe(1);
    expect(state.saves[0].range_filter_enabled).toBe(true);
    expect(state.saves[0].range_filter_region_level).toBe('county');
});

test('with no location the switch is disabled with the reason and a way to set one', async ({ page }) => {
    await open(page, { status: { reason: 'needs_location', location_precision: 'none' } });

    await expect(panel(page)).toContainText('Off: needs your location.');
    const toggle = card(page).getByRole('switch', { name: 'Check new detections against your region' });
    await expect(toggle).toHaveAttribute('aria-disabled', 'true');
    await expect(card(page)).toContainText('Set a location first.');
    await expect(card(page).locator('[data-range-filter-facts]')).toHaveCount(0);
    await card(page).getByRole('button', { name: 'Set location' }).click();
    await expect(page.locator('[data-fixture-route]')).toHaveAttribute('data-fixture-route', '/settings/integrations');
    // With an automatic location the coordinates are hidden, so the Manual choice that reveals them takes focus.
    await expect(page.locator('#location-lat').or(page.locator('#setting-location-mode + div button[aria-pressed="false"]'))).toBeFocused();
});

test('without an eBird key it names the missing key and that BirdNET-Go alone never filters', async ({ page }) => {
    await open(page, { status: { reason: 'needs_ebird_key', enabled: true } });

    await expect(panel(page)).toContainText('Not filtering');
    await expect(panel(page)).toContainText('Add an eBird API key to use range filtering.');
    await expect(panel(page)).toContainText('on its own it filters nothing');
    await expect(panel(page)).toHaveClass(/attention/);
    await card(page).getByRole('button', { name: 'Add eBird key' }).click();
    await expect(page.locator('[data-fixture-route]')).toHaveAttribute('data-fixture-route', '/settings/integrations');
    // eBird is off in this fixture, so its switch, the step that reveals the key field, takes focus.
    await expect(page.locator('[aria-labelledby="setting-ebird-enabled"]')).toBeFocused();
});

test('an approximate location says a state list is used, and a country alone says so too', async ({ page }) => {
    await open(page, {
        status: { ...ready, location_precision: 'approximate', region: { ...KENT, code: 'GB-ENG', codes: ['GB-ENG'], name: 'England, GB', level: 'state' } }
    });
    await expect(card(page)).toContainText('Your location is approximate, so a state list is used rather than a county.');
    await expect(card(page).locator('[data-range-filter-region]')).toContainText('State or province');

    await page.unrouteAll({ behavior: 'ignoreErrors' });
    await open(page, {
        status: { ...ready, location_precision: 'country_only', region: { ...KENT, code: 'GB', codes: ['GB'], name: 'United Kingdom', level: 'country' } }
    });
    await expect(card(page)).toContainText('Only a country is set, so the country list is used.');
});

test('a failed lookup stays open and says why', async ({ page }) => {
    await open(page, { status: { reason: 'lookup_failed', enabled: true, ebird_configured: true, problem: 'ebird_unreachable', last_error: 'ebird_unreachable' } });

    await expect(panel(page)).toHaveAttribute('data-state', 'lookup_failed');
    await expect(panel(page)).toContainText('Not filtering: the eBird list could not be fetched. eBird could not be reached.');
    await expect(panel(page)).toContainText('Nothing is filtered until a list is fetched.');
    await expect(card(page).getByRole('button', { name: 'Fetch list' })).toBeVisible();
});

test('a stale list stops filtering and says how old it is', async ({ page }) => {
    await open(page, { status: { ...ready, enabled: true, reason: 'list_stale', refreshed_at: daysAgo(34) } });

    await expect(panel(page)).toContainText('Not filtering: the list was fetched 34 days ago. A list older than 30 days is not trusted.');
});

test('an empty or unmatched list is refused and named', async ({ page }) => {
    await open(page, { status: { ...ready, enabled: true, reason: 'list_unusable', problem: 'poorly_mapped' } });

    await expect(panel(page)).toContainText('Not filtering: the stored list failed its checks. The list was empty or could not be matched to known species.');
});

test('labels the model cannot match to eBird are counted as never filtered', async ({ page }) => {
    await open(page, { status: { ...ready, model: { bird_species: 1486, out_of_range: 803, unmatched: 212 } } });

    await expect(card(page).locator('[data-range-filter-unmatched]')).toHaveText('212 model labels could not be matched to eBird and are never filtered.');
});

test('fetching the first list shows progress and then the region', async ({ page }) => {
    const state = await open(page, {
        status: { reason: 'waiting_for_list', ebird_configured: true },
        afterRefresh: ready
    });

    await expect(panel(page)).toContainText('No regional list yet. Fetch it to see the effect before turning the filter on.');
    await card(page).getByRole('button', { name: 'Fetch list' }).click();
    await expect.poll(() => state.rangeRefreshes).toBe(1);
    await expect(panel(page)).toContainText('Off. Turning it on would filter to 412 species recorded in Kent, England, GB.', { timeout: 10_000 });
});

test('a preview that cannot load says so without hiding the status', async ({ page }) => {
    await open(page, { status: ready, previewFails: true });

    await expect(card(page).locator('[data-range-filter-preview]')).toContainText('The preview could not be loaded.');
    await expect(panel(page)).toContainText('Off. Turning it on would filter');
});

test('detections set aside are listed with a way to the activity log and to record one by hand', async ({ page }) => {
    await open(page, {
        status: { ...ready, enabled: true, filtering: true, reason: 'active' },
        skips: [{ frigate_event: 'evt-1', camera: 'feeder', detected_at: daysAgo(1), decided_at: daysAgo(1), label: 'Turdus merula', score: 0.91, region_code: 'GB-ENG-KEN' }]
    });

    const skips = card(page).locator('[data-range-filter-skips]');
    await expect(skips).toContainText('Turdus merula');
    await expect(skips).toContainText('91% confidence');
    await expect(skips).toContainText('record it by hand');
    await skips.getByRole('button', { name: 'Open the activity log' }).click();
    await expect(page.locator('[data-fixture-route]')).toHaveAttribute('data-fixture-route', '/settings/health');
});

test('with nothing set aside the list says so', async ({ page }) => {
    await open(page, { status: { ...ready, enabled: true, filtering: true, reason: 'active' } });

    await expect(card(page).locator('[data-range-filter-skips]')).toContainText('Nothing has been set aside as outside the range.');
});
