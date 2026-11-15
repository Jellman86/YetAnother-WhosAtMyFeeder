import { expect, test, type Page } from '@playwright/test';

// Unsaved Settings edits are not thrown away without a word. Through the real App shell: choosing
// another page, Back, and reloading all ask first, while moving between Settings tabs keeps the
// draft without asking.

interface ShellOptions {
    // Sign-in is required, and each sign-in gets a new session token.
    signIn?: boolean;
}

// `saved` is read on every request, so a test can change it to stand for a save made elsewhere.
async function openOwnerShell(page: Page, start = '/settings/connection', saved: Record<string, unknown> = {}, options: ShellOptions = {}): Promise<void> {
    let sessions = 0;
    let signedIn = !options.signIn;
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route(url => url.pathname.startsWith('/api/'), route => {
        const path = new URL(route.request().url()).pathname;
        if (path === '/api/auth/status') {
            return route.fulfill({ json: { auth_required: Boolean(options.signIn), public_access_enabled: false, is_authenticated: signedIn, username: signedIn && options.signIn ? 'owner' : null, needs_initial_setup: false } });
        }
        if (path === '/api/auth/login') {
            sessions += 1;
            signedIn = true;
            return route.fulfill({ json: { access_token: `session-${sessions}`, token_type: 'bearer', expires_in_hours: 1 } });
        }
        if (path === '/api/auth/logout') {
            signedIn = false;
            return route.fulfill({ json: { status: 'ok' } });
        }
        if (!signedIn) return route.fulfill({ status: 401, json: { detail: 'Not signed in' } });
        // A save is kept, so the next read shows it, as the backend does.
        if (path === '/api/settings' && route.request().method() === 'POST') {
            saved = { ...saved, ...(route.request().postDataJSON() as Record<string, unknown>) };
            return route.fulfill({ json: { status: 'updated' } });
        }
        const responses: Record<string, unknown> = {
            '/api/settings': { frigate_url: 'http://frigate:5000', mqtt_server: 'mqtt', mqtt_port: 1883, mqtt_auth: false, cameras: ['patio'], ...saved },
            '/api/update-status': { update_available: false },
        };
        if (path in responses) return route.fulfill({ json: responses[path] });
        return route.fulfill({ status: 503, json: { detail: 'Unavailable in leave guard fixture' } });
    });
    await page.route('**/health', route => route.fulfill({ json: { status: 'healthy' } }));
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto(start);
    if (options.signIn) await signIn(page);
    if (start.startsWith('/settings')) await expect(page.locator('#mqtt-server')).toHaveValue('mqtt');
}

async function signIn(page: Page): Promise<void> {
    await page.getByLabel('Username').fill('owner');
    await page.getByLabel('Password').fill('correct horse');
    await page.getByRole('button', { name: 'Sign in', exact: true }).click();
    await expect(page.getByRole('heading', { level: 1, name: 'Sign in' })).toHaveCount(0);
}

