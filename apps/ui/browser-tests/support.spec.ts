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
    await page.getByRole('link', { name: 'Open Health', exact: true }).click();
    await expect(page.getByLabel('Current route')).toHaveText('/system-health');
    const exportPanel = page.locator('[data-diagnostics-export]');
    await exportPanel.locator('summary').click();
    await expect.poll(() => workspaceReads).toBe(1);
    revision = 31;
    await exportPanel.getByRole('textbox', { name: 'What went wrong? Included in the bundle.' }).fill('Queue remains busy');
    await exportPanel.getByRole('button', { name: 'Capture bundle', exact: true }).click();
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
    await expect(page.getByRole('link', { name: 'Open Health', exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Become guest' }).click();
    await expect(page.getByRole('link', { name: 'Open Health', exact: true })).toHaveCount(0);
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
        await page.getByRole('link', { name: 'Open Health', exact: true }).click();
        const now = page.locator('[data-system-health-now]');
        // This reading carries no memory figure, so the memory reading says so in words as well.
        await expect(now.locator('div', { hasText: 'This app in memory' }).getByText('Not measured', { exact: true })).toBeVisible();
        if (percent === null) {
            await expect(now.locator('div', { hasText: 'Intel GPU now' }).getByText('Not measured', { exact: true })).toBeVisible();
            await expect(now.locator('[data-system-health-measurement-gap]')).toContainText('does not establish a CPU fallback');
        } else {
            await expect(now.getByText('0.0%', { exact: true })).toBeVisible();
            await expect(now.locator('[data-system-health-measurement-gap]')).toHaveCount(0);
        }
    });
}

test('Health says an empty list in one plain sentence and lists every sample it read', async ({ page }) => {
    await page.route(url => url.pathname.startsWith('/api/'), async route => {
        const path = new URL(route.request().url()).pathname;
        if (path.endsWith('/system-telemetry/history')) return route.fulfill({ json: {
            // One sample, just after start-up: the table may show only it, whatever times the axis names.
            points: [{ at: 1_790_000_000, cpu_percent: 25, app_cpu_percent: 8, other_cpu_percent: 17, accelerators: { gpu: null } }],
            accelerators: [{ id: 'gpu', kind: 'gpu', label: 'Intel GPU', scope: 'app', unreadable: null }],
            processes: [], host: { memory_total_bytes: 4096, cpu_count: 4 }, window_seconds: 1800
        } });
        if (path.endsWith('/diagnostics/workspace')) return route.fulfill({ json: {
            health: { status: 'ok' }, backend_diagnostics: { events: [] }, classifier: {}, startup_warnings: []
        } });
        return route.fulfill({ json: { items: [] } });
    });
    await page.goto('/browser-tests/support.html');
    await page.getByRole('link', { name: 'Open Health', exact: true }).click();

    const backend = page.locator('[data-health-backend-diagnostics]');
    const empty = backend.locator('[data-read-state="empty"]');
    await expect(empty).toContainText('recorded no warnings or errors');
    // Inside a panel the state is a line of text, not a box within the card, and has no filler heading.
    await expect(empty).toHaveCSS('border-top-width', '0px');
    await expect(empty).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)');
    await expect(backend.getByText('Nothing here yet')).toHaveCount(0);

    // Figures are lining and tabular everywhere, also where a utility such as tabular-nums sets its own
    // spacing: the display face's old-style figures read "o8:oo" and "1oo%".
    const cpuNow = page.locator('[data-system-health-now] dd').first();
    await expect(cpuNow).toHaveCSS('font-variant-numeric', 'lining-nums tabular-nums');
    await expect(page.locator('[data-system-health]').locator('p').first()).toHaveCSS('font-variant-numeric', 'lining-nums tabular-nums');

    await page.getByText('Show the data as a table').click();
    const rows = page.locator('[data-system-health] figure table tbody tr');
    await expect(rows).toHaveCount(1);
    // The first cell names the row (its time), so the figures follow it as data cells.
    await expect(rows.first().locator('th[scope="row"]')).toHaveCount(1);
    await expect(rows.first().locator('td').nth(0)).toHaveText('25.0%');
    await expect(rows.first().locator('td').nth(1)).toHaveText('Not measured');
});

