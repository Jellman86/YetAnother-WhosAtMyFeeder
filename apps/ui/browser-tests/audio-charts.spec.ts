import { test, expect, type Page } from '@playwright/test';

const summary = {
    total: 73,
    species_count: 3,
    source_count: 1,
    top_species: [
        { species: 'Dunnock', count: 38, avg_confidence: 0.9, max_confidence: 0.99 },
        { species: 'Robin', count: 25, avg_confidence: 0.85, max_confidence: 0.98 },
        { species: 'Wren', count: 10, avg_confidence: 0.8, max_confidence: 0.95 },
    ],
    daily_counts: [
        { date: '2026-09-24', count: 12 },
        { date: '2026-09-25', count: 28 },
        { date: '2026-09-26', count: 33 },
    ],
    hourly_counts: Array.from({ length: 24 }, (_, hour) => ({ hour, count: hour === 8 ? 18 : hour % 5 })),
    sources: [{ source_name: 'BirdCam', count: 73, last_heard: '2026-09-26T12:00:00Z' }],
    window_start: '2026-08-27T12:00:00Z',
    window_end: '2026-09-26T12:00:00Z',
};

// The same 73 calls by weekday and hour: Monday 08:00 is the busiest slot.
const heatmapCells = Array.from({ length: 7 * 24 }, (_, index) => ({ day_of_week: Math.floor(index / 24), hour: index % 24, count: 0 }));
for (const [day, hour, count] of [[1, 8, 18], [1, 9, 12], [2, 8, 9], [3, 6, 14], [5, 18, 20]] as const) heatmapCells[day * 24 + hour].count = count;
const heatmap = { window_start: '2026-08-27T12:00:00Z', window_end: '2026-09-26T12:00:00Z', total_count: 73, max_cell_count: 20, cells: heatmapCells };

test.beforeEach(async ({ page }) => {
    await page.route(url => url.pathname.startsWith('/api/'), async route => {
        const path = new URL(route.request().url()).pathname;
        if (path === '/api/audio/history') {
            await route.fulfill({ json: { items: [], total: 0, limit: 25, offset: 0 } });
        } else if (path === '/api/audio/history/hidden-count') {
            await route.fulfill({ json: { hidden_count: 0 } });
        } else if (path === '/api/audio/summary') {
            await route.fulfill({ json: summary });
        } else if (path === '/api/audio/activity-heatmap') {
            await route.fulfill({ json: heatmap });
        } else if (path === '/api/settings' || path.includes('/species/') && path.endsWith('/info')) {
            await route.fulfill({ json: {} });
        } else {
            throw new Error(`Unexpected audio fixture API request: ${route.request().url()}`);
        }
    });
    page.on('pageerror', error => { throw error; });
    await page.goto('/browser-tests/audio-charts.html');
});

