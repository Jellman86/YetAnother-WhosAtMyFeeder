import { expect, test, type Page } from '@playwright/test';

// The address decides the Settings section through the real App shell. Older and loose addresses,
// including every former tab's, are rewritten to the section's canonical address in place, with the
// former tab as the anchor, so the visible section and the URL always agree.

async function openOwnerShell(page: Page, saved: Record<string, unknown> = {}): Promise<string[]> {
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route(url => url.pathname.startsWith('/api/'), route => {
        const path = new URL(route.request().url()).pathname;
        const responses: Record<string, unknown> = {
            '/api/auth/status': { auth_required: false, is_authenticated: true, needs_initial_setup: false },
            // The backend always sends the naming threshold; Identifying birds binds it.
            '/api/settings': { frigate_url: 'http://frigate:5000', mqtt_server: 'mqtt', mqtt_port: 1883, mqtt_auth: false, cameras: ['patio'], classification_threshold: 0.7, ...saved },
            '/api/update-status': { update_available: false },
        };
        if (path in responses) return route.fulfill({ json: responses[path] });
        return route.fulfill({ status: 503, json: { detail: 'Unavailable in settings route fixture' } });
    });
    // The backend's own /health only: a glob would also answer the /settings/health page.
    await page.route((url) => url.pathname === '/health', route => route.fulfill({ json: { status: 'healthy' } }));
    await page.setViewportSize({ width: 1280, height: 900 });
    return errors;
}

const settingsNav = (page: Page) => page.locator('[data-settings-navigation]');
const pathname = (page: Page) => new URL(page.url()).pathname;

const hash = (page: Page) => new URL(page.url()).hash;

async function expectSection(page: Page, path: string, label: string, anchor = ''): Promise<void> {
    await expect.poll(() => pathname(page)).toBe(path);
    await expect.poll(() => hash(page)).toBe(anchor);
    await expect(settingsNav(page).getByRole('link', { name: label, exact: true })).toHaveAttribute('aria-current', 'page');
    await expect(settingsNav(page).locator('[aria-current="page"]')).toHaveCount(1);
}

test('older and loose Settings addresses open the section they name at its canonical address', async ({ page }) => {
    await openOwnerShell(page);
    for (const [address, path, label, anchor] of [
        ['/settings', '/settings/cameras', 'Cameras & connection', ''],
        ['/settings/', '/settings/cameras', 'Cameras & connection', ''],
        ['/settings#notifications', '/settings/alerts', 'Alerts', '#notifications'],
        ['/settings/debug', '/settings/identification', 'Identifying birds', '#models'],
        ['/settings/security/', '/settings/sharing', 'Sharing & integrations', '#security'],
        ['/settings/not-a-tab', '/settings/cameras', 'Cameras & connection', ''],
        ['/settings/display', '/settings/display', 'Display', '']
    ] as const) {
        await page.goto(address);
        await expectSection(page, path, label, anchor);
    }
});

test('a former tab\'s address lands on its part inside the section, below the parts before it', async ({ page }) => {
    await openOwnerShell(page);
    await page.goto('/settings/maintenance');
    await expectSection(page, '/settings/storage', 'Storage & upkeep', '#maintenance');
    const part = page.locator('[data-settings-part="maintenance"]');
    await expect(part.getByRole('heading', { level: 2 }).first()).toBeVisible();
    // Scrolled to: the part starts at or near the top of the window, not below the Data part.
    await expect.poll(async () => Math.round((await part.boundingBox())?.y ?? 9999)).toBeLessThan(200);
});

/** The part is where the window was scrolled to: at its top, or as far as the page can scroll. */
async function expectAtPart(page: Page, part: string): Promise<void> {
    await expect.poll(() => page.evaluate((name) => {
        const element = document.querySelector(`[data-settings-part="${name}"]`);
        if (!element) return 'missing';
        const top = element.getBoundingClientRect().top;
        const atBottom = Math.ceil(window.scrollY + window.innerHeight) >= document.documentElement.scrollHeight - 2;
        // A few pixels either way: the sticky save bar's scroll padding and late image sizes nudge it.
        return top > -16 && (top < 120 || atBottom) ? 'there' : `top at ${Math.round(top)}`;
    }, part), { timeout: 10_000 }).toBe('there');
}

