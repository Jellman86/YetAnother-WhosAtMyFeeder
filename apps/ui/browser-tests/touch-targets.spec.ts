import { test, expect, type Locator } from '@playwright/test';

async function targetSizes(controls: Locator): Promise<void> {
    await expect(controls.first()).toBeVisible();
    const bounds = await controls.evaluateAll(nodes => nodes.map(node => {
        const { width, height, x, y } = node.getBoundingClientRect();
        return { label: node.getAttribute('aria-label') || node.textContent, width, height, x, y };
    }));
    expect(bounds.length).toBeGreaterThan(0);
    for (const target of bounds) {
        expect(target.width, `${target.label} width`).toBeGreaterThanOrEqual(44);
        expect(target.height, `${target.label} height`).toBeGreaterThanOrEqual(44);
    }
    for (let a = 0; a < bounds.length; a += 1) {
        for (let b = a + 1; b < bounds.length; b += 1) {
            const left = bounds[a], right = bounds[b];
            const overlap = Math.min(left.x + left.width, right.x + right.width) - Math.max(left.x, right.x) > .5
                && Math.min(left.y + left.height, right.y + right.height) - Math.max(left.y, right.y) > .5;
            expect(overlap, `${left.label} overlaps ${right.label}`).toBe(false);
        }
    }
}

for (const textSize of ['standard', 'smallest']) {
test(`navigation targets fit narrow phones and keep distinct hit regions (${textSize} text)`, async ({ page }, testInfo) => {
    // A smaller text size shrinks the type, never the 44px targets.
    await page.addInitScript((size) => localStorage.setItem('text_size', size), textSize);
    await page.setViewportSize({ width: 320, height: 800 });
    await page.route(url => url.pathname.startsWith('/api/'), async route => {
        if (new URL(route.request().url()).pathname === '/api/update-status') {
            await route.fulfill({ json: { update_available: false } });
        } else if (new URL(route.request().url()).pathname === '/api/system-telemetry') {
            await route.fulfill({ status: 503, json: { detail: 'Fixture telemetry unavailable' } });
        } else throw new Error(`Unexpected chrome fixture request: ${route.request().url()}`);
    });
    page.on('pageerror', error => { throw error; });
    await page.goto('/browser-tests/touch-targets.html');
    await targetSizes(page.getByRole('button', { name: /^(Open menu|Switch theme)$/ }));
    await page.getByRole('button', { name: 'Open menu' }).click();
    const sidebar = page.locator('aside');
    await expect(sidebar.getByRole('button', { name: 'Log Out', exact: true })).toBeVisible();
    await targetSizes(sidebar.locator('button:visible'));
    await sidebar.getByRole('button', { name: 'English', exact: true }).click();
    await targetSizes(sidebar.getByRole('menuitem'));
    await sidebar.getByRole('menu').focus();
    await page.keyboard.press('Escape');
    await expect(sidebar.getByRole('menu')).toHaveCount(0);
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`navigation-targets-320-${textSize}.png`), fullPage: true });
    await sidebar.getByRole('button', { name: 'Collapse sidebar', exact: true }).click();
    await targetSizes(sidebar.locator('button:visible'));
});
}

/** Every control in `controls` is at least 44px tall; width is the label's business. */
async function targetHeights(controls: Locator): Promise<void> {
    await expect(controls.first()).toBeVisible();
    const bounds = await controls.evaluateAll(nodes => nodes.map(node => ({
        label: node.getAttribute('aria-label') || node.textContent?.trim(),
        height: node.getBoundingClientRect().height
    })));
    expect(bounds.length).toBeGreaterThan(0);
    for (const target of bounds) expect(target.height, `${target.label} height`).toBeGreaterThanOrEqual(44);
}

async function withoutWebFonts(page: import('@playwright/test').Page): Promise<void> {
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
}

const pixel = '<svg xmlns="http://www.w3.org/2000/svg" width="4" height="4"><rect width="4" height="4" fill="#7a9a6a"/></svg>';

test('page-size arrows and the wizard account controls clear the touch floor', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    page.on('pageerror', error => { throw error; });
    await withoutWebFonts(page);
    await page.route(url => url.pathname.startsWith('/api/'), route => route.fulfill({ status: 503, json: { detail: 'Not part of the kit fixture' } }));
    await page.goto('/browser-tests/touch-targets.html?surface=kit');

    await targetSizes(page.getByRole('button', { name: /^(Previous page|Next page)$/ }));
    // The page-size select is named by its visible label alone (WCAG 2.5.3).
    const pageSize = page.getByRole('combobox', { name: 'Show:' });
    await expect(pageSize).toBeVisible();
    await expect(pageSize).not.toHaveAttribute('aria-label', /.*/);
    await targetHeights(pageSize);

    const account = page.locator('[data-kit-account]');
    await targetHeights(account.locator('label').filter({ has: page.getByRole('checkbox') }));
    await expect(account.getByLabel('Admin username')).toHaveAttribute('autocomplete', 'username');
    await expect(account.getByLabel('Password', { exact: true })).toHaveAttribute('autocomplete', 'new-password');
    await expect(account.getByLabel('Password', { exact: true })).toHaveAccessibleDescription(/At least 8 characters/);
});

