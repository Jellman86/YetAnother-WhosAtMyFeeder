import { test, expect, type Locator } from '@playwright/test';

const start = '2026-09-01T00:00:00Z';
const end = '2026-09-08T00:00:00Z';
const points = Array.from({ length: 7 }, (_, index) => ({
    bucket_start: `2026-09-${String(index + 1).padStart(2, '0')}T00:00:00Z`,
    label: `${index + 1} Sep`,
    count: [3, 5, 9, 7, 12, 8, 10][index],
    unique_species: 3,
}));
const species = [
    { species: 'Robin', count: 22 },
    { species: 'Dunnock', count: 18 },
    { species: 'Wren', count: 14 },
].map(({ species, count }) => ({
    species, common_name: species, scientific_name: species,
    window_count: count, window_prev_count: count - 2, window_delta: 2, window_percent: 10,
    window_avg_confidence: 0.87, window_camera_count: 1,
    window_first_seen: start, window_last_seen: end,
}));

// The wall's captures: one visit each (an hour apart), Robin, Dunnock and Wren in turn.
const pixel = '<svg xmlns="http://www.w3.org/2000/svg" width="4" height="4"><rect width="4" height="4" fill="#7a9a6a"/></svg>';
let wallCaptures: Array<Record<string, unknown>>;
const captures = (count: number) => Array.from({ length: count }, (_, index) => ({
    frigate_event: `wall-${index}`,
    display_name: species[index % 3].species,
    scientific_name: species[index % 3].species,
    score: 0.7 + (index % 5) / 20,
    detection_time: new Date(Date.parse('2026-09-07T20:00:00Z') - index * 3_600_000).toISOString(),
    camera_name: 'feeder',
    has_snapshot: true,
    has_clip: index % 4 === 0,
}));

let capturedImage: string | null;
test.beforeEach(async ({ page }) => {
    capturedImage = null;
    wallCaptures = [];
    await page.route(url => url.pathname.startsWith('/api/'), async route => {
        const url = new URL(route.request().url());
        const path = url.pathname;
        if (path === '/api/leaderboard/species') {
            await route.fulfill({ json: { span: 'month', species, window_start: start, window_end: end } });
        } else if (path === '/api/leaderboard/portraits') {
            await route.fulfill({ json: { span: 'month', portraits: [] } });
        } else if (path === '/api/stats/detections/timeline') {
            await route.fulfill({ json: {
                span: 'month', bucket: 'day', points, total_count: 54,
                window_start: start, window_end: end,
                compare_series: species.map(({ species }, speciesIndex) => ({
                    species,
                    points: points.map((point, index) => ({ bucket_start: point.bucket_start, count: [1, 2, 2][speciesIndex] + index % 3 })),
                })),
                weather: points.map((point, index) => ({ bucket_start: point.bucket_start, temp_avg: 12 + index, wind_avg: 6 + index, rain_total: index === 3 ? 2 : 0 })),
            } });
        } else if (path === '/api/stats/detections/activity-heatmap') {
            await route.fulfill({ json: {
                span: 'month', window_start: start, window_end: end, total_count: 54, max_cell_count: 12,
                cells: [{ day_of_week: 1, hour: 8, count: 12 }, { day_of_week: 6, hour: 17, count: 5 }],
            } });
        } else if (path === '/api/leaderboard/analysis') {
            await route.fulfill({ status: 204 });
        } else if (path === '/api/leaderboard/analyze') {
            const body = route.request().postDataJSON();
            capturedImage = body.image_base64;
            await route.fulfill({ json: { analysis: 'Activity peaks on 5 September.', analysis_timestamp: end } });
        } else if (path === '/api/events') {
            await route.fulfill({ json: wallCaptures });
        } else if (path.startsWith('/api/about/showcase/') && path.endsWith('.jpg')) {
            await route.fulfill({ contentType: 'image/svg+xml', body: pixel });
        } else if (path.includes('/species/') && path.endsWith('/info')) {
            await route.fulfill({ json: {} });
        } else {
            throw new Error(`Unexpected species fixture API request: ${route.request().url()}`);
        }
    });
    await page.goto('/browser-tests/species-charts.html');
});