test('audio charts draw, toggle species and fit the viewport', async ({ page }, testInfo) => {
    const canvases = page.locator('[data-audio-history-analytics] canvas');
    await expect(canvases).toHaveCount(2);
    await expect.poll(() => canvases.evaluateAll(nodes => nodes.map(node => Boolean((node as HTMLCanvasElement & { __chartjs?: unknown }).__chartjs)))).toEqual([true, true]);

    const rendered = await canvases.evaluateAll(nodes => nodes.map(node => {
        const canvas = node as HTMLCanvasElement;
        const context = canvas.getContext('2d');
        const pixels = context?.getImageData(0, 0, canvas.width, canvas.height).data ?? [];
        let opaquePixels = 0;
        for (let index = 3; index < pixels.length; index += 4) {
            if (pixels[index] > 0) opaquePixels += 1;
        }
        return { width: canvas.getBoundingClientRect().width, height: canvas.getBoundingClientRect().height, opaquePixels };
    }));
    for (const chart of rendered) {
        expect(chart.width).toBeGreaterThan(100);
        expect(chart.height).toBeGreaterThan(100);
        expect(chart.opaquePixels).toBeGreaterThan(100);
    }

    // The plotted coordinates settle after the configured 250 ms animation.
    await page.waitForTimeout(350);

    for (const canvas of [canvases.nth(0)]) {
        const point = await canvas.evaluate(node => {
            const chart = (node as HTMLCanvasElement & { __chartjs?: { getDatasetMeta(index: number): { data: Array<{ x: number; y: number }> } } }).__chartjs;
            const element = chart?.getDatasetMeta(0).data[8] ?? chart?.getDatasetMeta(0).data[1];
            return element ? { x: element.x, y: element.y + 8 } : null;
        });
        expect(point).not.toBeNull();
        await canvas.hover({ position: point! });
        await expect.poll(() => canvas.evaluate(node => {
            const chart = (node as HTMLCanvasElement & { __chartjs?: { tooltip?: { opacity: number } } }).__chartjs;
            return chart?.tooltip?.opacity ?? 0;
        })).toBeGreaterThan(0);
    }

    const donut = canvases.nth(1);
    await page.getByRole('button', { name: 'Hide Dunnock' }).focus();
    await page.keyboard.press('Enter');
    await expect.poll(() => donut.evaluate(node => (node as HTMLCanvasElement & { __chartjs?: { getDataVisibility(index: number): boolean } }).__chartjs?.getDataVisibility(0))).toBe(false);
    await expect(page.getByRole('button', { name: 'Show Dunnock' })).toHaveAttribute('aria-pressed', 'false');

    await expect(page.locator('html')).toHaveClass(/dark/);
    await page.screenshot({ path: testInfo.outputPath('audio-charts-dark.png'), fullPage: true });
    await page.getByRole('button', { name: 'Toggle theme' }).click();
    await expect(page.locator('html')).not.toHaveClass(/dark/);
    await expect(page.getByRole('button', { name: 'Hide Dunnock' })).toHaveAttribute('aria-pressed', 'true');
    await expect.poll(() => donut.evaluate(node => (node as HTMLCanvasElement & { __chartjs?: { getDataVisibility(index: number): boolean } }).__chartjs?.getDataVisibility(0))).toBe(true);
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath('audio-charts.png'), fullPage: true });
});

test('audio charts respect reduced motion', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.reload();
    const canvases = page.locator('[data-audio-history-analytics] canvas');
    await expect(canvases).toHaveCount(2);
    await expect.poll(() => canvases.evaluateAll(nodes => nodes.map(node => {
        const chart = (node as HTMLCanvasElement & { __chartjs?: { options: { animation: unknown } } }).__chartjs;
        return chart?.options.animation === false;
    }))).toEqual([true, true]);
});

test('a full species legend leaves the donut readable on phones', async ({ page, isMobile }, testInfo) => {
    test.skip(!isMobile);
    const names = [
        'Dunnock', 'House Sparrow', 'Eurasian Blue Tit', 'European Robin',
        'Great Spotted Woodpecker', 'Long-tailed Tit', 'Goldcrest', 'Eurasian Wren',
    ];
    await page.route('**/api/audio/summary?*', route => route.fulfill({
        json: {
            ...summary,
            total: 108,
            species_count: 8,
            top_species: names.map((species, index) => ({ species, count: 24 - index * 3, avg_confidence: 0.9, max_confidence: 0.99 })),
        },
    }));
    await page.getByRole('button', { name: 'Refresh' }).click();
    const donut = page.locator('[data-audio-history-analytics] canvas').nth(1);
    await expect.poll(() => donut.evaluate(node => {
        const chart = (node as HTMLCanvasElement & { __chartjs?: { data: { labels: string[] }; chartArea: { top: number; bottom: number } } }).__chartjs;
        return chart?.data.labels.length === 8 ? chart.chartArea.bottom - chart.chartArea.top : 0;
    })).toBeGreaterThan(70);
    await page.screenshot({ path: testInfo.outputPath('audio-charts-full-legend.png'), fullPage: true });
});

test('filters apply on Enter and say when the form differs from the list', async ({ page }) => {
    const requests: URLSearchParams[] = [];
    await page.route('**/api/audio/history?*', route => {
        requests.push(new URL(route.request().url()).searchParams);
        return route.fulfill({ json: { items: [], total: 0, limit: 25, offset: 0 } });
    });
    const changed = page.locator('[data-audio-filters-changed]');
    await expect(changed).toHaveText('');

    const species = page.getByRole('textbox', { name: 'Species' });
    await species.fill('Dunnock');
    await expect(changed).toHaveText('Filters changed. Apply to update the list.');
    // Typing alone fetches nothing for the new species; only applying does.
    expect(requests.filter(params => params.has('species'))).toEqual([]);

    await species.press('Enter');
    await expect.poll(() => requests.at(-1)?.get('species')).toBe('Dunnock');
    await expect(changed).toHaveText('');
});

