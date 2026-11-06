import { test, expect } from '@playwright/test';

test('owners reach support from Notifications and export fresh server evidence', async ({ page }) => {
    const pageErrors: string[] = [];
    page.on('pageerror', error => pageErrors.push(error.message));
    let revision = 1;
    let denied = false;
    let workspaceReads = 0;
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route(url => url.pathname.startsWith('/api/'), async route => {
        const path = new URL(route.request().url()).pathname;
        if (path.endsWith('/diagnostics/workspace')) {
            expect(route.request().headers().authorization).toBe('Bearer fixture-owner-session');
            workspaceReads++;
            if (denied) return route.fulfill({ status: 503, json: { detail: 'Diagnostics temporarily unavailable' } });
            return route.fulfill({ json: {
                workspace_schema_version: 'support-fixture',
                health: { status: 'ok', version: 'fixture', video_classifier: { pending: revision, active: 0 } },
                backend_diagnostics: { events: [], captured_at: new Date().toISOString() },
                focused_diagnostics: { revision }, classifier: {}, startup_warnings: []
            } });
        }
        if (path.endsWith('/jobs')) return route.fulfill({ json: { items: [], captured_at: new Date().toISOString() } });
        if (path.endsWith('/system-telemetry/history')) return route.fulfill({ json: { points: [], accelerators: [], processes: [], host: { memory_total_bytes: 1024, cpu_count: 1 }, window_seconds: 1800 } });
        if (path.endsWith('/detections')) return route.fulfill({ json: [] });
        return route.fulfill({ json: {} });
    });
    await page.goto('/browser-tests/support.html');
    await page.getByRole('button', { name: /Health.*Diagnostics export/ }).click();
    await expect(page.getByLabel('Current route')).toHaveText('/settings/health');
    const exportPanel = page.locator('[data-diagnostics-export]');
    await exportPanel.locator('summary').click();
    await expect.poll(() => workspaceReads).toBe(1);
    revision = 31;
    await exportPanel.getByRole('textbox', { name: 'What went wrong? Included in the bundle.' }).fill('Queue remains busy');
    await exportPanel.getByRole('button', { name: 'Capture Bundle', exact: true }).click();
    await expect(exportPanel.getByRole('button', { name: 'Download', exact: true })).toBeVisible();
    expect(workspaceReads).toBe(2);
    const savedDownload = page.waitForEvent('download');
    await exportPanel.getByRole('button', { name: 'Download', exact: true }).click();
    const savedStream = await (await savedDownload).createReadStream();
    let savedBody = '';
    if (savedStream) for await (const chunk of savedStream) savedBody += chunk.toString();
    expect(JSON.parse(savedBody)).toMatchObject({
        health: { video_classifier: { pending: 31 } },
        report: { notes: 'Queue remains busy' },
        workspace_snapshot: { focused_diagnostics: { revision: 31 } }
    });
    revision = 0;
    const currentDownload = page.waitForEvent('download');
    await exportPanel.getByRole('button', { name: 'Download without saving' }).click();
    const currentStream = await (await currentDownload).createReadStream();
    let currentBody = '';
    if (currentStream) for await (const chunk of currentStream) currentBody += chunk.toString();
    expect(JSON.parse(currentBody).health.video_classifier.pending).toBe(0);
    expect(workspaceReads).toBe(3);
    denied = true;
    await exportPanel.getByRole('button', { name: 'Download without saving' }).click();
    await expect(exportPanel.getByRole('alert')).toHaveText('Diagnostics temporarily unavailable');
    await expect(exportPanel.getByRole('button', { name: 'Download without saving' })).toBeEnabled();
    // Existing captures remain downloadable even if the server is unavailable.
    await expect(exportPanel.getByRole('button', { name: 'Download', exact: true })).toBeEnabled();
    expect(pageErrors).toEqual([]);
});

test('guests cannot follow the owner support shortcut', async ({ page }) => {
    await page.route(url => url.pathname.startsWith('/api/'), route => route.fulfill({ json: { items: [] } }));
    await page.goto('/browser-tests/support.html');
    await expect(page.getByRole('button', { name: /Health.*Diagnostics export/ })).toBeVisible();
    await page.getByRole('button', { name: 'Become guest' }).click();
    await expect(page.getByRole('button', { name: /Health.*Diagnostics export/ })).toHaveCount(0);
});


for (const percent of [null, 0]) {
    test(`GPU measurement ${percent === null ? 'unavailable' : 'idle'} keeps the loaded provider honest`, async ({ page }) => {
        await page.route(url => url.pathname.startsWith('/api/'), async route => {
            const path = new URL(route.request().url()).pathname;
            if (path.endsWith('/system-telemetry/history')) return route.fulfill({ json: {
                points: [{ at: 10, cpu_percent: 25, app_cpu_percent: 8, other_cpu_percent: 17, accelerators: { gpu: percent } }],
                accelerators: [{ id: 'gpu', kind: 'gpu', label: 'Intel GPU', scope: 'app', unreadable: null }],
                processes: [{ pid: 123, role: 'video_worker', label: 'video-0', cpu_percent: 8, rss_bytes: 1024, accelerator: { kind: 'gpu', label: 'Intel GPU' } }],
                host: { memory_total_bytes: 4096, cpu_count: 4 }, window_seconds: 1800
            } });
            if (path.endsWith('/diagnostics/workspace')) return route.fulfill({ json: {
                health: { status: 'ok' }, backend_diagnostics: { events: [] }, classifier: {}, startup_warnings: []
            } });
            return route.fulfill({ json: { items: [] } });
        });
        await page.goto('/browser-tests/support.html');
        await page.getByRole('button', { name: /Health.*Diagnostics export/ }).click();
        const now = page.locator('[data-system-health-now]');
        if (percent === null) {
            await expect(now.getByText('Not measured', { exact: true })).toBeVisible();
            await expect(now.locator('[data-system-health-measurement-gap]')).toContainText('does not establish a CPU fallback');
        } else {
            await expect(now.getByText('0.0%', { exact: true })).toBeVisible();
            await expect(now.locator('[data-system-health-measurement-gap]')).toHaveCount(0);
        }
    });
}
