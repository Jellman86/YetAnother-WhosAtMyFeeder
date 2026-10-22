import { expect, test, type Page } from '@playwright/test';

// Every Garden visitor setting lives with its switch in Settings → Beta features, and saves with
// the rest of the settings page.

type Settings = Record<string, unknown>;

async function openSettings(page: Page, overrides: Settings = {}, frigateCameras: string[] = ['patio', 'front']): Promise<{ writes: Settings[] }> {
    let settings: Settings = {
        frigate_url: 'http://frigate:5000', mqtt_server: 'mqtt', mqtt_port: 1883,
        mqtt_auth: false, cameras: ['patio', 'front'], camera_roles: { patio: 'nest' },
        garden_cameras: [], garden_motion_cameras: [], garden_labels: ['cat', 'dog'],
        garden_motion_confidence: 0.5, garden_automatic_naming: true, garden_naming_threshold: 0.8,
        classification_threshold: 0.7,
        beta_garden_animals: true,
        ...overrides
    };
    const writes: Settings[] = [];
    await page.route(url => url.pathname.startsWith('/api/'), route => {
        const request = route.request();
        const path = new URL(request.url()).pathname;
        if (path === '/api/settings') {
            if (request.method() === 'POST') {
                const payload: unknown = request.postDataJSON();
                if (typeof payload !== 'object' || payload === null || Array.isArray(payload)) throw new Error('Expected settings object');
                writes.push(payload as Settings);
                settings = { ...settings, ...(payload as Settings) };
                return route.fulfill({ json: { status: 'ok' } });
            }
            return route.fulfill({ json: settings });
        }
        if (path.endsWith('/frigate/config')) return route.fulfill({ json: { cameras: Object.fromEntries(frigateCameras.map(name => [name, {}])) } });
        if (path.endsWith('/audio/sources')) return route.fulfill({ json: [] });
        if (path.endsWith('/backfill/status')) return route.fulfill({ json: null });
        return route.fulfill({ json: {} });
    });
    await page.goto('/browser-tests/settings-backfill.html');
    await expect(page.getByRole('link', { name: 'Beta features' })).toBeVisible();
    return { writes };
}

async function openBeta(page: Page): Promise<void> {
    await page.getByRole('link', { name: 'Beta features' }).click();
    await expect(page.getByRole('heading', { name: 'Beta features' })).toBeVisible();
}

test('Connection keeps only bird camera settings and points to Beta features for Garden', async ({ page }) => {
    await openSettings(page);
    await expect(page.getByRole('button', { name: /Garden animals/ })).toHaveCount(0);
    await expect(page.getByLabel('Frigate animal labels', { exact: true })).toHaveCount(0);
    await expect(page.getByText('Garden animal cameras are set in Settings → Beta features.')).toBeVisible();
});

test('every Garden setting is set under Beta features and saves without touching the bird role', async ({ page }) => {
    const { writes } = await openSettings(page);
    await openBeta(page);
    const garden = page.locator('[data-garden-beta-settings]');

    const patio = garden.getByRole('button', { name: 'Garden animals on patio' });
    await expect(patio).toHaveAttribute('aria-pressed', 'false');
    await expect(garden.getByRole('button', { name: 'Collect motion review photos on patio' })).toHaveCount(0);
    await patio.click();
    await expect(patio).toHaveAttribute('aria-pressed', 'true');
    await garden.getByRole('button', { name: 'Collect motion review photos on patio' }).click();
    await expect(garden.getByRole('button', { name: 'Garden animals on front' })).toHaveAttribute('aria-pressed', 'false');

    await garden.getByLabel('Frigate animal labels', { exact: true }).fill('cat, dog, squirrel');
    await garden.getByRole('spinbutton', { name: 'Animal proposal threshold' }).fill('0.64');
    await page.getByRole('button', { name: /Apply Settings/i }).click();

    await expect.poll(() => writes.length).toBe(1);
    expect(writes[0]).toMatchObject({
        beta_garden_animals: true,
        garden_cameras: ['patio'],
        garden_motion_cameras: ['patio'],
        garden_labels: ['cat', 'dog', 'squirrel'],
        garden_motion_confidence: 0.64,
        camera_roles: { patio: 'nest' }
    });
});