test('a spectrogram that fails to load falls back to the placeholder', async ({ page }) => {
    await page.route('**/api/audio/history?*', route => route.fulfill({ json: {
        items: [{ id: 1, birdnet_id: 501, species: 'Dunnock', confidence: 0.91, timestamp: '2026-09-26T08:15:00Z', source_name: 'BirdCam' }],
        total: 1, limit: 25, offset: 0,
    } }));
    await page.route('**/api/audio/spectrogram/**', route => route.fulfill({ status: 404, body: 'Not found' }));
    await page.reload();
    await expect(page.locator('[data-audio-history-table]')).toContainText('Dunnock');
    await expect(page.locator('[data-audio-spectrogram]')).toHaveCount(0);
    await expect(page.locator('[data-audio-history-table] svg[aria-hidden="true"]').first()).toBeVisible();
});

test('the hour of day is a weekday-by-hour grid of calls heard, read with the same filters as the summary', async ({ page, isMobile }) => {
    test.skip(isMobile, 'drives the window bar and inline filters, which are the desktop controls; the phone sheet has its own spec');
    const requests: URLSearchParams[] = [];
    await page.route('**/api/audio/activity-heatmap?*', route => {
        requests.push(new URL(route.request().url()).searchParams);
        return route.fulfill({ json: heatmap });
    });
    await page.reload();
    const grid = page.locator('[data-audio-heatmap] [role="grid"]');
    await expect(grid).toBeVisible();
    await expect(grid.locator('[role="gridcell"]')).toHaveCount(7 * 24);
    // Each slot reads in calls heard, never as captures or visits.
    await expect(grid.getByRole('gridcell', { name: /^Fri 18:00 to 19:00: 20 calls heard\. Busiest slot$/ })).toHaveCount(1);
    await expect(grid.getByRole('gridcell', { name: /^Mon 08:00 to 09:00: 18 calls heard$/ })).toHaveCount(1);
    await expect(page.locator('[data-audio-heatmap]')).toContainText('calls heard in one hour slot');
    await expect(page.locator('[data-audio-heatmap]')).not.toContainText(/capture|visit/i);
    // The busiest hour is the grid's own, and the window line names the window the server counted.
    await expect(page.locator('[data-audio-standing]')).toContainText('Busiest hour');
    await expect(page.locator('[data-audio-standing]')).toContainText('08:00');
    await expect(page.locator('[data-audio-standing]')).toContainText('27 calls heard');
    await expect(page.locator('[data-audio-analytics-window]')).toHaveText(/^Last 30 days · .+-.+$/);

    // The grid follows the page: a new window and an applied species are both sent.
    await page.locator('[data-audio-window-bar] [data-segment="7d"]').click();
    await expect.poll(() => requests.at(-1)?.get('days')).toBe('7');
    await page.getByRole('textbox', { name: 'Species' }).fill('Dunnock');
    await page.getByRole('textbox', { name: 'Species' }).press('Enter');
    await expect.poll(() => requests.at(-1)?.get('species')).toBe('Dunnock');
    expect(requests.at(-1)?.get('days')).toBe('7');

    // Its data is a table too, a row per weekday.
    const figure = page.locator('[data-audio-history-analytics] figure').filter({ has: page.locator('[data-audio-heatmap]') });
    await figure.locator('summary').filter({ hasText: 'Show the data as a table' }).click();
    await expect(figure.locator('table tbody tr')).toHaveCount(7);
});

