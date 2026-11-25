import { expect, test, type Page } from '@playwright/test';
import { replayFeeder, settled } from './accessibility-mock';

/**
 * The Leaderboard and Audio history use the space each device gives them: on a phone the controls
 * are compact and the filters wait in a sheet; on a desktop secondary figures stand in a side column
 * and charts take the full width; at no width does the page scroll sideways. Every chart carries its
 * data as a table, and the wall's preview stays inside the page's main landmark.
 */
const READY = { timeout: 15_000 };
const WIDTHS = [
    { width: 390, height: 844 },
    { width: 768, height: 1024 },
    { width: 1024, height: 768 },
    { width: 1440, height: 900 },
    { width: 1920, height: 1080 }
];

async function open(page: Page, path: string, ready: string, size: { width: number; height: number }): Promise<void> {
    await page.setViewportSize(size);
    await replayFeeder(page, 'light');
    await page.goto(path);
    await expect(page.locator(ready).first()).toBeVisible(READY);
    await settled(page);
}

for (const size of WIDTHS) {
    for (const [name, path, ready] of [['the Leaderboard', '/species', '[data-leaderboard-species-portrait]'], ['Audio history', '/audio', '[data-audio-top-species-button]']] as const) {
        test(`${name} does not scroll sideways at ${size.width} px`, async ({ page }) => {
            await open(page, path, ready, size);
            expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(0);
        });
    }
}

test('on a phone the Leaderboard controls are one compact row, with the rarer choice under More', async ({ page }) => {
    await open(page, '/species', '[data-leaderboard-species-portrait]', WIDTHS[0]);
    const controls = page.locator('[data-leaderboard-controls]');
    await expect(page.locator('[data-leaderboard-span-select]')).toBeVisible();
    await expect(page.locator('[data-leaderboard-span-bar]')).toBeHidden();
    await expect(controls.getByRole('checkbox', { name: 'Include Unknown bird' })).toBeHidden();
    expect((await controls.boundingBox())?.height ?? Infinity).toBeLessThan(140);
    await page.locator('[data-leaderboard-more-controls] summary').click();
    await expect(controls.getByRole('checkbox', { name: 'Include Unknown bird' })).toBeVisible();
    await page.locator('[data-leaderboard-span-select]').selectOption('week');
    await expect(page.locator('[data-leaderboard-analytics-window]')).toContainText('Last 7 days');
});

test('at 1440 px the standing figures sit beside the wall, and the rankings table and charts take the full width', async ({ page }) => {
    await open(page, '/species', '[data-leaderboard-species-portrait]', WIDTHS[3]);
    const wall = await page.locator('[data-capture-wall]').boundingBox();
    const side = await page.locator('[data-leaderboard-side]').boundingBox();
    expect(wall && side && side.x > wall.x + wall.width - 1).toBe(true);
    // The ranking is a table at this width, and it and the charts reach the side column's far edge.
    await expect(page.locator('[data-leaderboard-table-rankings]')).toBeVisible();
    for (const selector of ['[data-leaderboard-rankings]', '[data-leaderboard-analytics]']) {
        const box = await page.locator(selector).boundingBox();
        expect(box && side && box.x + box.width >= side.x + side.width - 1, selector).toBe(true);
    }
});

test('every Leaderboard chart has its data as a table', async ({ page }) => {
    await open(page, '/species', '[data-leaderboard-species-portrait]', WIDTHS[3]);
    const figures = page.locator('[data-leaderboard-analytics] figure');
    await expect(figures).toHaveCount(3);
    for (const figure of await figures.all()) {
        await figure.scrollIntoViewIfNeeded();
        await figure.locator('summary').filter({ hasText: 'Show the data as a table' }).click();
        await expect(figure.locator('table tbody tr').first()).toBeVisible();
        expect(await figure.locator('table th[scope="row"]').count()).toBeGreaterThan(0);
    }
});

test('the wall\'s preview opens inside the main landmark', async ({ page }) => {
    await open(page, '/species', '[data-capture-wall]', WIDTHS[3]);
    const tile = page.locator('[data-capture-wall] [data-capture-wall-tile]').first();
    await tile.scrollIntoViewIfNeeded();
    await tile.hover();
    const popout = page.locator('[data-capture-wall-popout]');
    await expect(popout).toBeVisible();
    expect(await popout.evaluate((node) => Boolean(node.closest('main')))).toBe(true);
});