test('switching Garden off hides its settings and keeps them for later', async ({ page }) => {
    const { writes } = await openSettings(page, { garden_cameras: ['patio'], garden_motion_confidence: 0.63 });
    await openBeta(page);
    await expect(page.getByRole('button', { name: 'Garden animals on patio' })).toHaveAttribute('aria-pressed', 'true');
    await page.getByRole('switch', { name: 'Garden animals' }).click();
    await expect(page.locator('[data-garden-beta-settings]')).toHaveCount(0);
    await page.getByRole('button', { name: /Apply Settings/i }).click();
    await expect.poll(() => writes.length).toBe(1);
    expect(writes[0]).toMatchObject({ beta_garden_animals: false, garden_cameras: ['patio'], garden_motion_confidence: 0.63 });
});

test('without synced cameras, Beta features says where to get them', async ({ page }) => {
    await openSettings(page, { cameras: [] }, []);
    await openBeta(page);
    await expect(page.locator('[data-garden-beta-settings]')).toContainText('Sync the camera list in Settings → Connection');
});

for (const calibrated of [0.63, 0.625]) {
    test(`a calibrated ${calibrated} proposal threshold is valid and steps at its own precision`, async ({ page }) => {
        await openSettings(page, { garden_motion_confidence: calibrated });
        await openBeta(page);
        const threshold = page.getByRole('spinbutton', { name: 'Animal proposal threshold' });
        await expect(threshold).toHaveValue(String(calibrated));
        expect(await threshold.evaluate((input: HTMLInputElement) => ({ valid: input.checkValidity(), stepMismatch: input.validity.stepMismatch }))).toEqual({ valid: true, stepMismatch: false });
        await threshold.press('ArrowUp');
        await expect(threshold).toHaveValue(calibrated === 0.63 ? '0.64' : '0.626');
        await threshold.press('ArrowDown');
        await expect(threshold).toHaveValue(String(calibrated));
    });
}

for (const outside of ['0.49', '0.96']) {
    test(`a proposal threshold of ${outside} is explained and nothing is saved`, async ({ page }) => {
        const { writes } = await openSettings(page);
        await openBeta(page);
        await page.getByRole('spinbutton', { name: 'Animal proposal threshold' }).fill(outside);
        await page.getByRole('button', { name: /Apply Settings/i }).click();
        await expect(page.getByRole('status').filter({ hasText: 'Enter an animal proposal threshold between 0.5 and 0.95.' })).toBeVisible();
        expect(writes).toEqual([]);
    });
}

test('automatic naming is on at 0.80 by default and both choices save with the page', async ({ page }) => {
    const { writes } = await openSettings(page);
    await openBeta(page);
    const garden = page.locator('[data-garden-beta-settings]');
    const naming = garden.getByRole('switch', { name: 'Name animals automatically' });
    const threshold = garden.getByRole('spinbutton', { name: 'Naming threshold' });
    await expect(naming).toHaveAttribute('aria-checked', 'true');
    await expect(threshold).toHaveValue('0.8');
    await threshold.fill('0.9');
    await page.getByRole('button', { name: /Apply Settings/i }).click();
    await expect.poll(() => writes.length).toBe(1);
    expect(writes[0]).toMatchObject({ garden_automatic_naming: true, garden_naming_threshold: 0.9 });

    await naming.click();
    await expect(threshold).toHaveCount(0);
    await expect(garden.getByText('Every animal waits in Needs review for you to confirm and name it.')).toBeVisible();
    await page.getByRole('button', { name: /Apply Settings/i }).click();
    await expect.poll(() => writes.length).toBe(2);
    expect(writes[1]).toMatchObject({ garden_automatic_naming: false, garden_naming_threshold: 0.9 });
});

for (const outside of ['0.69', '1']) {
    test(`a naming threshold of ${outside} is explained and nothing is saved`, async ({ page }) => {
        const { writes } = await openSettings(page);
        await openBeta(page);
        await page.getByRole('spinbutton', { name: 'Naming threshold' }).fill(outside);
        await page.getByRole('button', { name: /Apply Settings/i }).click();
        await expect(page.getByRole('status').filter({ hasText: 'Enter a naming threshold between 0.7 and 0.99.' })).toBeVisible();
        expect(writes).toEqual([]);
    });
}
