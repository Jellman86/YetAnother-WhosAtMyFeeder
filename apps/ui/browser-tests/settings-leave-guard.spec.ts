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

const historyLength = (page: Page) => page.evaluate(() => window.history.length);

// History is Dashboard → Settings, with an unsaved edit on Settings.
async function editSettingsAfterDashboard(page: Page): Promise<number> {
    await openOwnerShell(page, '/');
    await page.locator('aside').getByRole('button', { name: 'Settings', exact: true }).click();
    await expect(page.locator('#mqtt-server')).toHaveValue('mqtt');
    await page.locator('#mqtt-server').fill('broker.lan');
    return historyLength(page);
}

test('Back with unsaved changes asks first; Cancel restores Settings without adding or losing history entries', async ({ page }) => {
    const length = await editSettingsAfterDashboard(page);

    await page.goBack();
    await expect(leaveDialog(page)).toBeVisible();
    await leaveDialog(page).getByRole('button', { name: 'Cancel', exact: true }).click();
    await expect.poll(() => pathname(page)).toBe('/settings/connection');
    await expect(page.locator('#mqtt-server')).toHaveValue('broker.lan');
    expect(await historyLength(page)).toBe(length);

    // The entry behind Settings is still the Dashboard: leaving lands there, and Forward returns.
    await page.goBack();
    await leaveDialog(page).getByRole('button', { name: 'Leave without saving', exact: true }).click();
    await expect.poll(() => pathname(page)).toBe('/');
    expect(await historyLength(page)).toBe(length);
    await page.goForward();
    await expect.poll(() => pathname(page)).toBe('/settings/connection');
    await expect(page.locator('#mqtt-server')).toHaveValue('mqtt');
});

test('Forward with unsaved changes asks first; Cancel keeps the forward entry, so Forward still works', async ({ page }) => {
    const settingsLength = await editSettingsAfterDashboard(page);
    // Settings → Dashboard (clean), then Back to Settings, edit: Dashboard is now a forward entry.
    await page.locator('#mqtt-server').fill('mqtt');
    await dashboardLink(page).click();
    await expect.poll(() => pathname(page)).toBe('/');
    const length = await historyLength(page);
    expect(length).toBe(settingsLength + 1);
    await page.goBack();
    await expect.poll(() => pathname(page)).toBe('/settings/connection');
    await page.locator('#mqtt-server').fill('broker.lan');

    await page.goForward();
    await expect(leaveDialog(page)).toBeVisible();
    await leaveDialog(page).getByRole('button', { name: 'Cancel', exact: true }).click();
    await expect.poll(() => pathname(page)).toBe('/settings/connection');
    await expect(page.locator('#mqtt-server')).toHaveValue('broker.lan');
    expect(await historyLength(page)).toBe(length);

    await page.goForward();
    await leaveDialog(page).getByRole('button', { name: 'Leave without saving', exact: true }).click();
    await expect.poll(() => pathname(page)).toBe('/');
    expect(await historyLength(page)).toBe(length);
    // Back from the Dashboard still reaches Settings, then the Dashboard before it.
    await page.goBack();
    await expect.poll(() => pathname(page)).toBe('/settings/connection');
    await page.goBack();
    await expect.poll(() => pathname(page)).toBe('/');
});

test('repeated cancelled history steps never grow or shrink the history', async ({ page }) => {
    const length = await editSettingsAfterDashboard(page);
    for (let attempt = 0; attempt < 3; attempt += 1) {
        await page.goBack();
        await expect(leaveDialog(page)).toBeVisible();
        await leaveDialog(page).getByRole('button', { name: 'Cancel', exact: true }).click();
        await expect.poll(() => pathname(page)).toBe('/settings/connection');
        expect(await historyLength(page)).toBe(length);
    }
    await expect(page.locator('#mqtt-server')).toHaveValue('broker.lan');
    await page.goBack();
    await leaveDialog(page).getByRole('button', { name: 'Leave without saving', exact: true }).click();
    await expect.poll(() => pathname(page)).toBe('/');
    expect(await historyLength(page)).toBe(length);
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
    const tabs = ['Connection', 'Detection', 'Integrations', 'AI', 'Notifications', 'Security', 'Beta features', 'Data', 'Appearance', 'Accessibility'];
    for (const tab of tabs) {
        await page.locator('[data-settings-navigation]').getByRole('link', { name: tab, exact: true }).click();
        await expect(page.locator('[data-settings-navigation] [aria-current="page"]')).toHaveText(tab);
        await page.waitForTimeout(200);
        await expect(page.getByRole('region', { name: 'Unsaved changes' }), `${tab} looked unsaved on open`).toHaveCount(0);
    }
});