test('on a phone Audio history puts the window\'s figures before the log and its filters in a sheet', async ({ page }) => {
    await open(page, '/audio', '[data-audio-top-species-button]', WIDTHS[0]);
    await expect(page.locator('[data-audio-history-filters] form')).toBeHidden();
    const opener = page.locator('[data-audio-filters-open]');
    await expect(opener).toBeVisible();
    // How the window stands is read first, as on the Leaderboard: in the page and on screen, the
    // figures come before the first call, and they are drawn once.
    const figures = page.locator('[data-audio-history-summary]');
    await expect(figures).toHaveCount(1);
    const firstCall = page.locator('[data-audio-history-table] tbody tr').first();
    await expect(firstCall).toBeVisible();
    expect(await figures.evaluate((node) => {
        const call = document.querySelector('[data-audio-history-table] tbody tr');
        return Boolean(call && node.compareDocumentPosition(call) & Node.DOCUMENT_POSITION_FOLLOWING);
    })).toBe(true);
    const [figuresBox, callBox] = await Promise.all([figures.boundingBox(), firstCall.boundingBox()]);
    expect(figuresBox && callBox && figuresBox.y + figuresBox.height <= callBox.y).toBe(true);
    // The species and sources still follow the log, and their landmark has its own name.
    await expect(page.getByRole('complementary', { name: 'Most heard species and sources' })).toHaveCount(1);
    await opener.click();
    const sheet = page.getByRole('dialog', { name: 'Filters' });
    await expect(sheet).toBeVisible();
    await expect(sheet.getByRole('slider')).toHaveAttribute('aria-valuetext', /%$/);
    // Focus moves into the sheet, as a modal's does, so Escape is the sheet's to take.
    await expect.poll(() => page.evaluate(() => Boolean(document.activeElement?.closest('[role="dialog"]')))).toBe(true);
    await page.keyboard.press('Escape');
    await expect(sheet).toBeHidden();
    await expect(opener).toBeFocused();
});

test('at 1440 px Audio history keeps the log in the main column with the figures, then species and sources, beside it', async ({ page }) => {
    await open(page, '/audio', '[data-audio-top-species-button]', WIDTHS[3]);
    const [log, figures, side] = await Promise.all(
        ['[data-audio-history-log]', '[data-audio-history-summary]', '[data-audio-history-side]'].map((selector) => page.locator(selector).boundingBox())
    );
    expect(log && figures && side).toBeTruthy();
    if (!log || !figures || !side) return;
    // The figures sit at the head of the right-hand column, level with the log's top.
    expect(figures.x).toBeGreaterThan(log.x + log.width - 1);
    expect(Math.abs(figures.y - log.y)).toBeLessThanOrEqual(1);
    // Species and sources follow directly under them in the same column, 2rem apart as before: the
    // log's height opens no gap under the figures.
    expect(Math.abs(side.x - figures.x)).toBeLessThanOrEqual(1);
    expect(Math.abs(side.width - figures.width)).toBeLessThanOrEqual(1);
    const twoRem = await page.evaluate(() => 2 * parseFloat(getComputedStyle(document.documentElement).fontSize));
    expect(Math.abs(side.y - (figures.y + figures.height) - twoRem)).toBeLessThanOrEqual(1);
});

test('every Audio history chart has its data as a table', async ({ page }) => {
    await open(page, '/audio', '[data-audio-top-species-button]', WIDTHS[3]);
    const figures = page.locator('[data-audio-history-analytics] figure');
    await expect(figures).toHaveCount(3);
    for (const figure of await figures.all()) {
        await figure.scrollIntoViewIfNeeded();
        await figure.locator('summary').filter({ hasText: 'Show the data as a table' }).click();
        await expect(figure.locator('table tbody tr').first()).toBeVisible();
    }
});

test('the Audio filter sheet goes with the phone width, and lets the page scroll again', async ({ page }) => {
    await open(page, '/audio', '[data-audio-top-species-button]', WIDTHS[0]);
    await page.locator('[data-audio-filters-open]').click();
    const sheet = page.getByRole('dialog', { name: 'Filters' });
    await expect(sheet).toBeVisible();
    await sheet.getByPlaceholder('Any species').fill('Robin');
    await expect.poll(() => page.evaluate(() => document.body.style.position)).toBe('fixed');
    // A tablet turned to landscape: the fields now stand inline, so the modal and its lock go.
    await page.setViewportSize(WIDTHS[1]);
    await expect(sheet).toHaveCount(0);
    await expect.poll(() => page.evaluate(() => document.body.style.position)).toBe('');
    // The draft is kept in the inline form, beside the Apply it needs.
    const inline = page.locator('[data-audio-history-filters] form');
    await expect(inline.getByPlaceholder('Any species')).toHaveValue('Robin');
    await expect(page.locator('[data-audio-filters-changed]')).toContainText('Apply');
    await expect(inline.getByRole('button', { name: 'Apply' })).toBeVisible();
});

