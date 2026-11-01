import { expect, test, type Page } from '@playwright/test';

// The address decides the Settings tab through the real App shell. Older and loose addresses are
// rewritten to the tab's canonical address in place, so the visible tab and the URL always agree.

async function openOwnerShell(page: Page): Promise<string[]> {
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route(url => url.pathname.startsWith('/api/'), route => {
        const path = new URL(route.request().url()).pathname;
        const responses: Record<string, unknown> = {
            '/api/auth/status': { auth_required: false, is_authenticated: true, needs_initial_setup: false },
            '/api/settings': { frigate_url: 'http://frigate:5000', mqtt_server: 'mqtt', mqtt_port: 1883, mqtt_auth: false, cameras: ['patio'] },
            '/api/update-status': { update_available: false },
        };
        if (path in responses) return route.fulfill({ json: responses[path] });
        return route.fulfill({ status: 503, json: { detail: 'Unavailable in settings route fixture' } });
    });
    await page.route('**/health', route => route.fulfill({ json: { status: 'healthy' } }));
    await page.setViewportSize({ width: 1280, height: 900 });
    return errors;
}

const settingsNav = (page: Page) => page.locator('[data-settings-navigation]');
const pathname = (page: Page) => new URL(page.url()).pathname;

async function expectTab(page: Page, path: string, label: string): Promise<void> {
    await expect.poll(() => pathname(page)).toBe(path);
    await expect(settingsNav(page).getByRole('link', { name: label, exact: true })).toHaveAttribute('aria-current', 'page');
    await expect(settingsNav(page).locator('[aria-current="page"]')).toHaveCount(1);
}

test('older and loose Settings addresses open the tab they name at its canonical address', async ({ page }) => {
    await openOwnerShell(page);
    for (const [address, path, label] of [
        ['/settings', '/settings/connection', 'Connection'],
        ['/settings/', '/settings/connection', 'Connection'],
        ['/settings#notifications', '/settings/notifications', 'Notifications'],
        ['/settings/errors', '/settings/health', 'Health'],
        ['/settings/security/', '/settings/security', 'Security'],
        ['/settings/not-a-tab', '/settings/connection', 'Connection'],
    ] as const) {
        await page.goto(address);
        await expectTab(page, path, label);
    }
});

test('choosing a tab, Back and a later non-canonical address all keep the tab and the URL together', async ({ page }) => {
    const errors = await openOwnerShell(page);
    await page.goto('/settings/connection');
    await expectTab(page, '/settings/connection', 'Connection');

    await settingsNav(page).getByRole('link', { name: 'Security', exact: true }).click();
    await expectTab(page, '/settings/security', 'Security');

    await page.goBack();
    await expectTab(page, '/settings/connection', 'Connection');

    // An address that arrives after Settings mounted (a bookmark reached by Back) is rewritten too.
    await page.evaluate(() => {
        history.pushState(null, '', '/settings/not-a-tab');
        dispatchEvent(new PopStateEvent('popstate'));
    });
    await expectTab(page, '/settings/connection', 'Connection');
    expect(errors).toEqual([]);
});