test('Health renders GPU readings and an isolated 0% dot even when CPU counters are unmeasured (#1088)', async ({ page }) => {
    await page.route(url => url.pathname.startsWith('/api/'), async route => {
        const path = new URL(route.request().url()).pathname;
        if (path.endsWith('/system-telemetry/history')) return route.fulfill({ json: {
            points: [{ at: 1_790_000_000, cpu_percent: null, app_cpu_percent: null, other_cpu_percent: null, accelerators: { gpu: 0 } }],
            accelerators: [{ id: 'gpu', kind: 'gpu', label: 'Intel GPU', scope: 'app', unreadable: null }],
            processes: [], host: { memory_total_bytes: 4096, cpu_count: 4 }, window_seconds: 1800
        } });
        if (path.endsWith('/diagnostics/workspace')) return route.fulfill({ json: {
            health: { status: 'ok' }, backend_diagnostics: { events: [] }, classifier: {}, startup_warnings: []
        } });
        return route.fulfill({ json: { items: [] } });
    });
    await page.goto('/browser-tests/support.html');
    await page.getByRole('link', { name: 'Open Health', exact: true }).click();

    await expect(page.locator('[data-system-health-chart]')).toBeVisible();
    await expect(page.locator('[data-system-health-point="gpu"]')).toHaveCount(1);
    await expect(page.locator('[data-system-health-legend]')).toContainText('Intel GPU');
    await expect(page.locator('[data-system-health-cpu-unmeasured]')).toBeVisible();

    await page.getByText('Show the data as a table').click();
    const row = page.locator('[data-system-health] figure table tbody tr').first();
    await expect(row.locator('td').nth(0)).toHaveText('Not measured');
    await expect(row.locator('td').nth(1)).toHaveText('0.0%');
});

test('Health keeps legend, table, and unreadable accelerator notes visible when all samples are null (#1088)', async ({ page }) => {
    await page.route(url => url.pathname.startsWith('/api/'), async route => {
        const path = new URL(route.request().url()).pathname;
        if (path.endsWith('/system-telemetry/history')) return route.fulfill({ json: {
            points: [{ at: 1_790_000_000, cpu_percent: null, app_cpu_percent: null, other_cpu_percent: null, accelerators: { gpu: null } }],
            accelerators: [
                { id: 'gpu', kind: 'gpu', label: 'Intel GPU', scope: 'app', unreadable: null },
                { id: 'nvidia-0', kind: 'gpu', label: 'NVIDIA GPU', scope: 'device', unreadable: 'nvidia_no_counter' }
            ],
            processes: [], host: { memory_total_bytes: 4096, cpu_count: 4 }, window_seconds: 1800
        } });
        if (path.endsWith('/diagnostics/workspace')) return route.fulfill({ json: {
            health: { status: 'ok' }, backend_diagnostics: { events: [] }, classifier: {}, startup_warnings: []
        } });
        return route.fulfill({ json: { items: [] } });
    });
    await page.goto('/browser-tests/support.html');
    await page.getByRole('link', { name: 'Open Health', exact: true }).click();

    await expect(page.locator('[data-system-health-legend]')).toContainText('Intel GPU');
    await expect(page.locator('[data-system-health-unreadable="nvidia-0"]')).toContainText('NVIDIA GPU');
    await page.getByText('Show the data as a table').click();
    const row = page.locator('[data-system-health] figure table tbody tr').first();
    await expect(row.locator('td').nth(0)).toHaveText('Not measured');
    await expect(row.locator('td').nth(1)).toHaveText('Not measured');
});