test('About quick links and credit links clear the touch floor', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 900 });
    page.on('pageerror', error => { throw error; });
    await withoutWebFonts(page);
    await page.route('**/ready', route => route.fulfill({ json: { status: 'ready', startup_started_at: '2026-09-01T08:00:00Z' } }));
    await page.route(url => url.pathname.startsWith('/api/'), async route => {
        const path = new URL(route.request().url()).pathname;
        if (path === '/api/about/portrait') return route.fulfill({ status: 503, json: { detail: 'No portrait in this fixture' } });
        if (path === '/api/version') return route.fulfill({ json: { version: '2.9.15', base_version: '2.9.15', git_hash: 'fixture', branch: 'dev' } });
        if (path === '/api/about/community') return route.fulfill({ json: { enabled: false, active_installs: null } });
        if (path === '/api/classifier/status') return route.fulfill({ json: { loaded: true, effective_model_id: 'dinov2_b14_inat21_metadata_336', active_provider: 'intel_gpu' } });
        if (path === '/api/stats/uptime') return route.fulfill({ json: { buckets: [], longest_gap_minutes: 0, availability_percent: 100 } });
        if (path === '/api/update-status') return route.fulfill({ json: { enabled: false, update_available: false } });
        return route.fulfill({ status: 503, json: { detail: 'Not part of the About fixture' } });
    });
    await page.goto('/browser-tests/about-portrait.html');
    const credits = page.locator('section[aria-labelledby="about-credits-heading"]');
    await expect(credits).toBeVisible({ timeout: 15000 });
    await targetHeights(credits.getByRole('link'));
    // The model id is an identifier: it wraps inside its step rather than being cut or overflowing.
    const modelStep = page.locator('[data-about-pipeline] li').filter({ hasText: 'dinov2_b14_inat21_metadata_336' });
    await expect(modelStep).toBeVisible();
    expect(await modelStep.evaluate(node => node.scrollWidth <= node.clientWidth)).toBe(true);
});

test('Leaderboard span tabs clear the touch floor and run from day to total', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    page.on('pageerror', error => { throw error; });
    await withoutWebFonts(page);
    const span = { window_start: '2026-09-01T00:00:00Z', window_end: '2026-09-08T00:00:00Z' };
    await page.route(url => url.pathname.startsWith('/api/'), async route => {
        const path = new URL(route.request().url()).pathname;
        if (path === '/api/leaderboard/species') return route.fulfill({ json: { span: 'month', species: [], ...span } });
        if (path === '/api/leaderboard/portraits') return route.fulfill({ json: { span: 'month', portraits: [] } });
        if (path === '/api/stats/detections/timeline') return route.fulfill({ json: { span: 'month', bucket: 'day', points: [], total_count: 0, ...span } });
        if (path === '/api/stats/detections/activity-heatmap') return route.fulfill({ json: { span: 'month', total_count: 0, max_cell_count: 0, cells: [], ...span } });
        if (path === '/api/leaderboard/analysis') return route.fulfill({ status: 204 });
        if (path === '/api/events') return route.fulfill({ json: [] });
        if (path.endsWith('.jpg')) return route.fulfill({ contentType: 'image/svg+xml', body: pixel });
        return route.fulfill({ json: {} });
    });
    await page.goto('/browser-tests/species-charts.html');
    const spans = page.getByRole('group', { name: 'Time span' });
    await expect(spans).toBeVisible({ timeout: 15000 });
    const tabs = spans.getByRole('button');
    await expect(tabs).toHaveText(['Day', 'Week', 'Month', 'Total'].map(name => new RegExp(name)));
    await expect(spans.getByRole('button', { name: /Month/ })).toHaveAttribute('aria-pressed', 'true');
    await targetSizes(tabs);
});

test('the record’s audio context and edit-name controls clear the touch floor', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    page.on('pageerror', error => { throw error; });
    await withoutWebFonts(page);
    await page.route(url => url.pathname.startsWith('/api/'), async route => {
        const path = new URL(route.request().url()).pathname;
        if (path.endsWith('/snapshot/candidates')) return route.fulfill({ json: { candidates: [], birds: [], current_source: 'frigate_snapshot' } });
        if (path.endsWith('/snapshot/status')) return route.fulfill({ json: { available: true, high_quality_bird_crop_enabled: true, source: 'frigate_snapshot' } });
        if (path.endsWith('.jpg')) return route.fulfill({ contentType: 'image/svg+xml', body: pixel });
        if (path.startsWith('/api/audio/context/') || path === '/api/species/search' || path.includes('/conversation')) return route.fulfill({ json: [] });
        if (path.endsWith('/classifier/status')) return route.fulfill({ json: { ready: true } });
        return route.fulfill({ json: {} });
    });
    await page.goto('/browser-tests/modal-text-layout.html?controls=true');
    const modal = page.locator('[data-detection-detail-modal]');
    await expect(modal).toBeVisible({ timeout: 15000 });
    const audio = modal.getByRole('button', { name: /^Audio context/ });
    await expect(audio).toHaveAttribute('aria-expanded', 'false');
    const editName = modal.getByRole('button', { name: 'Edit name' });
    await targetHeights(audio);
    await targetHeights(editName);
    await audio.click();
    await expect(audio).toHaveAttribute('aria-expanded', 'true');
});