test('one part after another in a section lands on each, and Back and Forward land on them again', async ({ page }) => {
    const errors = await openOwnerShell(page);
    await page.goto('/settings/identification#models');
    await expectSection(page, '/settings/identification', 'Identifying birds', '#models');
    await expectAtPart(page, 'models');

    // A fragment followed on the page (a link, or typed), then back to the first.
    await page.evaluate(() => { location.hash = '#beta'; });
    await expectAtPart(page, 'beta');
    await page.evaluate(() => { location.hash = '#models'; });
    await expectAtPart(page, 'models');

    await page.goBack();
    await expect.poll(() => hash(page)).toBe('#beta');
    await expectAtPart(page, 'beta');
    await page.goForward();
    await expect.poll(() => hash(page)).toBe('#models');
    await expectAtPart(page, 'models');
    // The section's first part is the top of the page.
    await page.evaluate(() => { location.hash = '#detection'; });
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0);
    expect(errors).toEqual([]);
});

test('landing on a part below a paused video check keeps the alert that says so in view', async ({ page }) => {
    await openOwnerShell(page, { auto_video_classification: true, video_classification_circuit_open: true, video_classification_circuit_failures: 3 });
    await page.goto('/settings/detection');
    await expectSection(page, '/settings/identification', 'Identifying birds', '#detection');
    const alert = page.locator('[data-video-circuit]');
    await expect(alert).toBeVisible();
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0);
    expect(await alert.evaluate((node) => node.getBoundingClientRect().top >= 0)).toBe(true);
});

test('a loose address keeps its part when it is rewritten, so a reload lands there again', async ({ page }) => {
    await openOwnerShell(page);
    await page.goto('/settings/sharing/#security');
    await expectSection(page, '/settings/sharing', 'Sharing & integrations', '#security');
    await expectAtPart(page, 'security');
    await page.reload();
    await expectSection(page, '/settings/sharing', 'Sharing & integrations', '#security');
    await expectAtPart(page, 'security');
});

test('Health is a page of its own, and the old Settings addresses open it', async ({ page }) => {
    await openOwnerShell(page);
    for (const address of ['/settings/health', '/settings#health', '/settings/#health', '/settings/errors', '/notifications/errors']) {
        await page.goto(address);
        // The first open compiles the Health page on the dev server, which is slow under load.
        await expect.poll(() => pathname(page), { timeout: 15_000 }).toBe('/system-health');
        await expect(page.getByRole('heading', { level: 1, name: 'Health' })).toBeVisible();
    }
    await expect(page.locator('#app-sidebar').getByRole('button', { name: 'Health', exact: true })).toHaveAttribute('aria-current', 'page');
    await expect(settingsNav(page)).toHaveCount(0);
});

test('choosing a section, Back and a later non-canonical address all keep the section and the URL together', async ({ page }) => {
    const errors = await openOwnerShell(page);
    await page.goto('/settings/cameras');
    await expectSection(page, '/settings/cameras', 'Cameras & connection');

    await settingsNav(page).getByRole('link', { name: 'Sharing & integrations', exact: true }).click();
    await expectSection(page, '/settings/sharing', 'Sharing & integrations');

    await page.goBack();
    await expectSection(page, '/settings/cameras', 'Cameras & connection');

    // An address that arrives after Settings mounted (a bookmark reached by Back) is rewritten too.
    await page.evaluate(() => {
        history.pushState(null, '', '/settings/not-a-tab');
        dispatchEvent(new PopStateEvent('popstate'));
    });
    await expectSection(page, '/settings/cameras', 'Cameras & connection');
    expect(errors).toEqual([]);
});