test('trend, composition and heatmap render and respond to controls', async ({ page }, testInfo) => {
    const trend = page.locator('canvas[aria-label^="Detections over time"]');
    const donut = page.locator('canvas[aria-label="Species composition"]');
    await expect(trend).toBeVisible();
    await expect(donut).toBeVisible();
    await expect.poll(() => trend.evaluate(node => Boolean((node as HTMLCanvasElement & { __chartjs?: unknown }).__chartjs))).toBe(true);
    await expect.poll(() => donut.evaluate(node => Boolean((node as HTMLCanvasElement & { __chartjs?: unknown }).__chartjs))).toBe(true);
    await expect.poll(() => trend.evaluate(node => {
        const chart = (node as HTMLCanvasElement & { __chartjs?: { data: { datasets: unknown[] } } }).__chartjs;
        return chart?.data.datasets.length;
    })).toBe(4);
    await expect(page.getByRole('grid', { name: /Activity by weekday and hour/ }).getByRole('gridcell')).toHaveCount(168);
    await expect(page.getByRole('gridcell', { name: 'Mon 08:00 to 09:00: 12 detections. Busiest slot', exact: true })).toBeVisible();

    await page.getByRole('group', { name: 'Species composition' }).getByRole('button', { name: 'Hide Robin' }).focus();
    await page.keyboard.press('Enter');
    await expect.poll(() => donut.evaluate(node => (node as HTMLCanvasElement & { __chartjs?: { getDataVisibility(index: number): boolean } }).__chartjs?.getDataVisibility(0))).toBe(false);
    await expect(page.getByRole('group', { name: 'Species composition' }).getByRole('button', { name: 'Show Robin' })).toHaveAttribute('aria-pressed', 'false');

    await page.getByRole('button', { name: 'Toggle theme' }).click();
    await expect(page.getByRole('group', { name: 'Species composition' }).getByRole('button', { name: 'Hide Robin' })).toHaveAttribute('aria-pressed', 'true');
    await expect.poll(() => donut.evaluate(node => (node as HTMLCanvasElement & { __chartjs?: { getDataVisibility(index: number): boolean } }).__chartjs?.getDataVisibility(0))).toBe(true);
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath('species-charts.png'), fullPage: true });
});

test('AI analysis receives a PNG capture of the chart', async ({ page }) => {
    await page.getByRole('button', { name: /Analyze chart/i }).click();
    await expect.poll(() => capturedImage?.startsWith('data:image/png;base64,')).toBe(true);
    await expect(page.getByText('Activity peaks on 5 September.')).toBeVisible();
});

test('weather overlays and reduced motion preserve an understandable trend', async ({ page }) => {
    const trend = page.locator('canvas[aria-label^="Detections over time"]');
    await expect(trend).toBeVisible();
    await page.getByText('Weather overlays', { exact: true }).click();
    await page.getByRole('button', { name: 'Temperature' }).click();
    await page.getByRole('button', { name: 'Avg wind' }).click();
    const temperature = page.locator('[data-leaderboard-weather-panel="temperature"] canvas');
    const wind = page.locator('[data-leaderboard-weather-panel="wind"] canvas');
    await expect(temperature).toBeVisible();
    await expect(wind).toBeVisible();
    for (const [canvas, expected] of [[temperature, [12, 13, 14, 15, 16, 17, 18]], [wind, [6, 7, 8, 9, 10, 11, 12]]] as const) {
        await expect.poll(() => canvas.evaluate(node => {
            const chart = (node as HTMLCanvasElement & { __chartjs?: { data: { datasets: Array<{ data: unknown[] }> }; scales: Record<string, unknown> } }).__chartjs;
            return { values: chart?.data.datasets[0].data, scales: Object.keys(chart?.scales ?? {}).sort() };
        })).toEqual({ values: expected, scales: ['x', 'y'] });
    }
    await expect.poll(() => trend.evaluate(node => {
        const chart = (node as HTMLCanvasElement & { __chartjs?: { data: { datasets: Array<{ label?: string }> } } }).__chartjs;
        return chart?.data.datasets.map(dataset => dataset.label);
    })).toEqual(['Robin', 'Dunnock', 'Wren', 'Other']);
    // The configured 300 ms chart animation must settle before sampling pixels.
    await page.waitForTimeout(350);
    const beforeRain = await rainPixels(trend);
    if (!beforeRain) throw new Error('Trend chart did not initialize');
    await page.getByRole('button', { name: 'Show precip' }).click();
    await expect.poll(async () => {
        const pixels = await rainPixels(trend);
        return pixels !== null && JSON.stringify(pixels[0]) !== JSON.stringify(beforeRain[0]) && JSON.stringify(pixels[1]) === JSON.stringify(beforeRain[1]);
    }).toBe(true);
    await page.getByRole('button', { name: 'Show precip' }).click();
    await expect.poll(() => rainPixels(trend)).toEqual(beforeRain);
    await page.getByRole('button', { name: 'Temperature', exact: true }).click();
    await expect(temperature).toHaveCount(0);
    await expect(wind).toBeVisible();

    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.reload();
    await expect.poll(() => trend.evaluate(node => (node as HTMLCanvasElement & { __chartjs?: { options: { animation: unknown } } }).__chartjs?.options.animation)).toBe(false);
});

