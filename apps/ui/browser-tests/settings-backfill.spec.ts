import { test, expect, type Page } from '@playwright/test';

// Settings reads the repair jobs' status on the Data tab, which shows them, and follows a job the
// pushed status says is running on whichever tab is open, so its end is announced wherever you are.

/** A status push saying this backfill is running, as the live stream delivers it in the app. */
async function pushRunningBackfill(page: Page, kind: 'detections' | 'weather'): Promise<void> {
    await page.evaluate((jobKind) => {
        const store = (window as unknown as { __systemStatus: { ingest(snapshot: unknown): void; snapshot: { revision: number } | null } }).__systemStatus;
        const now = new Date().toISOString();
        store.ingest({
            revision: (store.snapshot?.revision ?? 0) + 1,
            generated_at: now,
            startup_instance_id: 'fixture',
            version: 'fixture',
            overall: { state: 'ok', cause: 'ok', subsystem: null },
            subsystems: [],
            jobs_summary: { running: 1, queued: 0, progress: null },
            jobs: { captured_at: now, items: [{ id: 'current-job', kind: jobKind, title: 'Backfill', status: 'running', current: 2, total: 10, updated_at: now }], lanes: [] },
            analysis: { pending: 0, active: 0, circuit_open: false },
            model: { state: 'ok', cause: 'ready', revision: 'fixture' },
            connections: null,
            cameras: null,
            telemetry: null,
            diagnostics_revision: 0,
            incident_revision: 'fixture',
            health_revision: 'fixture'
        });
    }, kind === 'detections' ? 'backfill' : 'weather_backfill');
}

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
        await page.goto('/browser-tests/settings-backfill.html?route=/settings/data');
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
            let runningReads = 0;
            await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ body: '' }));
            await page.route('https://fonts.gstatic.com/**', route => route.abort());
            await page.route(url => url.pathname.startsWith('/api/'), route => {
                const url = new URL(route.request().url());
                if (url.pathname.endsWith('/backfill/status')) {
                    if (url.searchParams.get('kind') !== kind) return route.fulfill({ json: null });
                    if (finished) terminalReads++;
                    else runningReads++;
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
            await pushRunningBackfill(page, kind);
            // The job is seen running before it finishes, so its end is a new transition.
            await expect.poll(() => runningReads).toBeGreaterThan(0);
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