test('leaving the Audio filter sheet without Apply puts the fields back to what the list shows', async ({ page }) => {
    await open(page, '/audio', '[data-audio-top-species-button]', WIDTHS[0]);
    const opener = page.locator('[data-audio-filters-open]');
    await opener.click();
    const sheet = page.getByRole('dialog', { name: 'Filters' });
    await sheet.getByPlaceholder('Any species').fill('Robin');
    await expect.poll(() => page.evaluate(() => Boolean(document.activeElement?.closest('[role="dialog"]')))).toBe(true);
    await page.keyboard.press('Escape');
    await expect(sheet).toHaveCount(0);
    // Nothing waits on an Apply the reader can no longer see.
    await expect(page.locator('[data-audio-filters-changed]')).toHaveText('');
    await opener.click();
    await expect(page.getByRole('dialog', { name: 'Filters' }).getByPlaceholder('Any species')).toHaveValue('');
});


test('the Leaderboard names one window: the wall says the same span and dates as the rankings', async ({ page }) => {
    await open(page, '/species', '[data-leaderboard-species-portrait]', WIDTHS[3]);
    const rankings = (await page.locator('[data-leaderboard-rankings-window]').textContent())?.trim() ?? '';
    expect(rankings).toMatch(/·/);
    const eyebrow = (await page.locator('[data-capture-wall] header p').first().textContent())?.trim() ?? '';
    expect(eyebrow).toContain(rankings);
    expect(rankings).toMatch(/^Last 30 days · /);
    // The period has one name: the old "Month" label must not sit beside "Last 30 days".
    await expect(page.locator('main')).not.toContainText(/\bMonth\b/);
});