async function signOut(page: Page): Promise<void> {
    await page.locator('aside').getByRole('button', { name: 'Log out', exact: true }).first().click();
    await expect(page.getByRole('heading', { level: 1, name: 'Sign in' })).toBeVisible();
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

test('Save and leave saves the changes, then goes where you chose', async ({ page }) => {
    const posts: unknown[] = [];
    page.on('request', (request) => {
        if (request.method() === 'POST' && new URL(request.url()).pathname === '/api/settings') posts.push(request.postDataJSON());
    });
    await openOwnerShell(page);
    await page.locator('#mqtt-server').fill('broker.lan');
    await dashboardLink(page).click();
    await expect(leaveDialog(page)).toBeVisible();
    await leaveDialog(page).getByRole('button', { name: 'Save and leave', exact: true }).click();
    await expect.poll(() => posts.length).toBe(1);
    expect(posts[0]).toMatchObject({ mqtt_server: 'broker.lan' });
    await expect.poll(() => pathname(page)).toBe('/');
});

const restoredNotice = (page: Page) => page.getByText("You left with unsaved changes. They're still here.", { exact: true });

// History is Dashboard → Settings, with an unsaved edit on Settings.
async function editSettingsAfterDashboard(page: Page, saved: Record<string, unknown> = {}, options: ShellOptions = {}): Promise<void> {
    await openOwnerShell(page, '/', saved, options);
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

test('a draft kept by Back is gone after signing out and in again', async ({ page }) => {
    await editSettingsAfterDashboard(page, {}, { signIn: true });
    await page.goBack();
    await expect.poll(() => pathname(page)).toBe('/');
    await signOut(page);
    await signIn(page);
    await page.locator('aside').getByRole('button', { name: 'Settings', exact: true }).click();
    await expect(page.locator('#mqtt-server')).toHaveValue('mqtt');
    await expect(restoredNotice(page)).toHaveCount(0);
    await expect(page.getByRole('region', { name: 'Unsaved changes' })).toHaveCount(0);
});

test('signing out from Settings with unsaved changes keeps nothing for the next sign-in', async ({ page }) => {
    await editSettingsAfterDashboard(page, {}, { signIn: true });
    await signOut(page);
    await signIn(page);
    await page.locator('aside').getByRole('button', { name: 'Settings', exact: true }).click();
    await expect(page.locator('#mqtt-server')).toHaveValue('mqtt');
    await expect(restoredNotice(page)).toHaveCount(0);
});

test.describe('a kept draft meets a newer saved copy', () => {
    const conflictRow = (page: Page) => page.locator('[data-draft-conflict="mqtt_server"]');
    const saveButton = (page: Page) => page.getByRole('button', { name: 'Save changes', exact: true });

    async function leaveEditAndReturn(page: Page, saved: Record<string, unknown>, elsewhere: Record<string, unknown>): Promise<void> {
        await editSettingsAfterDashboard(page, saved);
        await page.goBack();
        await expect.poll(() => pathname(page)).toBe('/');
        Object.assign(saved, elsewhere);
        await page.goForward();
        await expect.poll(() => pathname(page)).toBe('/settings/connection');
        await expect(restoredNotice(page)).toBeVisible();
    }

    test('a change elsewhere to another setting is shown, and the draft is put back over it', async ({ page }) => {
        await leaveEditAndReturn(page, {}, { frigate_url: 'http://frigate-new:5000' });
        await expect(page.locator('#mqtt-server')).toHaveValue('broker.lan');
        await expect(page.locator('#frigate-url')).toHaveValue('http://frigate-new:5000');
        await expect(page.locator('[data-draft-conflicts]')).toHaveCount(0);
        await expect(saveButton(page)).toBeEnabled();
    });

    test('the same setting changed elsewhere is not overwritten: it is named, and Save waits for a choice', async ({ page }) => {
        await leaveEditAndReturn(page, {}, { mqtt_server: 'mqtt.elsewhere' });
        await expect(page.locator('#mqtt-server')).toHaveValue('mqtt.elsewhere');
        await expect(page.locator('#mqtt-server')).not.toHaveAttribute('aria-invalid', 'true');
        await expect(page.locator('[data-field-conflict="mqtt_server"]')).toContainText('The saved value changed elsewhere');
        await expect(page.locator('#mqtt-server')).toHaveAccessibleDescription(/saved value changed elsewhere/);
        await expect(page.locator('[data-draft-conflicts]')).toContainText('A setting you changed was also changed elsewhere');
        await expect(conflictRow(page)).toContainText('Connection');
        await expect(saveButton(page)).toBeDisabled();
        await expect(saveButton(page)).toHaveAccessibleDescription(/Choose which value to keep before saving/);
    });

    test('a conflict left undecided is asked again on the next return', async ({ page }) => {
        await leaveEditAndReturn(page, {}, { mqtt_server: 'mqtt.elsewhere' });
        await page.goBack();
        await expect.poll(() => pathname(page)).toBe('/');
        await page.goForward();
        await expect(conflictRow(page)).toBeVisible();
        await conflictRow(page).getByRole('button', { name: 'Use my change for MQTT broker (Connection)', exact: true }).click();
        await expect(page.locator('#mqtt-server')).toHaveValue('broker.lan');
    });

    test('Use the saved value keeps the value saved elsewhere and leaves nothing to save', async ({ page }) => {
        await leaveEditAndReturn(page, {}, { mqtt_server: 'mqtt.elsewhere' });
        await conflictRow(page).getByRole('button', { name: 'Use the saved value for MQTT broker (Connection)', exact: true }).click();
        await expect(page.locator('[data-draft-conflicts]')).toHaveCount(0);
        await expect(page.locator('[data-field-conflict]')).toHaveCount(0);
        await expect(page.locator('#mqtt-server')).toHaveValue('mqtt.elsewhere');
        await expect(saveButton(page)).toHaveCount(0);
    });

    test('Use my change puts the edit back and Save can send it', async ({ page }) => {
        await leaveEditAndReturn(page, {}, { mqtt_server: 'mqtt.elsewhere' });
        await conflictRow(page).getByRole('button', { name: 'Use my change for MQTT broker (Connection)', exact: true }).click();
        await expect(page.locator('[data-draft-conflicts]')).toHaveCount(0);
        await expect(page.locator('#mqtt-server')).toHaveValue('broker.lan');
        await expect(saveButton(page)).toBeEnabled();
        const write = page.waitForRequest(request => request.method() !== 'GET' && new URL(request.url()).pathname === '/api/settings');
        await saveButton(page).click();
        expect((await write).postDataJSON()).toMatchObject({ mqtt_server: 'broker.lan' });
    });

    test('a secret edited before leaving is never a conflict: it is only asked for again', async ({ page }) => {
        await editSettingsAfterDashboard(page, { mqtt_auth: true, mqtt_username: 'feeder', mqtt_password: '***REDACTED***' });
        await page.locator('#mqtt-password').fill('hunter2-secret');
        await page.goBack();
        await expect.poll(() => pathname(page)).toBe('/');
        await page.goForward();
        await expect(page.locator('[data-restored-secrets]')).toContainText('MQTT password');
        await expect(page.locator('[data-draft-conflict="mqtt_password"]')).toHaveCount(0);
        await expect(page.locator('#mqtt-password')).toHaveValue('');
    });

    test('a secret typed again on return survives choosing my change for another setting', async ({ page }) => {
        const saved: Record<string, unknown> = { mqtt_auth: true, mqtt_username: 'feeder', mqtt_password: '***REDACTED***' };
        await leaveEditAndReturn(page, saved, { mqtt_server: 'mqtt.elsewhere' });
        await page.locator('#mqtt-password').fill('typed-again');
        await conflictRow(page).getByRole('button', { name: 'Use my change for MQTT broker (Connection)', exact: true }).click();
        await expect(page.locator('#mqtt-server')).toHaveValue('broker.lan');
        await expect(page.locator('#mqtt-password')).toHaveValue('typed-again');
    });
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
