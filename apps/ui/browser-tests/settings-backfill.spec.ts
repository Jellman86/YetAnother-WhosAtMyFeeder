import { test, expect } from '@playwright/test';

for (const terminal of ['completed', 'failed'] as const) {
    test(`opening Settings does not announce historical ${terminal} backfills`, async ({ page }) => {
        const errors: string[] = [];
        page.on('pageerror', error => errors.push(error.message));
        let reads = 0;
        await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ body: '' }));
        await page.route('https://fonts.gstatic.com/**', route => route.abort());
        await page.route(url => url.pathname.startsWith('/api/'), route => {
            const url = new URL(route.request().url());
            if (url.pathname.endsWith('/backfill/status')) {
                reads++;
                return route.fulfill({ json: {
                    id: `old-${url.searchParams.get('kind')}`, status: terminal,
                    processed: 657, total: 657, new_detections: 656, updated: 657,
                    skipped: 0, errors: terminal === 'failed' ? 1 : 0,
                    message: 'Historical backfill result', skipped_reasons: {}, error_reasons: {}
                } });
            }
            if (url.pathname === '/api/settings') return route.fulfill({ json: { frigate_url: 'http://frigate:5000', mqtt_server: 'mqtt', mqtt_port: 1883, mqtt_auth: false, classification_threshold: 0.7 } });
            if (url.pathname.endsWith('/audio/sources')) return route.fulfill({ json: [] });
            if (url.pathname.endsWith('/frigate/config')) return route.fulfill({ json: { cameras: {} } });
            return route.fulfill({ json: {} });
        });
        await page.goto('/browser-tests/settings-backfill.html');
        await expect.poll(() => reads).toBe(2);
        await expect(page.getByRole('button', { name: 'Setup wizard', exact: true })).toBeVisible();
        await expect(page.locator('[data-toast-container]')).toHaveText('', { timeout: 1000 });
        await page.getByRole('button', { name: 'Leave Settings', exact: true }).click();
        await page.getByRole('button', { name: 'Open Settings', exact: true }).click();
        await expect.poll(() => reads).toBe(4);
        await expect(page.locator('[data-toast-container]')).toHaveText('', { timeout: 1000 });
        reads = 0;
        await page.reload();
        await expect.poll(() => reads).toBe(2);
        await expect(page.locator('[data-toast-container]')).toHaveText('', { timeout: 1000 });
        expect(errors).toEqual([]);
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    });
}

for (const kind of ['detections', 'weather'] as const) {
    for (const terminal of ['completed', 'failed'] as const) {
        test(`${kind} backfill announces a new ${terminal} transition once`, async ({ page }) => {
            const errors: string[] = [];
            page.on('pageerror', error => errors.push(error.message));
            let finished = false;
            let terminalReads = 0;
            await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ body: '' }));
            await page.route('https://fonts.gstatic.com/**', route => route.abort());
            await page.route(url => url.pathname.startsWith('/api/'), route => {
                const url = new URL(route.request().url());
                if (url.pathname.endsWith('/backfill/status')) {
                    if (url.searchParams.get('kind') !== kind) return route.fulfill({ json: null });
                    if (finished) terminalReads++;
                    return route.fulfill({ json: {
                        id: 'current-job', status: finished ? terminal : 'running',
                        processed: finished ? 10 : 2, total: 10, new_detections: 10,
                        updated: 10, skipped: 0, errors: terminal === 'failed' ? 1 : 0,
                        message: finished ? 'New backfill result' : 'Working',
                        skipped_reasons: {}, error_reasons: {}
                    } });
                }
                if (url.pathname === '/api/settings') return route.fulfill({ json: { frigate_url: 'http://frigate:5000', mqtt_server: 'mqtt', mqtt_port: 1883, mqtt_auth: false, classification_threshold: 0.7 } });
                if (url.pathname.endsWith('/audio/sources')) return route.fulfill({ json: [] });
                if (url.pathname.endsWith('/frigate/config')) return route.fulfill({ json: { cameras: {} } });
                return route.fulfill({ json: {} });
            });
            await page.goto('/browser-tests/settings-backfill.html');
            await expect(page.getByRole('button', { name: 'Setup wizard', exact: true })).toBeVisible();
            await expect(page.locator('[data-toast-container]')).toHaveText('');
            finished = true;
            await expect.poll(() => terminalReads).toBe(1);
            const toast = page.locator('[data-toast-container]');
            await expect(toast).toContainText('New backfill result');
            await expect(toast.getByRole('button', { name: 'Close notification' })).toHaveCount(1);
            await toast.getByRole('button', { name: 'Close notification' }).click();
            await page.getByRole('button', { name: 'Leave Settings', exact: true }).click();
            await page.getByRole('button', { name: 'Open Settings', exact: true }).click();
            await expect.poll(() => terminalReads).toBe(2);
            await expect(toast).toHaveText('', { timeout: 1000 });
            expect(errors).toEqual([]);
        });
    }
}