test('Today asks the list, the summary and the grid for one pair of instants, and says when nothing is heard yet', async ({ page, isMobile }) => {
    test.skip(isMobile, 'drives the window bar, which is the desktop control');
    const asked: Record<string, URLSearchParams[]> = { history: [], summary: [], 'activity-heatmap': [] };
    await page.route(/\/api\/audio\/(history|summary|activity-heatmap)\?/, route => {
        const url = new URL(route.request().url());
        const surface = url.pathname.split('/').at(-1) ?? '';
        asked[surface].push(url.searchParams);
        if (surface === 'history') return route.fulfill({ json: { items: [], total: 0, limit: 25, offset: 0 } });
        if (surface === 'summary') return route.fulfill({ json: { ...summary, total: 0, top_species: [], daily_counts: [] } });
        return route.fulfill({ json: { ...heatmap, total_count: 0, max_cell_count: 0, cells: heatmapCells.map(cell => ({ ...cell, count: 0 })) } });
    });
    await page.reload();

    await page.locator('[data-audio-window-bar] [data-segment="today"]').click();
    await expect.poll(() => asked['activity-heatmap'].at(-1)?.get('start_date')).toBeTruthy();

    const [history, totals, grid] = [asked.history.at(-1), asked.summary.at(-1), asked['activity-heatmap'].at(-1)];
    const start = history?.get('start_date') ?? '';
    const end = history?.get('end_date') ?? '';
    const localMidnight = await page.evaluate(() => { const midnight = new Date(); midnight.setHours(0, 0, 0, 0); return midnight.toISOString(); });
    expect(start).toBe(localMidnight);
    expect(Date.parse(end)).toBeGreaterThanOrEqual(Date.parse(start));
    for (const params of [totals, grid]) {
        expect(params?.get('start_date')).toBe(start);
        expect(params?.get('end_date')).toBe(end);
    }
    expect(history?.get('offset')).toBe('0');
    await expect(page.locator('[data-audio-history-empty-today]')).toHaveText('No calls heard yet today. Select Refresh to check for new calls.');
    await expect(page.locator('[data-audio-analytics-window]')).toHaveText(/^Today · .+-.+$/);
});

/** Holds the list, summary and grid reads until released, so a test can look at the page while they load. */
async function holdAudioReads(page: Page): Promise<{ held: () => number; release: () => void }> {
    let opened = false;
    let open: () => void = () => undefined;
    const gate = new Promise<void>(resolve => { open = resolve; });
    let held = 0;
    await page.route(/\/api\/audio\/(history|summary|activity-heatmap)\?/, async route => {
        if (!opened) {
            held += 1;
            await gate;
        }
        await route.fallback();
    });
    return { held: () => held, release: () => { opened = true; open(); } };
}

test('choosing Today shows no dates beside its name until Today has been read', async ({ page, isMobile }) => {
    test.skip(isMobile, 'drives the window bar, which is the desktop control');
    const windowLine = page.locator('[data-audio-analytics-window]');
    await expect(windowLine).toHaveText(/^Last 30 days · .+-.+$/);

    const reads = await holdAudioReads(page);
    await page.locator('[data-audio-window-bar] [data-segment="today"]').click();
    await expect.poll(reads.held).toBeGreaterThanOrEqual(3);
    // The 30 days' dates never stand beside Today's name.
    await expect(windowLine).toHaveText('Today');

    reads.release();
    await expect(windowLine).toHaveText(/^Today · .+-.+$/);
});

test('at midnight Today reads the new day and hides the old day\'s range until it lands', async ({ page, isMobile }) => {
    test.skip(isMobile, 'drives the window bar, which is the desktop control');
    await page.clock.install({ time: new Date('2026-11-25T23:59:30') });
    await page.reload();
    const windowLine = page.locator('[data-audio-analytics-window]');
    await page.locator('[data-audio-window-bar] [data-segment="today"]').click();
    await expect(windowLine).toHaveText(/^Today · .+-.+$/);

    const asked: string[] = [];
    page.on('request', request => {
        const url = new URL(request.url());
        if (url.pathname === '/api/audio/summary') asked.push(url.searchParams.get('start_date') ?? '');
    });
    const reads = await holdAudioReads(page);
    await page.clock.fastForward('01:00');
    await expect.poll(reads.held).toBeGreaterThanOrEqual(3);
    await expect(windowLine).toHaveText('Today');
    // The new day starts at the next local midnight (the fixture's zone is London, at UTC in November).
    expect(asked.at(-1)).toBe('2026-11-26T00:00:00.000Z');

    reads.release();
    await expect(windowLine).toHaveText(/^Today · .+-.+$/);
});

