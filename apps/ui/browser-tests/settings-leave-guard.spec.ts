import { expect, test, type Page } from '@playwright/test';

// Unsaved Settings edits are not thrown away without a word. Through the real App shell: choosing
// another page, Back, and reloading all ask first, while moving between Settings tabs keeps the
// draft without asking.

async function openOwnerShell(page: Page, start = '/settings/connection'): Promise<void> {
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
        return route.fulfill({ status: 503, json: { detail: 'Unavailable in leave guard fixture' } });
    });
    await page.route('**/health', route => route.fulfill({ json: { status: 'healthy' } }));
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto(start);
    if (start.startsWith('/settings')) await expect(page.locator('#mqtt-server')).toHaveValue('mqtt');
}

const pathname = (page: Page) => new URL(page.url()).pathname;
const leaveDialog = (page: Page) => page.getByRole('alertdialog', { name: 'Leave without saving?' });
const dashboardLink = (page: Page) => page.locator('aside').getByRole('button', { name: 'Dashboard', exact: true });

test('choosing another page with unsaved changes asks first; Cancel keeps the edit, Leave goes', async ({ page }) => {
    await openOwnerShell(page);
    await page.locator('#mqtt-server').fill('broker.lan');

    // Another Settings tab keeps the draft and does not ask.
    await page.locator('[data-settings-navigation]').getByRole('link', { name: 'Security', exact: true }).click();
    await expect.poll(() => pathname(page)).toBe('/settings/security');
    await expect(leaveDialog(page)).toHaveCount(0);
    await page.locator('[data-settings-navigation]').getByRole('link', { name: 'Connection', exact: true }).click();
    await expect(page.locator('#mqtt-server')).toHaveValue('broker.lan');

    await dashboardLink(page).click();
    await expect(leaveDialog(page)).toBeVisible();
    await expect(leaveDialog(page)).toContainText('Connection');
    await leaveDialog(page).getByRole('button', { name: 'Cancel', exact: true }).click();
    await expect(leaveDialog(page)).toHaveCount(0);
    expect(pathname(page)).toBe('/settings/connection');
    await expect(page.locator('#mqtt-server')).toHaveValue('broker.lan');

    await dashboardLink(page).click();
    await leaveDialog(page).getByRole('button', { name: 'Leave without saving', exact: true }).click();
    await expect.poll(() => pathname(page)).toBe('/');
});

test('Back with unsaved changes asks first, keeps Settings open on Cancel, and leaves when confirmed', async ({ page }) => {
    await openOwnerShell(page, '/');
    await page.locator('aside').getByRole('button', { name: 'Settings', exact: true }).click();
    await expect(page.locator('#mqtt-server')).toHaveValue('mqtt');
    await page.locator('#mqtt-server').fill('broker.lan');

    await page.goBack();
    await expect(leaveDialog(page)).toBeVisible();
    await leaveDialog(page).getByRole('button', { name: 'Cancel', exact: true }).click();
    await expect.poll(() => pathname(page)).toBe('/settings/connection');
    await expect(page.locator('#mqtt-server')).toHaveValue('broker.lan');

    await page.goBack();
    await leaveDialog(page).getByRole('button', { name: 'Leave without saving', exact: true }).click();
    await expect.poll(() => pathname(page)).toBe('/');
    await expect(page.locator('#mqtt-server')).toHaveCount(0);
});

test('reloading with unsaved changes asks the browser to confirm, and without them does not', async ({ page }) => {
    await openOwnerShell(page);
    const asked: string[] = [];
    page.on('dialog', dialog => {
        asked.push(dialog.type());
        void dialog.dismiss();
    });
    await page.locator('#mqtt-server').fill('broker.lan');
    // A dismissed unload prompt cancels the reload, so its promise never settles.
    void page.reload().catch(() => undefined);
    await expect.poll(() => asked).toEqual(['beforeunload']);
    await expect(page.locator('#mqtt-server')).toHaveValue('broker.lan');

    await page.locator('#mqtt-server').fill('mqtt');
    await page.reload();
    await expect(page.locator('#mqtt-server')).toHaveValue('mqtt');
    expect(asked).toEqual(['beforeunload']);
});

test('every Settings tab opens with nothing unsaved on a sparse saved copy', async ({ page }) => {
    await openOwnerShell(page);
    const tabs = ['Connection', 'Detection', 'Integrations', 'Enrichment', 'AI', 'Notifications', 'Security', 'Beta features', 'Data', 'Appearance', 'Accessibility'];
    for (const tab of tabs) {
        await page.locator('[data-settings-navigation]').getByRole('link', { name: tab, exact: true }).click();
        await expect(page.locator('[data-settings-navigation] [aria-current="page"]')).toHaveText(tab);
        await page.waitForTimeout(200);
        await expect(page.getByRole('region', { name: 'Unsaved changes' }), `${tab} looked unsaved on open`).toHaveCount(0);
    }
});
