import { expect, test, type Page } from '@playwright/test';

// Settings → Appearance holds its choices in the one Settings draft and loads its tab body on
// first use. The saved choices must load into the tab, an edit must survive leaving the tab, and
// Apply must send the Appearance fields with the rest of the form.

type Settings = Record<string, unknown>;

const SAVED_APPEARANCE: Settings = {
    display_common_names: true,
    scientific_name_primary: true,
    appearance_explorer_view: 'list',
    date_format: 'ymd',
    time_format: '12h',
    appearance_font_theme: 'studio',
    appearance_color_theme: 'default'
};

interface Harness {
    writes: Settings[];
    appearanceModuleRequests: () => number;
}

async function openSettings(page: Page): Promise<Harness> {
    let settings: Settings = {
        frigate_url: 'http://frigate:5000', mqtt_server: 'mqtt', mqtt_port: 1883, mqtt_auth: false,
        cameras: [], classification_threshold: 0.7, trusted_proxy_hosts: ['*'], notifications_notify_on_insert: true,
        ...SAVED_APPEARANCE
    };
    const writes: Settings[] = [];
    let appearanceModuleRequests = 0;
    page.on('request', request => {
        if (new URL(request.url()).pathname.endsWith('/AppearanceSettings.svelte')) appearanceModuleRequests += 1;
    });
    await page.route(url => url.pathname.startsWith('/api/') || url.pathname === '/health', async route => {
        const request = route.request();
        const path = new URL(request.url()).pathname;
        if (path === '/api/settings') {
            if (request.method() === 'POST') {
                const payload = request.postDataJSON() as Settings;
                writes.push(payload);
                settings = { ...settings, ...payload };
                return route.fulfill({ json: { status: 'updated' } });
            }
            return route.fulfill({ json: settings });
        }
        if (path === '/api/models/installed' || path === '/api/models/available') return route.fulfill({ json: [] });
        if (path.endsWith('/audio/sources')) return route.fulfill({ json: [] });
        if (path.endsWith('/frigate/config')) return route.fulfill({ json: { cameras: {} } });
        if (path.endsWith('/backfill/status')) return route.fulfill({ json: null });
        return route.fulfill({ json: {} });
    });
    await page.goto('/browser-tests/settings-backfill.html');
    await expect(page.locator('#mqtt-server')).toHaveValue('mqtt');
    return { writes, appearanceModuleRequests: () => appearanceModuleRequests };
}

const unsaved = (page: Page) => page.getByText('Unsaved Changes', { exact: true });

test('Appearance loads on first open, shows the saved choices and saves edits with Apply', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    const harness = await openSettings(page);
    expect(harness.appearanceModuleRequests()).toBe(0);

    await page.getByRole('link', { name: 'Appearance' }).click();
    await expect(page.locator('#date-format-select')).toHaveValue('ymd');
    expect(harness.appearanceModuleRequests()).toBe(1);
    await expect(page.locator('#time-format-select')).toHaveValue('12h');
    await expect(page.locator('#explorer-view-select')).toHaveValue('list');
    await expect(page.getByRole('button', { name: 'Select Hobbyist naming style' })).toHaveAttribute('aria-pressed', 'true');
    await expect(unsaved(page)).toHaveCount(0);

    await page.locator('#time-format-select').selectOption('24h');
    await page.getByRole('button', { name: /Advanced options/ }).click();
    await page.getByRole('button', { name: 'Blue Tit', exact: true }).click();
    await expect(unsaved(page)).toBeVisible();

    // Leaving the tab unmounts its body; the draft is the page's, so the edit is still there.
    await page.getByRole('link', { name: 'Connection' }).click();
    await expect(page.locator('#mqtt-server')).toBeVisible();
    await expect(unsaved(page)).toBeVisible();
    await page.getByRole('link', { name: 'Appearance' }).click();
    await expect(page.locator('#time-format-select')).toHaveValue('24h');

    await page.getByRole('button', { name: 'Apply Settings', exact: true }).click();
    await expect.poll(() => harness.writes.length).toBe(1);
    expect(harness.writes[0]).toMatchObject({
        ...SAVED_APPEARANCE,
        time_format: '24h',
        appearance_color_theme: 'bluetit'
    });
    await expect(unsaved(page)).toHaveCount(0);
    await expect(page.locator('#time-format-select')).toHaveValue('24h');
    expect(errors).toEqual([]);
});

test('switching the naming style back to the saved one leaves nothing to apply', async ({ page }) => {
    await openSettings(page);
    await page.getByRole('link', { name: 'Appearance' }).click();
    const scientific = page.getByRole('button', { name: 'Select Strictly Scientific naming style' });
    const hobbyist = page.getByRole('button', { name: 'Select Hobbyist naming style' });
    await expect(hobbyist).toHaveAttribute('aria-pressed', 'true');

    await scientific.click();
    await expect(scientific).toHaveAttribute('aria-pressed', 'true');
    await expect(unsaved(page)).toBeVisible();
    await hobbyist.click();
    await expect(unsaved(page)).toHaveCount(0);
});