test('a window with no calls says so in the grid, not as an empty grid', async ({ page }) => {
    await page.route('**/api/audio/activity-heatmap?*', route => route.fulfill({ json: { ...heatmap, total_count: 0, max_cell_count: 0, cells: heatmapCells.map(cell => ({ ...cell, count: 0 })) } }));
    await page.reload();
    await expect(page.locator('[data-audio-heatmap-empty]')).toHaveText('No calls heard in this window.');
    await expect(page.locator('[data-audio-heatmap]')).toHaveCount(0);
});

test('a grid that cannot be read says so in its own frame, and the list and other figures stay', async ({ page }) => {
    await page.route('**/api/audio/activity-heatmap?*', route => route.fulfill({ status: 503, json: { detail: 'History temporarily unavailable.' } }));
    await page.route('**/api/audio/history?*', route => route.fulfill({ json: {
        items: [{ id: 1, birdnet_id: null, species: 'Dunnock', confidence: 0.91, timestamp: '2026-09-26T08:15:00Z', source_name: 'BirdCam' }],
        total: 1, limit: 25, offset: 0,
    } }));
    await page.reload();
    await expect(page.locator('[data-audio-heatmap-failed]')).toContainText('could not be read');
    await expect(page.locator('[data-audio-heatmap]')).toHaveCount(0);
    // The page as a whole was read: no page-level failure, the list and the summary's figures are on show.
    await expect(page.locator('[data-audio-read-failed]')).toHaveCount(0);
    await expect(page.locator('[data-audio-history-table]')).toContainText('Dunnock');
    await expect(page.locator('[data-audio-standing]')).toContainText('73');
    // Only the figure that comes from the grid is withheld, in words.
    await expect(page.locator('[data-audio-standing] [data-audio-stat-unavailable]')).toHaveCount(1);
    await expect(page.locator('[data-audio-history-analytics] canvas')).toHaveCount(2);

    // Retrying reads it again.
    await page.unroute('**/api/audio/activity-heatmap?*');
    await page.locator('[data-audio-heatmap-failed]').getByRole('button', { name: 'Retry' }).click();
    await expect(page.locator('[data-audio-heatmap] [role="grid"]')).toBeVisible();
    await expect(page.locator('[data-audio-standing] [data-audio-stat-unavailable]')).toHaveCount(0);
});

// The window's most heard species, named as the grid asks for them: by scientific name.
const namedSummary = {
    ...summary,
    top_species: [
        { species: 'Dunnock', scientific_name: 'Prunella modularis', count: 38, avg_confidence: 0.9, max_confidence: 0.99 },
        { species: 'Robin', scientific_name: 'Erithacus rubecula', count: 25, avg_confidence: 0.85, max_confidence: 0.98 },
        { species: 'Wren', scientific_name: 'Troglodytes troglodytes', count: 10, avg_confidence: 0.8, max_confidence: 0.95 },
    ],
};
const robinCells = heatmapCells.map(cell => ({ ...cell, count: cell.day_of_week === 2 && cell.hour === 7 ? 6 : 0 }));
const robinHeatmap = { ...heatmap, total_count: 6, max_cell_count: 6, cells: robinCells };

/** Serves the named summary and records every grid request; a species grid is answered by `forSpecies`. */
async function withSpeciesChips(page: Page, forSpecies: (scientificName: string) => Promise<object | null> | object | null = () => robinHeatmap) {
    const requests: URLSearchParams[] = [];
    await page.route('**/api/audio/summary?*', route => route.fulfill({ json: namedSummary }));
    await page.route('**/api/audio/activity-heatmap?*', async route => {
        const params = new URL(route.request().url()).searchParams;
        requests.push(params);
        const scientificName = params.get('scientific_name');
        if (!scientificName) return route.fulfill({ json: heatmap });
        const answer = await forSpecies(scientificName);
        // A request the page has since aborted can no longer be answered; that is the point.
        const reply = answer ? route.fulfill({ json: answer }) : route.fulfill({ status: 503, json: { detail: 'Grid temporarily unavailable.' } });
        return reply.catch(() => undefined);
    });
    await page.reload();
    await expect(page.locator('[data-audio-heatmap] [role="grid"]')).toBeVisible();
    return { requests, picker: page.getByRole('group', { name: 'Show calls heard from' }) };
}