test('heatmap keyboard reading starts at the peak and follows grid navigation', async ({ page }) => {
    const grid = page.getByRole('grid', { name: /Activity by weekday and hour/ });
    const peak = grid.getByRole('gridcell', { name: 'Mon 08:00 to 09:00: 12 detections. Busiest slot', exact: true });
    await page.keyboard.press('Tab');
    await grid.focus();
    await expect(grid).toBeFocused();
    await expect.poll(() => grid.getAttribute('aria-activedescendant')).toBe(await peak.getAttribute('id'));
    const tooltip = page.locator('[data-heatmap-tooltip]');
    await expect(tooltip).toContainText('12 detections');
    for (const [key, slot] of [['ArrowRight', 'Mon 09:00'], ['ArrowLeft', 'Mon 08:00'], ['ArrowDown', 'Tue 08:00'], ['Home', 'Tue 00:00'], ['End', 'Tue 23:00'], ['ArrowUp', 'Mon 23:00']] as const) {
        await page.keyboard.press(key);
        await expect(tooltip).toContainText(slot);
        const cell = grid.getByRole('gridcell', { name: new RegExp(`^${slot}`) });
        await expect.poll(() => grid.getAttribute('aria-activedescendant')).toBe(await cell.getAttribute('id'));
    }
    await page.keyboard.press('Escape');
    await expect(tooltip).toHaveCount(0);
    await expect(grid).toBeFocused();
});

test('heatmap pointer and touch reading show the selected slot and dismiss cleanly', async ({ page, isMobile }) => {
    const grid = page.getByRole('grid', { name: /Activity by weekday and hour/ });
    const peak = grid.getByRole('gridcell', { name: 'Mon 08:00 to 09:00: 12 detections. Busiest slot', exact: true });
    const tooltip = page.locator('[data-heatmap-tooltip]');
    if (isMobile) {
        await peak.tap();
        await expect(tooltip).toContainText('12 detections');
        await peak.tap();
        await expect(tooltip).toHaveCount(0);
        await grid.getByRole('gridcell', { name: 'Sat 17:00 to 18:00: 5 detections', exact: true }).tap();
        await expect(tooltip).toContainText('5 detections');
        await page.getByRole('button', { name: 'Toggle theme' }).tap();
    } else {
        await peak.hover();
        await expect(tooltip).toContainText('12 detections');
        await page.getByRole('button', { name: 'Toggle theme' }).hover();
    }
    await expect(tooltip).toHaveCount(0);
});

test('guest revalidation clears old records without collapsing the scrolled page', async ({ page }) => {
    await page.goto('/browser-tests/species-charts.html?guest');
    await expect(page.getByRole('grid', { name: /Activity by weekday and hour/ })).toBeVisible();
    const oldGeometry = await page.evaluate(() => {
        window.scrollTo(0, Math.min(900, document.documentElement.scrollHeight - innerHeight - 40));
        return { y: scrollY, height: document.documentElement.scrollHeight };
    });
    expect(oldGeometry.y).toBeGreaterThan(100);
    let release = () => {};
    const waiting = new Promise<void>(resolve => { release = resolve; });
    let requested = false;
    await page.route('**/api/leaderboard/species?*', async route => {
        requested = true;
        await waiting;
        await route.fulfill({ json: { span: 'month', species, window_start: start, window_end: end } });
    });
    try {
        await page.evaluate(() => document.dispatchEvent(new Event('fixture-public-history')));
        await expect.poll(() => requested).toBe(true);
        await expect(page.locator('[data-leaderboard-rankings]')).toHaveCount(0);
        await expect.poll(() => page.evaluate(() => scrollY)).toBeCloseTo(oldGeometry.y, 0);
        await expect.poll(() => page.evaluate(() => document.documentElement.scrollHeight)).toBeGreaterThanOrEqual(oldGeometry.height - 2);
    } finally {
        release();
    }
    await expect(page.getByRole('grid', { name: /Activity by weekday and hour/ })).toBeVisible();
    await expect.poll(() => page.evaluate(() => scrollY)).toBeCloseTo(oldGeometry.y, 0);
    await expect(page.locator('[data-leaderboard-page]')).not.toHaveAttribute('style', /min-height: [1-9]/);
});

test('a failed guest refresh drops old records and releases the temporary page height', async ({ page }) => {
    await page.goto('/browser-tests/species-charts.html?guest');
    await expect(page.getByRole('grid', { name: /Activity by weekday and hour/ })).toBeVisible();
    await page.route('**/api/leaderboard/species?*', route => route.fulfill({ status: 503, json: { detail: 'Unavailable' } }));
    await page.evaluate(() => document.dispatchEvent(new Event('fixture-public-history')));
    await expect(page.getByRole('button', { name: 'Retry', exact: true })).toBeVisible();
    await expect(page.locator('[data-leaderboard-rankings]')).toHaveCount(0);
    await expect(page.locator('[data-leaderboard-page]')).not.toHaveAttribute('style', /min-height: [1-9]/);
});

