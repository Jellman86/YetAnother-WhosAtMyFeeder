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

test.beforeEach(async ({ page }) => {
    await page.route(url => url.pathname.startsWith('/api/'), async route => {
        const path = new URL(route.request().url()).pathname;
        if (path === '/api/audio/history') {
            await route.fulfill({ json: { items: [], total: 0, limit: 25, offset: 0 } });
        } else if (path === '/api/audio/summary') {
            await route.fulfill({ json: summary });
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
    await expect(canvases).toHaveCount(3);
    await expect.poll(() => canvases.evaluateAll(nodes => nodes.map(node => Boolean((node as HTMLCanvasElement & { __chartjs?: unknown }).__chartjs)))).toEqual([true, true, true]);

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

    for (const canvas of [canvases.nth(0), canvases.nth(1)]) {
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

    const donut = canvases.nth(2);
    const legend = await donut.evaluate(node => {
        const chart = (node as HTMLCanvasElement & { __chartjs?: { legend?: { legendHitBoxes?: Array<{ left: number; top: number; width: number; height: number }> } } }).__chartjs;
        return chart?.legend?.legendHitBoxes?.[0] ?? null;
    });
    expect(legend).not.toBeNull();
    await donut.click({ position: { x: legend!.left + legend!.width / 2, y: legend!.top + legend!.height / 2 } });
    await expect.poll(() => donut.evaluate(node => (node as HTMLCanvasElement & { __chartjs?: { getDataVisibility(index: number): boolean } }).__chartjs?.getDataVisibility(0))).toBe(false);

    await expect(page.locator('html')).toHaveClass(/dark/);
    await page.screenshot({ path: testInfo.outputPath('audio-charts-dark.png'), fullPage: true });
    await page.getByRole('button', { name: 'Toggle theme' }).click();
    await expect(page.locator('html')).not.toHaveClass(/dark/);
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath('audio-charts.png'), fullPage: true });
});

test('audio charts respect reduced motion', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.reload();
    const canvases = page.locator('[data-audio-history-analytics] canvas');
    await expect(canvases).toHaveCount(3);
    await expect.poll(() => canvases.evaluateAll(nodes => nodes.map(node => {
        const chart = (node as HTMLCanvasElement & { __chartjs?: { options: { animation: unknown } } }).__chartjs;
        return chart?.options.animation === false;
    }))).toEqual([true, true, true]);
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
    const donut = page.locator('[data-audio-history-analytics] canvas').nth(2);
    await expect.poll(() => donut.evaluate(node => {
        const chart = (node as HTMLCanvasElement & { __chartjs?: { data: { labels: string[] }; chartArea: { top: number; bottom: number } } }).__chartjs;
        return chart?.data.labels.length === 8 ? chart.chartArea.bottom - chart.chartArea.top : 0;
    })).toBeGreaterThan(70);
    await page.screenshot({ path: testInfo.outputPath('audio-charts-full-legend.png'), fullPage: true });
});