test('a species chip shows that species’ calls by hour and weekday, read under the page’s filters', async ({ page, isMobile }) => {
    test.skip(isMobile, 'drives the window bar and inline filters, which are the desktop controls');
    const { requests, picker } = await withSpeciesChips(page);
    const all = picker.getByRole('button', { name: 'All species', exact: true });
    const robin = picker.getByRole('button', { name: 'Robin', exact: true });
    // Ordered by calls heard, as many as the Leaderboard offers, all species first and chosen.
    await expect(picker.getByRole('button')).toHaveText(['All species', 'Dunnock', 'Robin', 'Wren']);
    await expect(all).toHaveAttribute('aria-pressed', 'true');

    await page.locator('[data-audio-window-bar] [data-segment="7d"]').click();
    await expect.poll(() => requests.at(-1)?.get('days')).toBe('7');
    await page.getByRole('textbox', { name: 'Source' }).fill('BirdCam');
    await page.getByRole('textbox', { name: 'Source' }).press('Enter');
    await expect.poll(() => requests.at(-1)?.get('source')).toBe('BirdCam');
    await expect(robin).toBeVisible();

    await robin.click();
    await expect.poll(() => requests.at(-1)?.get('scientific_name')).toBe('Erithacus rubecula');
    const asked = requests.at(-1);
    expect(asked?.get('days')).toBe('7');
    expect(asked?.get('source')).toBe('BirdCam');
    expect(asked?.has('species')).toBe(false);
    await expect(robin).toHaveAttribute('aria-pressed', 'true');
    await expect(all).toHaveAttribute('aria-pressed', 'false');

    // The grid, its slots and its total are the Robin's, and say so.
    const grid = page.getByRole('grid', { name: /Robin\.$/ });
    await expect(grid).toBeVisible();
    await expect(grid.getByRole('gridcell', { name: /^Tue 07:00 to 08:00: 6 Robin calls heard\. Busiest slot$/ })).toHaveCount(1);
    const figure = page.locator('[data-audio-history-analytics] figure').filter({ has: page.locator('[data-audio-heatmap]') });
    await expect(figure).toContainText('6 calls heard');
    // The page's own figures stay those of all species.
    await expect(page.locator('[data-audio-standing]')).toContainText('27 calls heard');

    await all.click();
    await expect(all).toHaveAttribute('aria-pressed', 'true');
    await expect(page.getByRole('grid', { name: /Robin/ })).toHaveCount(0);
    await expect(figure).toContainText('73 calls heard');
});

test('species chips work from the keyboard', async ({ page, isMobile }) => {
    test.skip(isMobile, 'keyboard focus order is a desktop concern');
    const { picker } = await withSpeciesChips(page);
    const all = picker.getByRole('button', { name: 'All species', exact: true });
    await all.focus();
    await page.keyboard.press('Tab');
    await page.keyboard.press('Tab');
    await expect(picker.getByRole('button', { name: 'Robin', exact: true })).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(picker.getByRole('button', { name: 'Robin', exact: true })).toHaveAttribute('aria-pressed', 'true');
    await expect(page.getByRole('grid', { name: /Robin\.$/ })).toBeVisible();
    await page.keyboard.press('Shift+Tab');
    await page.keyboard.press('Space');
    await expect(picker.getByRole('button', { name: 'Dunnock', exact: true })).toHaveAttribute('aria-pressed', 'true');
});