test('repeated guest refreshes and a new window do not leave a fixed page height', async ({ page }) => {
    await page.goto('/browser-tests/species-charts.html?guest');
    await expect(page.getByRole('grid', { name: /Activity by weekday and hour/ })).toBeVisible();
    for (let index = 0; index < 3; index += 1) {
        await page.evaluate(() => document.dispatchEvent(new Event('fixture-public-history')));
        await expect(page.getByRole('grid', { name: /Activity by weekday and hour/ })).toBeVisible();
        await expect(page.locator('[data-leaderboard-page]')).not.toHaveAttribute('style', /min-height: [1-9]/);
    }
    await page.getByRole('button', { name: 'Week', exact: true }).click();
    await expect(page.getByRole('grid', { name: /Activity by weekday and hour/ })).toBeVisible();
    await expect(page.locator('[data-leaderboard-page]')).not.toHaveAttribute('style', /min-height: [1-9]/);
});

test('the wall shows visits, the share bar lights a species and Escape lets go of a pin', async ({ page }) => {
    wallCaptures = captures(30);
    await page.reload();
    const tiles = page.locator('[data-capture-wall-tile]');
    await expect.poll(() => tiles.count()).toBeGreaterThanOrEqual(24);
    // One Tab stop for the whole wall.
    await expect(page.locator('[data-capture-wall-tile][tabindex="0"]')).toHaveCount(1);

    const robin = page.locator('[data-capture-wall-segment="species"]').first();
    await robin.hover();
    await expect.poll(() => page.locator('[data-capture-wall-tile].lit').count()).toBeGreaterThan(0);
    const lit = await page.locator('[data-capture-wall-tile].lit').evaluateAll(nodes => [...new Set(nodes.map(node => node.getAttribute('data-species')))]);
    expect(lit).toEqual(['Robin']);

    await robin.click();
    await expect(robin).toHaveAttribute('aria-pressed', 'true');
    await expect(page.locator('[data-capture-wall-open]')).toBeVisible();
    await page.mouse.move(0, 0);
    await expect(page.locator('[data-capture-wall-grid].has-active')).toHaveCount(1);
    await page.keyboard.press('Escape');
    await expect(robin).toHaveAttribute('aria-pressed', 'false');
    await expect(page.locator('[data-capture-wall-grid].has-active')).toHaveCount(0);
});

test('a visit opens its pop-out on keyboard focus, arrows move between visits and Escape closes it', async ({ page }) => {
    wallCaptures = captures(30);
    await page.reload();
    const first = page.locator('[data-capture-wall-tile][tabindex="0"]');
    await expect(first).toBeVisible();
    await first.focus();
    await page.keyboard.press('ArrowRight');
    await page.keyboard.press('ArrowLeft');
    await expect(page.locator('[data-capture-wall-popout]')).toBeVisible();
    await expect(page.locator('[data-capture-wall-popout]')).toContainText('Confidence');
    const before = await page.evaluate(() => document.activeElement?.getAttribute('data-capture-wall-tile'));
    await page.keyboard.press('ArrowRight');
    const after = await page.evaluate(() => document.activeElement?.getAttribute('data-capture-wall-tile'));
    expect(after).not.toBe(before);
    await page.keyboard.press('Escape');
    await expect(page.locator('[data-capture-wall-popout]')).toHaveCount(0);
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

async function rainPixels(canvas: Locator): Promise<number[][] | null> {
    return canvas.evaluate(node => {
        const element = node as HTMLCanvasElement & { __chartjs?: { scales: { x: { getPixelForValue(index: number): number } }; chartArea: { top: number }; currentDevicePixelRatio: number } };
        const chart = element.__chartjs;
        const context = element.getContext('2d');
        if (!chart || !context) return null;
        return [3, 0].map(index => Array.from(context.getImageData(
            Math.floor((chart.scales.x.getPixelForValue(index) + 4) * chart.currentDevicePixelRatio),
            Math.floor((chart.chartArea.top + 4) * chart.currentDevicePixelRatio), 1, 1
        ).data));
    });
}

test('the trend chart keeps its set height on a wide screen', async ({ page }) => {
    await page.setViewportSize({ width: 2560, height: 1440 });
    const trend = page.locator('canvas[aria-label^="Detections over time"]');
    await expect(trend).toBeVisible();
    await expect.poll(() => trend.evaluate(node => Boolean((node as HTMLCanvasElement & { __chartjs?: unknown }).__chartjs))).toBe(true);
    // Chart.js sizes the canvas to its box; a box that grows with the canvas balloons to half the width.
    await page.waitForTimeout(400);
    const height = await trend.evaluate(node => node.getBoundingClientRect().height);
    expect(height).toBeGreaterThan(200);
    expect(height).toBeLessThanOrEqual(380);
});
