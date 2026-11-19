import { test, expect } from '@playwright/test';

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

test('the hour of day is a weekday-by-hour grid of calls heard, read with the same filters as the summary', async ({ page }) => {
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
    await expect(page.locator('[data-audio-analytics-window]')).toHaveText(/^30 days · .+-.+$/);

    // The grid follows the page: a new window and an applied species are both sent.
    await page.locator('[data-audio-window-bar] [data-segment="7"]').click();
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

test('a window with no calls says so in the grid, not as an empty grid', async ({ page }) => {
    await page.route('**/api/audio/activity-heatmap?*', route => route.fulfill({ json: { ...heatmap, total_count: 0, max_cell_count: 0, cells: heatmapCells.map(cell => ({ ...cell, count: 0 })) } }));
    await page.reload();
    await expect(page.locator('[data-audio-heatmap-empty]')).toHaveText('No calls heard in this window.');
    await expect(page.locator('[data-audio-heatmap]')).toHaveCount(0);
});

test('a grid that cannot be read says so in its own frame, and the list and other figures stay', async ({ page }) => {
    await page.route('**/api/audio/activity-heatmap?*', route => route.fulfill({ status: 503, json: { detail: 'History temporarily unavailable.' } }));
    await page.route('**/api/audio/history?*', route => route.fulfill({ json: {
        items: [{ id: 1, birdnet_id: 501, species: 'Dunnock', confidence: 0.91, timestamp: '2026-09-26T08:15:00Z', source_name: 'BirdCam' }],
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