test('a species with no calls in the grid says so, and a grid that cannot be read offers a retry', async ({ page }) => {
    let fail = true;
    const { picker } = await withSpeciesChips(page, scientificName => {
        if (scientificName === 'Troglodytes troglodytes') return { ...heatmap, total_count: 0, max_cell_count: 0, cells: heatmapCells.map(cell => ({ ...cell, count: 0 })) };
        return fail ? null : robinHeatmap;
    });

    await picker.getByRole('button', { name: 'Wren', exact: true }).click();
    await expect(page.locator('[data-audio-species-heatmap-empty]')).toHaveText('No Wren calls heard in this window.');
    await expect(page.locator('[data-audio-heatmap]')).toHaveCount(0);

    await picker.getByRole('button', { name: 'Robin', exact: true }).click();
    const failed = page.locator('[data-audio-species-heatmap-failed]');
    await expect(failed).toContainText('Robin calls by hour and weekday could not be read. Everything else on the page was read.');
    await expect(page.locator('[data-audio-heatmap]')).toHaveCount(0);
    // Only the species grid failed: the page's figures stay.
    await expect(page.locator('[data-audio-standing] [data-audio-stat-unavailable]')).toHaveCount(0);

    fail = false;
    await failed.getByRole('button', { name: 'Retry' }).click();
    await expect(page.getByRole('grid', { name: /Robin\.$/ })).toBeVisible();
    await expect(failed).toHaveCount(0);
});

test('a quick second choice is never overwritten by the first one’s late answer', async ({ page }) => {
    let releaseRobin: () => void = () => {};
    const robinHeld = new Promise<void>(resolve => { releaseRobin = resolve; });
    const dunnockHeatmap = { ...robinHeatmap, cells: robinCells.map(cell => ({ ...cell, count: cell.count ? 4 : 0 })), total_count: 4, max_cell_count: 4 };
    const { picker } = await withSpeciesChips(page, async scientificName => {
        if (scientificName === 'Erithacus rubecula') {
            await robinHeld;
            return robinHeatmap;
        }
        return dunnockHeatmap;
    });

    await picker.getByRole('button', { name: 'Robin', exact: true }).click();
    await picker.getByRole('button', { name: 'Dunnock', exact: true }).click();
    await expect(page.getByRole('grid', { name: /Dunnock\.$/ })).toBeVisible();
    releaseRobin();
    await page.waitForTimeout(300);
    await expect(page.getByRole('grid', { name: /Dunnock\.$/ })).toBeVisible();
    await expect(page.getByRole('grid', { name: /Robin/ })).toHaveCount(0);
    await expect(picker.getByRole('button', { name: 'Dunnock', exact: true })).toHaveAttribute('aria-pressed', 'true');
});

test('a page species filter hides the chips, and a window without the chosen species goes back to all species', async ({ page, isMobile }) => {
    test.skip(isMobile, 'drives the window bar and inline filters, which are the desktop controls');
    const { picker } = await withSpeciesChips(page);
    await picker.getByRole('button', { name: 'Wren', exact: true }).click();
    await expect(picker.getByRole('button', { name: 'Wren', exact: true })).toHaveAttribute('aria-pressed', 'true');

    // The week heard no Wren, so the choice lapses rather than asking for a species not on offer.
    await page.route('**/api/audio/summary?*', route => route.fulfill({ json: { ...namedSummary, top_species: namedSummary.top_species.slice(0, 2) } }));
    await page.locator('[data-audio-window-bar] [data-segment="7d"]').click();
    await expect(picker.getByRole('button')).toHaveText(['All species', 'Dunnock', 'Robin']);
    await expect(picker.getByRole('button', { name: 'All species', exact: true })).toHaveAttribute('aria-pressed', 'true');
    await expect(page.getByRole('grid', { name: /Wren/ })).toHaveCount(0);

    // The page's species search already narrows the grid; a second species control is not offered.
    await page.getByRole('textbox', { name: 'Species' }).fill('Dunnock');
    await page.getByRole('textbox', { name: 'Species' }).press('Enter');
    await expect(picker).toHaveCount(0);
    await expect(page.locator('[data-audio-heatmap] [role="grid"]')).toBeVisible();
});

