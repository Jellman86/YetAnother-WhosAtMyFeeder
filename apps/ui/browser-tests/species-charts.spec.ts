import { test, expect } from '@playwright/test';

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

let capturedImage: string | null;
test.beforeEach(async ({ page }) => {
    capturedImage = null;
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
    await expect(page.getByRole('group', { name: 'Hour x weekday activity' }).getByRole('button')).toHaveCount(168);
    await expect(page.getByRole('button', { name: 'Mon 08:00: 12' })).toBeVisible();

    await page.getByRole('button', { name: 'Hide Robin' }).focus();
    await page.keyboard.press('Enter');
    await expect.poll(() => donut.evaluate(node => (node as HTMLCanvasElement & { __chartjs?: { getDataVisibility(index: number): boolean } }).__chartjs?.getDataVisibility(0))).toBe(false);
    await expect(page.getByRole('button', { name: 'Show Robin' })).toHaveAttribute('aria-pressed', 'false');

    await page.getByRole('button', { name: 'Toggle theme' }).click();
    await expect(page.getByRole('button', { name: 'Hide Robin' })).toHaveAttribute('aria-pressed', 'true');
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
    await page.getByRole('button', { name: 'Show precip' }).click();
    await expect.poll(() => trend.evaluate(node => {
        const chart = (node as HTMLCanvasElement & { __chartjs?: { data: { datasets: Array<{ yAxisID?: string }> }; scales: Record<string, unknown> } }).__chartjs;
        return {
            axes: chart?.data.datasets.map(dataset => dataset.yAxisID),
            scales: Object.keys(chart?.scales ?? {}).sort(),
        };
    })).toEqual({ axes: ['y', 'y', 'y', 'y', 'temperature', 'wind'], scales: ['temperature', 'wind', 'x', 'y'] });

    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.reload();
    await expect.poll(() => trend.evaluate(node => (node as HTMLCanvasElement & { __chartjs?: { options: { animation: unknown } } }).__chartjs?.options.animation)).toBe(false);
});
