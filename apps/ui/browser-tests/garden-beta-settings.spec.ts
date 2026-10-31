import { expect, test, type Page, type Route } from '@playwright/test';

// Every Garden visitor setting, including its own models, lives with its switch in Settings → Beta
// features. Settings save with the rest of the page; model downloads are separate explicit actions.

type Settings = Record<string, unknown>;

const identificationStatus = {
    country: 'GBR', catalogue_ready: true, busy: false, error: null,
    models: [
        { variant: '4.0.3a', installed: false, size_bytes: 223998782 },
        { variant: '4.0.3b', installed: false, size_bytes: 223999179 }
    ],
    automatic_message: 'No automatic check is due.'
};
const motionStatus = {
    cameras: [], installed: false, model_bytes: 101228666, catalogue_ready: true, busy: false,
    state: 'disabled', message: 'Motion collection is off.'
};

type GardenHandler = (route: Route, path: string, method: string) => Promise<void> | undefined;

interface Harness {
    writes: Settings[];
    gardenRequests: string[];
    otherWrites: string[];
}

async function openSettings(page: Page, overrides: Settings = {}, frigateCameras: string[] = ['patio', 'front'], garden?: GardenHandler): Promise<Harness> {
    let settings: Settings = {
        frigate_url: 'http://frigate:5000', mqtt_server: 'mqtt', mqtt_port: 1883,
        mqtt_auth: false, cameras: ['patio', 'front'], camera_roles: { patio: 'nest' },
        garden_cameras: [], garden_motion_cameras: [], garden_labels: ['cat', 'dog'],
        garden_motion_confidence: 0.5, garden_automatic_naming: true, garden_naming_threshold: 0.8,
        classification_threshold: 0.7,
        beta_garden_animals: true,
        ...overrides
    };
    const harness: Harness = { writes: [], gardenRequests: [], otherWrites: [] };
    await page.route(url => url.pathname.startsWith('/api/'), async route => {
        const request = route.request();
        const path = new URL(request.url()).pathname;
        if (path === '/api/settings') {
            if (request.method() === 'POST') {
                const payload: unknown = request.postDataJSON();
                if (typeof payload !== 'object' || payload === null || Array.isArray(payload)) throw new Error('Expected settings object');
                harness.writes.push(payload as Settings);
                settings = { ...settings, ...(payload as Settings) };
                return route.fulfill({ json: { status: 'ok' } });
            }
            return route.fulfill({ json: settings });
        }
        if (path.startsWith('/api/garden')) {
            harness.gardenRequests.push(`${request.method()} ${path}`);
            const handled = garden?.(route, path, request.method());
            if (handled) return handled;
            if (path === '/api/garden/identification') return route.fulfill({ json: identificationStatus });
            if (path === '/api/garden/motion') return route.fulfill({ json: motionStatus });
            return route.fulfill({ status: 500, json: { detail: 'Unexpected Garden request' } });
        }
        if (request.method() !== 'GET') harness.otherWrites.push(`${request.method()} ${path}`);
        if (path.endsWith('/frigate/config')) return route.fulfill({ json: { cameras: Object.fromEntries(frigateCameras.map(name => [name, {}])) } });
        if (path.endsWith('/audio/sources')) return route.fulfill({ json: [] });
        if (path.endsWith('/backfill/status')) return route.fulfill({ json: null });
        return route.fulfill({ json: {} });
    });
    await page.goto('/browser-tests/settings-backfill.html');
    await expect(page.getByRole('link', { name: 'Beta features' })).toBeVisible();
    return harness;
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

test('a switched-off Garden states what it needs without asking the Garden API or offering downloads', async ({ page }) => {
    const { gardenRequests } = await openSettings(page, { beta_garden_animals: false });
    await openBeta(page);
    await expect(page.locator('[data-garden-beta-requirements]')).toContainText('224 MB for automatic checks');
    await expect(page.locator('[data-garden-beta-requirements]')).toContainText('Your bird model is not changed.');
    await expect(page.getByRole('button', { name: /^Download/ })).toHaveCount(0);

    await page.getByRole('switch', { name: 'Garden animals' }).click();
    await expect(page.locator('[data-garden-models-apply]')).toContainText('Choose Apply Settings to switch Garden on');
    await expect(page.getByRole('button', { name: /^Download/ })).toHaveCount(0);
    expect(gardenRequests).toEqual([]);
});

test('model status appears once Apply Settings has switched Garden on', async ({ page }) => {
    const { writes } = await openSettings(page, { beta_garden_animals: false });
    await openBeta(page);
    await page.getByRole('switch', { name: 'Garden animals' }).click();
    await page.getByRole('button', { name: /Apply Settings/i }).click();
    await expect.poll(() => writes.length).toBe(1);
    await expect(page.locator('[data-garden-model="automatic_check"]')).toContainText('Required · Not downloaded');
});

test('Garden models lists its three own models with measured state, size and requirement', async ({ page }) => {
    await openSettings(page, { garden_cameras: ['patio'] }, ['patio', 'front'], (route, path) =>
        path === '/api/garden/identification'
            ? route.fulfill({ json: { ...identificationStatus, models: [{ ...identificationStatus.models[0], installed: true }, identificationStatus.models[1]] } })
            : undefined);
    await openBeta(page);
    const check = page.locator('[data-garden-model="automatic_check"]');
    await expect(check).toContainText('SpeciesNet 4.0.3a · Tracked crop · 224 MB');
    await expect(check).toContainText('Required · Downloaded');
    await expect(check.getByRole('button')).toHaveCount(0);
    await expect(page.locator('[data-garden-model="species_suggestions"]')).toContainText('Optional · Not downloaded');
    const detector = page.locator('[data-garden-model="motion_detector"]');
    await expect(detector).toContainText('MegaDetector v1000 Cedar · 101 MB');
    await expect(detector).toContainText('Optional · Not downloaded');
    await expect(page.locator('[data-garden-country]')).toHaveText('Animal names are filtered for GBR.');

    await page.getByRole('button', { name: 'Collect motion review photos on patio' }).click();
    await expect(detector).toContainText('Required · Not downloaded');
});

test('downloading a model shows its own progress, saves nothing and changes no bird model', async ({ page }) => {
    let release: () => void = () => undefined;
    const held = new Promise<void>(resolve => { release = resolve; });
    let installed = false;
    const harness = await openSettings(page, {}, ['patio', 'front'], (route, path, method) => {
        if (method === 'POST' && path === '/api/garden/models/4.0.3a/install') {
            return held.then(() => {
                installed = true;
                return route.fulfill({ json: { ...identificationStatus, models: [{ ...identificationStatus.models[0], installed: true }, identificationStatus.models[1]] } });
            });
        }
        if (path === '/api/garden/identification' && installed) {
            return route.fulfill({ json: { ...identificationStatus, models: [{ ...identificationStatus.models[0], installed: true }, identificationStatus.models[1]] } });
        }
        return undefined;
    });
    await openBeta(page);
    await page.getByLabel('Frigate animal labels', { exact: true }).fill('cat, dog, fox');

    const check = page.locator('[data-garden-model="automatic_check"]');
    await check.getByRole('button', { name: 'Download 224 MB' }).click();
    await expect(check.getByRole('progressbar', { name: 'Downloading Automatic check model' })).toBeVisible();
    await expect(check.getByRole('status')).toContainText('Downloading and verifying');
    await expect(page.locator('[data-garden-model="motion_detector"]').getByRole('button', { name: 'Download 101 MB' })).toBeDisabled();
    await expect(page.locator('[data-garden-model="species_suggestions"]').getByRole('progressbar')).toHaveCount(0);

    release();
    await expect(check).toContainText('Required · Downloaded');
    await expect(check.getByRole('status')).toHaveText('Downloaded and checksum verified.');
    await expect(page.getByLabel('Frigate animal labels', { exact: true })).toHaveValue('cat, dog, fox');
    expect(harness.writes).toEqual([]);
    expect(harness.otherWrites).toEqual([]);
    expect(harness.gardenRequests.filter(request => request.startsWith('POST'))).toEqual(['POST /api/garden/models/4.0.3a/install']);
});

test('a failed download says nothing changed and can be retried', async ({ page }) => {
    let attempts = 0;
    await openSettings(page, {}, ['patio', 'front'], (route, path, method) => {
        if (method !== 'POST' || path !== '/api/garden/motion/install') return undefined;
        attempts += 1;
        return attempts === 1
            ? route.fulfill({ status: 503, json: { detail: 'Motion detector could not be downloaded and verified. Try again.' } })
            : route.fulfill({ json: { ...motionStatus, installed: true } });
    });
    await openBeta(page);
    const detector = page.locator('[data-garden-model="motion_detector"]');
    await detector.getByRole('button', { name: 'Download 101 MB' }).click();
    await expect(detector.getByRole('alert')).toHaveText('Motion detector could not be downloaded and verified. Try again.');
    await expect(detector).toContainText('Optional · Not downloaded');
    await detector.getByRole('button', { name: 'Retry download' }).click();
    await expect.poll(() => attempts).toBe(2);
    await expect(detector.getByRole('alert')).toHaveCount(0);
});

test('a busy Garden explains why downloads wait', async ({ page }) => {
    await openSettings(page, {}, ['patio', 'front'], (route, path) =>
        path === '/api/garden/identification' ? route.fulfill({ json: { ...identificationStatus, busy: true } }) : undefined);
    await openBeta(page);
    await expect(page.locator('[data-garden-model="automatic_check"]').getByRole('button', { name: 'Download 224 MB' })).toBeDisabled();
    await expect(page.locator('#garden-models-block')).toHaveText('Garden is busy with a check, scan or download. Refresh the status in a minute.');
});

test('unavailable Garden data is reported and never offered as a download', async ({ page }) => {
    await openSettings(page, {}, ['patio', 'front'], (route, path) => {
        if (path === '/api/garden/identification') return route.fulfill({ json: { ...identificationStatus, catalogue_ready: false } });
        if (path === '/api/garden/motion') return route.fulfill({ json: { ...motionStatus, catalogue_ready: false } });
        return undefined;
    });
    await openBeta(page);
    await expect(page.locator('[data-garden-models]').getByRole('alert')).toContainText('Garden species data is unavailable');
    await expect(page.locator('[data-garden-model] [data-garden-model-state]')).toHaveText(Array(3).fill(/Unavailable/));
    await expect(page.locator('[data-garden-models]').getByRole('button', { name: /^Download/ })).toHaveCount(0);
});

for (const [status, detail] of [[500, 'Internal Server Error'], [403, 'Owner access is required.']] as const) {
    test(`an unreadable model status (${status}) is unknown, never ready, and refresh recovers`, async ({ page }) => {
        let failing = true;
        await openSettings(page, {}, ['patio', 'front'], (route, path) =>
            failing && path === '/api/garden/identification' ? route.fulfill({ status, json: { detail } }) : undefined);
        await openBeta(page);
        await expect(page.locator('[data-garden-models]').getByRole('alert')).toHaveText(detail);
        await expect(page.locator('[data-garden-model="automatic_check"]')).toContainText('Status unknown');
        await expect(page.locator('[data-garden-model="automatic_check"]').getByRole('button')).toHaveCount(0);
        failing = false;
        await page.getByRole('button', { name: 'Refresh model status' }).click();
        await expect(page.locator('[data-garden-model="automatic_check"]')).toContainText('Required · Not downloaded');
        await expect(page.locator('[data-garden-models]').getByRole('alert')).toHaveCount(0);
    });
}

test('without a country, the view says naming and suggestions wait for one', async ({ page }) => {
    await openSettings(page, {}, ['patio', 'front'], (route, path) =>
        path === '/api/garden/identification' ? route.fulfill({ json: { ...identificationStatus, country: null } }) : undefined);
    await openBeta(page);
    await expect(page.locator('[data-garden-country]')).toContainText('Set a country in Settings → Location.');
});

test('the view explains each capture outcome and links daily review to the Explorer', async ({ page }) => {
    await openSettings(page);
    await openBeta(page);
    const outcomes = page.locator('[data-garden-outcomes]');
    await expect(outcomes.getByRole('term')).toHaveText(['Needs review', 'Confirmed animals', 'Dismissed']);
    await expect(outcomes).toContainText('Low-confidence automatic results');
    await expect(outcomes).toContainText('person evidence is removed');
    await page.getByRole('button', { name: 'Review Garden animals' }).click();
    await expect(page.locator('main[data-fixture-route]')).toHaveAttribute('data-fixture-route', '/events?visitors=garden&review=pending');
});

test('a model downloads from the keyboard', async ({ page }) => {
    let requested = false;
    await openSettings(page, {}, ['patio', 'front'], (route, path, method) => {
        if (method === 'POST' && path === '/api/garden/models/4.0.3b/install') {
            requested = true;
            return route.fulfill({ json: { ...identificationStatus, models: [identificationStatus.models[0], { ...identificationStatus.models[1], installed: true }] } });
        }
        return undefined;
    });
    await openBeta(page);
    const button = page.locator('[data-garden-model="species_suggestions"]').getByRole('button', { name: 'Download 224 MB' });
    await button.focus();
    await expect(button).toBeFocused();
    await page.keyboard.press('Enter');
    await expect.poll(() => requested).toBe(true);
});

for (const width of [320, 393]) {
    test(`Garden setup fits ${width}px with 200% text`, async ({ page }) => {
        await openSettings(page, { garden_cameras: ['patio'] });
        await openBeta(page);
        await page.setViewportSize({ width, height: 900 });
        await page.addStyleTag({ content: 'html{font-size:200%!important}' });
        const garden = page.locator('[data-garden-beta-settings]');
        await expect(garden.locator('[data-garden-model="motion_detector"]')).toBeVisible();
        expect(await garden.evaluate(node => node.scrollWidth <= node.clientWidth + 1)).toBe(true);
        for (const row of await garden.locator('[data-garden-model]').all()) {
            expect(await row.evaluate(node => node.scrollWidth <= node.clientWidth + 1)).toBe(true);
        }
        const download = await garden.locator('[data-garden-model="automatic_check"]').getByRole('button', { name: 'Download 224 MB' }).boundingBox();
        expect(download && download.x >= 0 && download.x + download.width <= width).toBe(true);
    });
}

// Collection status moved here from the retired Garden page: what Garden is doing, as measured.
test('collection status shows the collector state, its limits and bounded catch-up on a narrow screen', async ({ page }) => {
    await openSettings(page, {}, ['patio', 'front'], (route, path) => path === '/api/garden/motion'
        ? route.fulfill({ json: {
            ...motionStatus, cameras: ['patio'], installed: true, state: 'waiting', message: 'Waiting for bird inference to become idle.',
            interval_seconds: 10, catchup_seconds: 1800, queue_limit: 24, photo_limit: 128, photo_retention_days: 3,
            queued_windows: 24, queue_camera: 'patio', queue_checked_at: '2026-10-13T18:00:00Z', last_scan_at: '2026-10-13T18:01:00Z'
        } })
        : undefined);
    await openBeta(page);
    const status = page.locator('[data-garden-collection-status]');
    await expect(status.locator('[data-garden-motion-status]')).toHaveText('Waiting for bird inference to become idle.');
    await expect(status).toContainText('No automatic check is due.');
    await expect(status.getByText('Motion detector only: CPU · At least 10s between scans · Up to 128 photos · 3-day photo retention')).toBeVisible();
    await expect(status.getByText('Up to 24 short windows queued per camera from the last 30 minutes. Birds and camera pressure pause collection; brief visits can be missed.')).toBeVisible();
    await expect(status.getByText(/patio: 24 windows waiting when checked at/)).toBeVisible();
    await expect(status.getByText(/Last scan:/)).toBeVisible();
    await page.setViewportSize({ width: 320, height: 900 });
    await page.evaluate(() => document.documentElement.style.fontSize = '200%');
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

for (const seconds of [5, 10]) {
    test(`collection status shows the selected ${seconds}-second scan interval`, async ({ page }) => {
        await openSettings(page, {}, ['patio', 'front'], (route, path) => path === '/api/garden/motion'
            ? route.fulfill({ json: { ...motionStatus, cameras: ['patio'], installed: true, state: 'waiting', interval_seconds: seconds, photo_limit: 128, photo_retention_days: 3, message: 'Recording scanned; no review photo retained.' } })
            : undefined);
        await openBeta(page);
        await expect(page.locator('[data-garden-collection-status]').getByText(`Motion detector only: CPU · At least ${seconds}s between scans · Up to 128 photos · 3-day photo retention`)).toBeVisible();
    });
}

test('collection status says so when the Garden service cannot report it', async ({ page }) => {
    await openSettings(page, {}, ['patio', 'front'], (route, path) => path === '/api/garden/motion'
        ? route.fulfill({ status: 503, json: { detail: 'Garden status unavailable.' } })
        : undefined);
    await openBeta(page);
    await expect(page.locator('[data-garden-collection-status]')).toContainText('Model status unavailable. Refresh to try again.');
});


test('Garden shows the actual last NPU execution separately from CPU-only motion scans', async ({ page }) => {
    await openSettings(page, {}, ['patio'], (route, path) => path === '/api/garden/identification'
        ? route.fulfill({ json: { ...identificationStatus, preferred_provider: 'intel_npu', last_execution: {
            model_id: 'garden-speciesnet-4.0.3a', provider: 'intel_npu', requested_provider: 'intel_npu',
            devices: ['NPU'], checked_at: '2026-10-25T06:34:22Z', fallback_reason: null
        } } }) : undefined);
    await openBeta(page);
    const status = page.locator('[data-garden-collection-status]');
    await expect(status).toContainText('Automatic check device preference: NPU');
    await expect(status).toContainText('Last completed run: NPU');
});

test('Garden alerts opt in to their own channels and report saved attempts without enabling bird alerts', async ({ page }) => {
    const harness = await openSettings(page, { garden_cameras: ['patio'], notifications_telegram_enabled: false }, ['patio'], (route, path) => {
        if (path === '/api/garden/notifications') return route.fulfill({ json: {
            enabled: false, channels: [], configured: { telegram: true, discord: false, pushover: false, email: false },
            attempts: { sent: 2, failed: 1, attempted: 0, skipped: 0 }
        } });
    });
    await openBeta(page);
    const toggle = page.getByRole('switch', { name: /^Garden notifications/ });
    await expect(toggle).toHaveAttribute('aria-checked', 'false');
    await expect(page.getByRole('button', { name: 'Garden alerts via Telegram', exact: true })).toHaveCount(0);
    await toggle.click();
    await page.getByRole('button', { name: 'Garden alerts via Telegram', exact: true }).click();
    await expect(page.locator('[data-garden-notification-status]')).toContainText('Accepted by channel: 2');
    await page.getByRole('button', { name: /Apply Settings/i }).click();
    await expect.poll(() => harness.writes.length).toBe(1);
    expect(harness.writes[0]).toMatchObject({ garden_notifications_enabled: true,
        garden_notification_channels: ['telegram'], notifications_telegram_enabled: false });
    expect(harness.otherWrites).toEqual([]);
    await page.setViewportSize({ width: 320, height: 800 });
    await page.evaluate(() => document.documentElement.style.fontSize = '200%');
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