test('species chips fit a phone at 390 pixels with full-size targets', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const { picker } = await withSpeciesChips(page);
    // The app's main column has a 16 px gutter on a phone; the bare fixture has none.
    await page.addStyleTag({ content: '#app { padding-inline: 1rem; }' });
    await expect(picker).toBeVisible();
    const figure = page.locator('[data-audio-history-analytics] figure').filter({ has: picker });
    const [row, frame] = await Promise.all([picker.boundingBox(), figure.boundingBox()]);
    // The row may reach into the figure's edge for focus rings, never past the gutter.
    expect((row?.x ?? 0) + (row?.width ?? 0)).toBeLessThanOrEqual((frame?.x ?? 0) + (frame?.width ?? 0) + 4);
    for (const box of await picker.getByRole('button').evaluateAll(nodes => nodes.map(node => node.getBoundingClientRect().height))) {
        expect(box).toBeGreaterThanOrEqual(44);
    }
    await picker.getByRole('button', { name: 'Wren', exact: true }).click();
    await expect(page.getByRole('grid', { name: /Wren\.$/ })).toBeVisible();
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('a refresh keeps the chosen species’ grid on screen, dimmed, until its new reading lands', async ({ page }) => {
    let holdNext = false;
    let release: () => void = () => {};
    const { picker } = await withSpeciesChips(page, async () => {
        if (holdNext) await new Promise<void>(resolve => { release = resolve; });
        return robinHeatmap;
    });
    await picker.getByRole('button', { name: 'Robin', exact: true }).click();
    const frame = page.locator('[data-audio-species-heatmap]');
    await expect(page.getByRole('grid', { name: /Robin\.$/ })).toBeVisible();
    await expect(frame).toHaveAttribute('aria-busy', 'false');

    holdNext = true;
    const refresh = page.getByRole('button', { name: 'Refresh', exact: true });
    await refresh.click();
    // The page's own reading has landed; the Robin grid's is still on its way.
    await expect(refresh).toBeEnabled();
    await expect(frame).toHaveAttribute('aria-busy', 'true');
    await expect(page.getByRole('grid', { name: /Robin\.$/ })).toBeVisible();
    await expect(frame.locator('.animate-pulse')).toHaveCount(0);

    release();
    await expect(frame).toHaveAttribute('aria-busy', 'false');
    await expect(page.getByRole('grid', { name: /Robin\.$/ })).toBeVisible();
});

test('a renamed source is one entry, and two sources that share a name show their BirdNET-Go ids', async ({ page }) => {
    await page.route('**/api/audio/summary*', route => route.fulfill({
        json: {
            ...summary,
            source_count: 8,
            sources: [
                { source_name: 'Feeder', source_id: 'rtsp_3af0d74c', count: 40, last_heard: '2026-09-26T12:00:00Z' },
                { source_name: 'nestcam', source_id: 'rtsp_0d6c2ad3', count: 20, last_heard: '2026-09-26T11:00:00Z' },
                { source_name: 'nestcam', source_id: 'rtsp_9e1b77a0', count: 9, last_heard: '2026-09-20T11:00:00Z' },
                { source_name: 'nestcam', source_id: null, count: 4, last_heard: '2026-08-30T11:00:00Z' },
                { source_name: 'Default Audio Device', source_id: 'audio_card_22a9b331', source_node: 'Shed', count: 3, last_heard: '2026-08-29T11:00:00Z' },
                { source_name: 'Default Audio Device', source_id: 'audio_card_22a9b331', source_node: 'House', count: 2, last_heard: '2026-08-28T11:00:00Z' },
                { source_name: 'Unknown source', source_id: null, source_node: 'Shed', count: 1, last_heard: '2026-08-27T11:00:00Z' },
                { source_name: 'Unknown source', source_id: null, source_node: 'House', count: 1, last_heard: '2026-08-26T11:00:00Z' },
            ],
        },
    }));
    await page.reload();

    const sources = page.getByRole('heading', { name: 'Sources', exact: true }).locator('xpath=following-sibling::div[1]');
    await expect(sources.getByText('Feeder', { exact: true })).toHaveCount(1);
    await expect(sources.getByText('nestcam', { exact: true })).toHaveCount(3);
    // A name only one source carries needs no id beside it.
    await expect(sources.locator('[data-audio-source-id]')).toHaveText([
        'BirdNET-Go id rtsp_0d6c2ad3',
        'BirdNET-Go id rtsp_9e1b77a0',
        'Calls without a usable BirdNET-Go id',
        // Two installs whose sound cards share a name and an id are told apart by the install.
        'BirdNET-Go id audio_card_22a9b331 on Shed',
        'BirdNET-Go id audio_card_22a9b331 on House',
        // Calls with no id that share a name are told apart by their install.
        'Calls without a usable BirdNET-Go id on Shed',
        'Calls without a usable BirdNET-Go id on House',
    ]);
});