test('Audio history offers icon hide/restore, hidden view, multi-select bulk actions, and search', async ({ page }) => {
    const calls = [
        { id: 101, timestamp: '2026-11-23T08:05:00Z', species: 'European Robin', confidence: 0.94, sensor_id: 'garden-mic', source_name: 'Garden Mic', birdnet_id: 1, matched_visual_event_id: null, hidden: false },
        { id: 102, timestamp: '2026-11-23T08:03:00Z', species: 'Eurasian Wren', confidence: 0.87, sensor_id: 'patio-mic', source_name: 'Patio Mic', birdnet_id: 2, matched_visual_event_id: null, hidden: false },
        { id: 103, timestamp: '2026-11-23T08:01:00Z', species: 'Blue Tit', confidence: 0.91, sensor_id: 'shed-mic', source_name: 'Shed Mic', birdnet_id: 3, matched_visual_event_id: null, hidden: true }
    ];
    const bulkPayloads: Array<{ ids: number[]; hidden: boolean }> = [];

    await replayFeeder(page, 'light');
    await page.route((url) => url.pathname.startsWith('/api/audio/'), async (route) => {
        const url = new URL(route.request().url());
        const method = route.request().method();
        if (url.pathname === '/api/audio/history/hidden-count') {
            return route.fulfill({ json: { hidden_count: calls.filter((item) => item.hidden).length } });
        }
        if (url.pathname === '/api/audio/history/visibility' && method === 'PATCH') {
            const body = route.request().postDataJSON() as { ids: number[]; hidden: boolean };
            bulkPayloads.push(body);
            for (const item of calls) {
                if (body.ids.includes(item.id)) item.hidden = body.hidden;
            }
            return route.fulfill({ json: { updated_count: body.ids.length, ids: body.ids, hidden: body.hidden } });
        }
        if (url.pathname.startsWith('/api/audio/history/') && method === 'PATCH') {
            const id = Number(url.pathname.split('/').pop());
            const body = route.request().postDataJSON() as { hidden: boolean };
            const found = calls.find((item) => item.id === id);
            if (found) found.hidden = body.hidden;
            return route.fulfill({ json: { id, hidden: body.hidden } });
        }
        if (url.pathname === '/api/audio/history') {
            const onlyHidden = url.searchParams.get('only_hidden') === 'true';
            const q = (url.searchParams.get('search') ?? '').trim().toLowerCase();
            const matching = calls.filter((item) => {
                if (item.hidden !== onlyHidden) return false;
                if (!q) return true;
                return item.species.toLowerCase().includes(q) || (item.source_name ?? '').toLowerCase().includes(q);
            });
            return route.fulfill({ json: { items: matching, total: matching.length, limit: 25, offset: 0 } });
        }
        if (url.pathname === '/api/audio/summary') {
            const onlyHidden = url.searchParams.get('only_hidden') === 'true';
            const matching = calls.filter((item) => item.hidden === onlyHidden);
            return route.fulfill({
                json: {
                    total: matching.length,
                    species_count: matching.length,
                    source_count: matching.length,
                    top_species: matching.map((item) => ({
                        species: item.species,
                        scientific_name: item.species,
                        count: 1,
                        avg_confidence: item.confidence,
                        max_confidence: item.confidence,
                        first_heard: item.timestamp,
                        last_heard: item.timestamp
                    })),
                    daily_counts: [{ date: '2026-11-23', count: matching.length }],
                    hourly_counts: [{ hour: 8, count: matching.length }],
                    sources: matching.map((item) => ({ source_name: item.source_name, count: 1, last_heard: item.timestamp }))
                }
            });
        }
        if (url.pathname === '/api/audio/activity-heatmap') {
            return route.fulfill({
                json: {
                    window_start: '2026-11-01T00:00:00Z',
                    window_end: '2026-11-23T15:00:00Z',
                    total_count: 1,
                    max_cell_count: 1,
                    cells: [{ day_of_week: 1, hour: 8, count: 1 }]
                }
            });
        }
        return route.fallback();
    });

    await page.setViewportSize(WIDTHS[3]);
    await page.goto('/audio');
    await expect(page.locator('[data-audio-history-table] tbody tr')).toHaveCount(2, READY);

    // Compact eye-slash icon button replaces verbose text label.
    const hideBtn = page.locator('[data-audio-visibility-toggle]').first();
    await expect(hideBtn).toHaveAccessibleName('Hide from YA-WAMF');
    expect((await hideBtn.textContent())?.trim()).toBe('');

    // Hidden toggle shows the current hidden count badge.
    await expect(page.locator('[data-audio-hidden-count]')).toHaveText('1');

    // Quick search filters calls by source or species.
    const search = page.locator('[data-audio-search-input]');
    await search.fill('Patio');
    await search.press('Enter');
    await expect(page.locator('[data-audio-history-table] tbody tr')).toHaveCount(1);
    await expect(page.locator('[data-audio-history-table]')).toContainText('Eurasian Wren');
    await page.locator('[data-audio-search-clear]').click();
    await expect(page.locator('[data-audio-history-table] tbody tr')).toHaveCount(2);

    // Multi-select bulk hides selected calls and offers Undo.
    await page.locator('[data-audio-multiselect-toggle]').click();
    await expect(page.locator('[data-audio-selection-bar]')).toBeVisible();
    await page.locator('[data-audio-select-all]').click();
    await expect(page.locator('[data-audio-selection-count]')).toHaveText('2 calls selected');
    await page.locator('[data-audio-bulk-visibility]').click();
    await expect.poll(() => bulkPayloads.length).toBe(1);
    expect(bulkPayloads[0]).toEqual({ ids: [101, 102], hidden: true });
    await expect(page.locator('[data-audio-hidden-count]')).toHaveText('3');
    await expect(page.locator('[data-audio-visibility-status]')).toContainText('2 calls hidden.');

    // Switching to Hidden view lists hidden calls and restores via open-eye icon.
    await page.locator('[data-audio-hidden-toggle]').click();
    await expect(page.locator('[data-audio-viewing-hidden]')).toBeVisible();
    await expect(page.locator('[data-audio-history-table] tbody tr')).toHaveCount(3);
    const restoreBtn = page.locator('[data-audio-visibility-toggle]').first();
    await expect(restoreBtn).toHaveAccessibleName('Restore to YA-WAMF');
    await restoreBtn.click();
    await expect(page.locator('[data-audio-history-table] tbody tr')).toHaveCount(2);
    await expect(page.locator('[data-audio-hidden-count]')).toHaveText('2');

    // Mobile width with multi-select active does not scroll sideways.
    await page.setViewportSize(WIDTHS[0]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(0);
});
