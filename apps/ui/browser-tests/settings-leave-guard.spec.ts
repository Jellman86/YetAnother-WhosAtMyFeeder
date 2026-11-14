import { expect, test, type Page } from '@playwright/test';

// Unsaved Settings edits are not thrown away without a word. Through the real App shell: choosing
// another page, Back, and reloading all ask first, while moving between Settings tabs keeps the
// draft without asking.

async function openOwnerShell(page: Page, start = '/settings/connection', saved: Record<string, unknown> = {}): Promise<void> {
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route(url => url.pathname.startsWith('/api/'), route => {
        const path = new URL(route.request().url()).pathname;
        const responses: Record<string, unknown> = {
            '/api/auth/status': { auth_required: false, is_authenticated: true, needs_initial_setup: false },
            '/api/settings': { frigate_url: 'http://frigate:5000', mqtt_server: 'mqtt', mqtt_port: 1883, mqtt_auth: false, cameras: ['patio'], ...saved },
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

const restoredNotice = (page: Page) => page.getByText("You left with unsaved changes. They're still here.", { exact: true });

// History is Dashboard → Settings, with an unsaved edit on Settings.
async function editSettingsAfterDashboard(page: Page, saved: Record<string, unknown> = {}): Promise<void> {
    await openOwnerShell(page, '/', saved);
    await page.locator('aside').getByRole('button', { name: 'Settings', exact: true }).click();
    await expect(page.locator('#mqtt-server')).toHaveValue('mqtt');
    await page.locator('#mqtt-server').fill('broker.lan');
}

test('Back and Forward never ask; the draft is waiting on return, and Discard drops it', async ({ page }) => {
    await editSettingsAfterDashboard(page);

    await page.goBack();
    await expect.poll(() => pathname(page)).toBe('/');
    await expect(leaveDialog(page)).toHaveCount(0);

    await page.goForward();
    await expect.poll(() => pathname(page)).toBe('/settings/connection');
    await expect(page.locator('#mqtt-server')).toHaveValue('broker.lan');
    await expect(restoredNotice(page)).toBeVisible();
    await expect(page.getByRole('region', { name: 'Unsaved changes' })).toContainText('1 unsaved change in');

    await page.getByRole('button', { name: 'Discard changes', exact: true }).click();
    await expect(page.locator('#mqtt-server')).toHaveValue('mqtt');
    await expect(restoredNotice(page)).toHaveCount(0);
    await page.goBack();
    await page.goForward();
    await expect(page.locator('#mqtt-server')).toHaveValue('mqtt');
    await expect(restoredNotice(page)).toHaveCount(0);
});

test('rapid Back and Forward never block or misroute, and keep the draft', async ({ page }) => {
    await editSettingsAfterDashboard(page);
    for (let step = 0; step < 4; step += 1) {
        await page.goBack();
        await page.goForward();
    }
    await page.goBack();
    await expect.poll(() => pathname(page)).toBe('/');
    await expect(page.getByRole('heading', { level: 1 })).not.toHaveText('Settings');
    await page.goForward();
    await expect.poll(() => pathname(page)).toBe('/settings/connection');
    await expect(leaveDialog(page)).toHaveCount(0);
    await expect(page.locator('#mqtt-server')).toHaveValue('broker.lan');
});

test('a secret typed before leaving is never kept: the return says to type it again', async ({ page }) => {
    await editSettingsAfterDashboard(page, { mqtt_auth: true, mqtt_username: 'feeder', mqtt_password: '***REDACTED***' });
    await page.locator('#mqtt-password').fill('hunter2-secret');

    await page.goBack();
    await expect.poll(() => pathname(page)).toBe('/');
    const stored = await page.evaluate(() => JSON.stringify({ ...localStorage }) + JSON.stringify({ ...sessionStorage }));
    expect(stored).not.toContain('hunter2');

    await page.goForward();
    await expect(page.locator('#mqtt-server')).toHaveValue('broker.lan');
    await expect(page.locator('#mqtt-password')).toHaveValue('');
    await expect(page.locator('[data-restored-secrets]')).toContainText('MQTT password');
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
