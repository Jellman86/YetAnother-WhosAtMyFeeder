import { test, expect } from '@playwright/test';

for (const outcome of ['success', 'failure'] as const) {
    test(`storage retry shows progress immediately and handles ${outcome}`, async ({ page }) => {
        let reads = 0;
        let completed = false;
        await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ body: '' }));
        await page.route('https://fonts.gstatic.com/**', route => route.abort());
        await page.route(url => url.pathname.startsWith('/api/'), async route => {
            const path = new URL(route.request().url()).pathname;
            if (path === '/api/cache/measurement') {
                if (!new URL(route.request().url()).searchParams.has('measurement_id')) {
                    reads++;
                    if (reads === 1) return route.fulfill({ status: 504, body: 'Gateway timeout' });
                }
                return route.fulfill({ json: {
                    id: 'retry', status: completed ? (outcome === 'success' ? 'completed' : 'failed') : 'running',
                    stats: completed && outcome === 'success' ? { total_size_mb: 184320, storage_available: true } : null
                } });
            }
            if (path === '/api/settings') return route.fulfill({ json: { frigate_url: 'http://frigate:5000', mqtt_server: 'mqtt', mqtt_port: 1883, mqtt_auth: false, classification_threshold: 0.7 } });
            if (path.endsWith('/audio/sources')) return route.fulfill({ json: [] });
            if (path.endsWith('/frigate/config')) return route.fulfill({ json: { cameras: {} } });
            return route.fulfill({ json: {} });
        });
        await page.goto('/browser-tests/settings-backfill.html');
        await page.getByRole('link', { name: 'Data', exact: true }).click();
        await expect(page.locator('[data-cache-size-unavailable]')).toBeVisible();
        await page.locator('[data-cache-size-retry]').click();
        await expect.poll(() => reads).toBe(2);
        await expect(page.locator('[data-cache-size-unavailable]')).toHaveCount(0);
        await expect(page.locator('[data-cache-size-loading]')).toHaveText('Measuring…');
        await expect(page.locator('[data-cache-size-retry]')).toHaveCount(0);
        completed = true;
        if (outcome === 'success') {
            await expect(page.locator('[data-cache-size]')).toHaveText('184320 MB');
        } else {
            await expect(page.locator('[data-cache-size-unavailable]')).toContainText("Couldn't load");
            await expect(page.locator('[data-cache-size-retry]')).toBeVisible();
        }
        await expect(page.locator('[data-cache-size-loading]')).toHaveCount(0);
        expect(reads).toBe(2);
    });
}
