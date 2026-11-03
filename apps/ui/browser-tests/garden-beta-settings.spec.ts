import { expect, test, type Page, type Route } from '@playwright/test';

// Every Garden visitor setting, including its own models, lives on its card in Settings → Beta
// features, except which cameras watch for Garden animals: that is one choice per camera, beside its
// bird role, in Settings → Connection. Settings save with the rest of the page; model downloads are
// separate explicit actions.

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

/** Opens one of the Garden card's collapsible sections by its heading. */
async function openSection(page: Page, name: string): Promise<void> {
    const toggle = page.getByRole('heading', { name }).getByRole('button');
    if (await toggle.getAttribute('aria-expanded') !== 'true') await toggle.click();
    await expect(toggle).toHaveAttribute('aria-expanded', 'true');
}

test('Connection chooses Garden cameras per camera, while Garden-only settings stay under Beta features', async ({ page }) => {
    await openSettings(page);
    const patio = page.getByRole('radiogroup', { name: 'patio: watch for' });
    await expect(patio.locator('label')).toHaveText(['Off', 'Birds', 'Garden animals', 'Both']);
    await expect(page.getByLabel('Frigate animal labels', { exact: true })).toHaveCount(0);
    await expect(page.getByRole('spinbutton', { name: 'Animal proposal threshold' })).toHaveCount(0);
});

test('Garden cameras chosen in Connection save with Beta settings without touching the bird role', async ({ page }) => {
    const { writes } = await openSettings(page);
    const patio = page.getByRole('radiogroup', { name: 'patio: watch for' });
    await expect(page.getByRole('checkbox', { name: 'Collect motion review photos on patio' })).toHaveCount(0);
    await patio.getByText('Both', { exact: true }).click();
    await page.getByRole('checkbox', { name: 'Collect motion review photos on patio' }).check();
    await expect(page.getByRole('radiogroup', { name: 'front: watch for' }).getByRole('radio', { name: 'Birds' })).toBeChecked();

    await openBeta(page);
    const garden = page.locator('[data-garden-beta-settings]');
    await expect(garden.locator('[data-garden-camera-summary]')).toContainText('Watching patio for Garden animals.');
    await garden.getByLabel('Frigate animal labels', { exact: true }).fill('cat, dog, squirrel');
    await garden.getByRole('spinbutton', { name: 'Animal proposal threshold' }).fill('64');
    await page.getByRole('button', { name: /Apply Settings/i }).click();

    await expect.poll(() => writes.length).toBe(1);
    expect(writes[0]).toMatchObject({
        beta_garden_animals: true,
        garden_cameras: ['patio'],
        garden_motion_cameras: ['patio'],
        garden_labels: ['cat', 'dog', 'squirrel'],
        garden_motion_confidence: 0.64,
        cameras: ['patio', 'front'],
        camera_roles: { patio: 'nest' }
    });
});

test('switching Garden off hides its settings and keeps them for later', async ({ page }) => {
    const { writes } = await openSettings(page, { garden_cameras: ['patio'], garden_motion_confidence: 0.63 });
    await openBeta(page);
    await expect(page.locator('[data-garden-camera-summary]')).toContainText('Watching patio for Garden animals.');
    await page.getByRole('switch', { name: 'Garden animals' }).click();
    await expect(page.locator('[data-garden-beta-settings]')).toHaveCount(0);
    await expect(page.locator('[data-beta-status]')).toHaveText('Off after you apply');
    await expect(page.locator('[data-garden-beta-off-note]')).toHaveText('Garden stops collecting new captures. Existing captures and settings are kept and come back when you turn it on again.');
    await expect(page.locator('[data-garden-beta-off]')).toContainText('hidden in the Explorer, its alerts stop, and birds you keep are recorded as wild birds');
    await page.getByRole('button', { name: /Apply Settings/i }).click();
    await expect.poll(() => writes.length).toBe(1);
    expect(writes[0]).toMatchObject({ beta_garden_animals: false, garden_cameras: ['patio'], garden_motion_confidence: 0.63 });
});

test('without Garden cameras, Beta features says where to choose them, once', async ({ page }) => {
    await openSettings(page, { cameras: [] }, []);
    await openBeta(page);
    await expect(page.locator('[data-garden-camera-summary]')).toContainText('No camera watches for Garden animals yet.');
    const step = page.locator('[data-garden-next-step="choose_camera"]');
    await expect(step).toContainText('Choose a camera to watch for Garden animals.');
    await expect(page.getByRole('button', { name: 'Choose cameras in Connection' })).toHaveCount(1);
    await step.getByRole('button', { name: 'Choose cameras in Connection' }).click();
    await expect(page.locator('#settings-camera-list')).toBeFocused();
});

for (const [calibrated, shown, up] of [[0.63, '63', '64'], [0.625, '62.5', '62.6']] as const) {
    test(`a calibrated ${calibrated} proposal threshold shows as ${shown}% and steps at its own precision`, async ({ page }) => {
        const { writes } = await openSettings(page, { garden_motion_confidence: calibrated });
        await openBeta(page);
        const threshold = page.getByRole('spinbutton', { name: 'Animal proposal threshold' });
        await expect(threshold).toHaveValue(shown);
        expect(await threshold.evaluate((input: HTMLInputElement) => ({ valid: input.checkValidity(), stepMismatch: input.validity.stepMismatch }))).toEqual({ valid: true, stepMismatch: false });
        await threshold.press('ArrowUp');
        await expect(threshold).toHaveValue(up);
        await threshold.press('ArrowDown');
        await expect(threshold).toHaveValue(shown);
        await threshold.press('ArrowUp');
        await page.getByRole('button', { name: /Apply Settings/i }).click();
        await expect.poll(() => writes.length).toBe(1);
        expect(writes[0].garden_motion_confidence).toBe(calibrated === 0.63 ? 0.64 : 0.626);
    });
}

for (const outside of ['49', '96', '']) {
    test(`a proposal threshold of "${outside}" is explained and nothing is saved`, async ({ page }) => {
        const { writes } = await openSettings(page);
        await openBeta(page);
        await page.getByRole('spinbutton', { name: 'Animal proposal threshold' }).fill(outside);
        await page.getByRole('button', { name: /Apply Settings/i }).click();
        await expect(page.getByRole('status').filter({ hasText: 'Enter an animal proposal threshold between 50% and 95%.' })).toBeVisible();
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
    await expect(threshold).toHaveValue('80');
    await threshold.fill('90');
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

for (const outside of ['69', '100']) {
    test(`a naming threshold of ${outside}% is explained and nothing is saved`, async ({ page }) => {
        const { writes } = await openSettings(page);
        await openBeta(page);
        await page.getByRole('spinbutton', { name: 'Naming threshold' }).fill(outside);
        await page.getByRole('button', { name: /Apply Settings/i }).click();
        await expect(page.getByRole('status').filter({ hasText: 'Enter a naming threshold between 70% and 99%.' })).toBeVisible();
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
    await openSection(page, 'Models');
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
    await openSection(page, 'Models');
    const check = page.locator('[data-garden-model="automatic_check"]');
    await expect(check).toContainText('SpeciesNet 4.0.3a · Tracked crop · 224 MB');
    await expect(check).toContainText('Required · Downloaded');
    await expect(check.getByRole('button')).toHaveCount(0);
    await expect(page.locator('[data-garden-model="species_suggestions"]')).toContainText('Optional · Not downloaded');
    const detector = page.locator('[data-garden-model="motion_detector"]');
    await expect(detector).toContainText('MegaDetector v1000 Cedar · 101 MB');
    await expect(detector).toContainText('Optional · Not downloaded');
    await expect(page.locator('[data-garden-country]')).toHaveText('Animal names are filtered for GBR.');

    await page.getByRole('link', { name: 'Connection', exact: true }).click();
    await page.getByRole('checkbox', { name: 'Collect motion review photos on patio' }).check();
    await openBeta(page);
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
    await openSection(page, 'Models');
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
    await openSection(page, 'Models');
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
    await openSection(page, 'Models');
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
    await openSection(page, 'Models');
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
        await openSection(page, 'Models');
        await expect(page.locator('[data-garden-models]').getByRole('alert')).toHaveText(detail);
        await expect(page.locator('[data-garden-model="automatic_check"]')).toContainText('Status unknown');
        await expect(page.locator('[data-garden-model="automatic_check"]').getByRole('button')).toHaveCount(0);
        failing = false;
        await page.getByRole('button', { name: 'Refresh status' }).click();
        await expect(page.locator('[data-garden-model="automatic_check"]')).toContainText('Required · Not downloaded');
        await expect(page.locator('[data-garden-models]').getByRole('alert')).toHaveCount(0);
    });
}

test('without a country, the view says naming and suggestions wait for one', async ({ page }) => {
    await openSettings(page, {}, ['patio', 'front'], (route, path) =>
        path === '/api/garden/identification' ? route.fulfill({ json: { ...identificationStatus, country: null } }) : undefined);
    await openBeta(page);
    await expect(page.locator('[data-garden-country]')).toContainText('No country is set, so animals are not named automatically');
    await expect(page.locator('[data-beta-status]')).toHaveText('On · no camera chosen · model not downloaded yet · no country set');
    await page.locator('[data-garden-next-step="set_location"]').getByRole('button', { name: 'Set location in Integrations' }).click();
    await expect(page.locator('#setting-location-mode')).toBeVisible();
});

test('the view explains each capture outcome and links daily review to the Explorer', async ({ page }) => {
    await openSettings(page);
    await openBeta(page);
    await openSection(page, 'Where captures go');
    const outcomes = page.locator('[data-garden-outcomes]');
    await expect(outcomes.getByRole('term')).toHaveText(['Needs review', 'Confirmed animals', 'Dismissed']);
    // The naming threshold is the floor for what Garden shows: below it, a photo is dismissed.
    await expect(outcomes.getByRole('definition').first()).not.toContainText('below the naming threshold');
    await expect(outcomes).toContainText('photos whose species score is below the naming threshold');
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
    await openSection(page, 'Models');
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
        await openSection(page, 'Models');
        await page.setViewportSize({ width, height: 900 });
        await page.addStyleTag({ content: 'html{font-size:200%!important}' });
        const garden = page.locator('[data-garden-beta-settings]');
        await expect(garden.locator('[data-garden-model="motion_detector"]')).toBeVisible();
        // Polled: a chevron mid-rotation briefly widens its own box.
        await expect.poll(() => garden.evaluate(node => node.scrollWidth <= node.clientWidth + 1)).toBe(true);
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

const notificationStatus = {
    enabled: false, use_bird_channels: true, channels: [], delivery_channels: [], include_photo: true,
    configured: { telegram: true, discord: false, pushover: false, email: false },
    attempts: { sent: 2, failed: 1, attempted: 0, skipped: 0 }
};

const gardenNotifications: GardenHandler = (route, path) => path === '/api/garden/notifications'
    ? route.fulfill({ json: notificationStatus }) : undefined;

async function openNotifications(page: Page): Promise<void> {
    await page.getByRole('link', { name: 'Notifications', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Garden animals' })).toBeVisible();
}

test('Beta features summarises Garden alerts and opens Notifications to set them up', async ({ page }) => {
    await openSettings(page, { garden_cameras: ['patio'] }, ['patio'], gardenNotifications);
    await openBeta(page);
    await expect(page.getByRole('heading', { name: 'Alerts' })).toContainText('Off');
    await openSection(page, 'Alerts');
    const summary = page.locator('[data-garden-alerts-summary]');
    await expect(summary).toContainText('Garden alerts are off.');
    await expect(page.getByRole('switch', { name: 'Send Garden alerts' })).toHaveCount(0);
    await summary.getByRole('button', { name: 'Set up alerts' }).click();
    await expect(page.getByRole('heading', { name: 'Garden animals' })).toBeVisible();
    await expect(page.getByRole('switch', { name: 'Send Garden alerts' })).toHaveAttribute('aria-checked', 'false');
});

test('Garden alerts follow the enabled bird channels by default, attach the photo and report saved attempts', async ({ page }) => {
    const harness = await openSettings(page, {
        garden_cameras: ['patio'], notifications_telegram_enabled: true,
        notifications_telegram_bot_token: '***REDACTED***', notifications_telegram_chat_id: '***REDACTED***'
    }, ['patio'], gardenNotifications);
    await openNotifications(page);
    const garden = page.locator('[data-garden-notifications]');
    await expect(garden.getByRole('radio')).toHaveCount(0);
    await page.getByRole('switch', { name: 'Send Garden alerts' }).click();
    await expect(garden.getByRole('radio', { name: /^Use my bird channels/ })).toBeChecked();
    await expect(garden.locator('[data-garden-delivery]')).toHaveText('Sends to Telegram.');
    await expect(page.getByRole('switch', { name: 'Include the photo' })).toHaveAttribute('aria-checked', 'true');
    await expect(garden.locator('[data-garden-notification-status]')).toContainText('Accepted by channel: 2');
    await page.getByRole('button', { name: /Apply Settings/i }).click();
    await expect.poll(() => harness.writes.length).toBe(1);
    expect(harness.writes[0]).toMatchObject({ garden_notifications_enabled: true,
        garden_notifications_use_bird_channels: true, garden_notifications_include_photo: true,
        notifications_telegram_enabled: true });
    expect(harness.otherWrites).toEqual([]);
});

test('chosen Garden channels use saved credentials without enabling bird alerts, and say what is missing', async ({ page }) => {
    const harness = await openSettings(page, { garden_cameras: ['patio'], notifications_telegram_enabled: false }, ['patio'], gardenNotifications);
    await openNotifications(page);
    const garden = page.locator('[data-garden-notifications]');
    await page.getByRole('switch', { name: 'Send Garden alerts' }).click();
    await expect(garden.locator('[data-garden-delivery]')).toContainText('No bird channel is switched on and configured');
    await garden.getByRole('radio', { name: /^Choose channels/ }).check();
    await expect(garden.locator('[data-garden-delivery]')).toHaveText('Choose at least one channel to deliver Garden alerts.');
    await page.getByRole('button', { name: 'Garden alerts via Telegram', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Garden alerts via Telegram', exact: true })).toHaveAttribute('aria-pressed', 'true');
    await expect(garden.locator('[data-garden-delivery]')).toContainText('No saved credentials for Telegram');
    await page.getByRole('switch', { name: 'Include the photo' }).click();
    await page.getByRole('button', { name: /Apply Settings/i }).click();
    await expect.poll(() => harness.writes.length).toBe(1);
    expect(harness.writes[0]).toMatchObject({ garden_notifications_enabled: true,
        garden_notifications_use_bird_channels: false, garden_notification_channels: ['telegram'],
        garden_notifications_include_photo: false, notifications_telegram_enabled: false });
    expect(harness.otherWrites).toEqual([]);
    // Reflow at 320px, and text resized to 200% on a tablet; the bird cards beside it have their own tests.
    for (const [width, fontSize] of [[320, '100%'], [768, '200%']] as const) {
        await page.setViewportSize({ width, height: 800 });
        await page.evaluate(size => document.documentElement.style.fontSize = size, fontSize);
        await expect.poll(() => garden.evaluate(node => node.scrollWidth <= node.clientWidth + 1)).toBe(true);
        for (const option of await garden.locator('label').all()) {
            expect(await option.evaluate(node => node.scrollWidth <= node.clientWidth + 1)).toBe(true);
        }
    }
});

test('the Garden alert choices work from the keyboard', async ({ page }) => {
    await openSettings(page, { garden_cameras: ['patio'], garden_notifications_enabled: true }, ['patio'], gardenNotifications);
    await openNotifications(page);
    const bird = page.getByRole('radio', { name: /^Use my bird channels/ });
    await bird.focus();
    await page.keyboard.press('ArrowRight');
    await expect(page.getByRole('radio', { name: /^Choose channels/ })).toBeChecked();
    await expect(page.getByRole('button', { name: 'Garden alerts via Telegram', exact: true })).toBeVisible();
});

test('Notifications shows no Garden section while the Garden beta is off', async ({ page }) => {
    const harness = await openSettings(page, { beta_garden_animals: false }, ['patio'], gardenNotifications);
    await page.getByRole('link', { name: 'Notifications', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Discord' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Garden animals' })).toHaveCount(0);
    expect(harness.gardenRequests).toEqual([]);
});

test('domestic birds you keep start empty, are added as chips and save with the page', async ({ page }) => {
    const { writes } = await openSettings(page);
    await openBeta(page);
    await expect(page.getByRole('heading', { name: 'Domestic birds you keep' })).toContainText('None');
    await openSection(page, 'Domestic birds you keep');
    const section = page.locator('[data-garden-domestic-birds]');
    await expect(section).toContainText('These are recorded as Garden animals, not wild birds, and are never sent to eBird, BirdWeather or iNaturalist.');
    await expect(section.locator('[data-garden-domestic-none]')).toBeVisible();
    const add = section.getByRole('combobox', { name: 'Add a domestic bird' });
    await add.selectOption('chicken');
    await add.selectOption('domestic_duck');
    const chips = section.getByRole('list', { name: 'Domestic birds you keep' });
    await expect(chips.getByRole('listitem')).toHaveText(['Chickens', 'Domestic ducks']);
    await expect(add.locator('option[value="chicken"]')).toHaveCount(0);
    // Removing works from the keyboard, with a label that says which bird.
    await section.getByRole('button', { name: 'Remove Domestic ducks' }).focus();
    await page.keyboard.press('Enter');
    await expect(chips.getByRole('listitem')).toHaveText(['Chickens']);
    await page.getByRole('button', { name: /Apply Settings/i }).click();
    await expect.poll(() => writes.length).toBe(1);
    expect(writes[0]).toMatchObject({ garden_domestic_birds: ['chicken'] });
});

test('saved domestic birds show as chips on a narrow screen', async ({ page }) => {
    await openSettings(page, { garden_domestic_birds: ['chicken', 'domestic_pigeon'] });
    await openBeta(page);
    await expect(page.getByRole('heading', { name: 'Domestic birds you keep' })).toContainText('2 birds');
    await openSection(page, 'Domestic birds you keep');
    await page.setViewportSize({ width: 320, height: 740 });
    const chips = page.locator('[data-garden-domestic-chips]');
    await expect(chips.getByRole('listitem')).toHaveText(['Chickens', 'Domestic pigeons or doves']);
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

// The Beta page: one card per feature, an on/off switch that stages in the draft, a status line in
// words, next steps while setup is unfinished, and the settings only while the feature is on.

test('the Beta page introduces beta features and lists Garden animals as a card', async ({ page }) => {
    await openSettings(page, { beta_garden_animals: false });
    await openBeta(page);
    await expect(page.locator('[data-beta-intro]')).toContainText('Each one is off until you turn it on');
    await expect(page.locator('[data-beta-intro]')).toContainText('Turning a feature off keeps what it has already recorded.');
    const list = page.getByRole('list', { name: 'Beta features' });
    await expect(list.getByRole('listitem')).toHaveCount(1);
    await expect(list.getByRole('article', { name: 'Garden animals' })).toBeVisible();
    await expect(page.locator('[data-beta-status]')).toHaveText('Off');
    await expect(page.locator('[data-beta-status]')).toHaveAttribute('data-beta-status', 'calm');
});

test('switching Garden on reveals its sections and the setup it still needs', async ({ page }) => {
    const { gardenRequests } = await openSettings(page, { beta_garden_animals: false, garden_cameras: [] });
    await openBeta(page);
    await expect(page.locator('[data-garden-beta-settings]')).toHaveCount(0);
    await page.getByRole('switch', { name: 'Garden animals' }).click();

    await expect(page.locator('[data-garden-beta-off-note]')).toHaveCount(0);
    const headings = page.locator('[data-garden-beta-settings] h5');
    await expect(headings).toHaveText(['Still to set up', 'Cameras', 'Automatic checks and naming', 'Models', 'Domestic birds you keep None', 'Alerts Off', 'Where captures go']);
    const expanded = page.locator('[data-beta-section] h5 button');
    await expect(expanded).toHaveCount(6);
    expect(await expanded.evaluateAll(buttons => buttons.map(button => button.getAttribute('aria-expanded')))).toEqual(['true', 'true', 'false', 'false', 'false', 'false']);

    await expect(page.locator('[data-beta-status]')).toHaveText('On after you apply · no camera chosen');
    await expect(page.locator('[data-beta-status]')).toHaveAttribute('data-beta-status', 'attention');
    await expect(page.locator('[data-garden-next-step]')).toHaveText([
        'Choose a camera to watch for Garden animals. Choose cameras in Connection',
        'Apply Settings to turn Garden on. Model and country checks then appear here.'
    ]);
    // Nothing asks the Garden API before Apply: it answers only while the saved switch is on.
    expect(gardenRequests).toEqual([]);
});

test('a running Garden states its cameras, the device it ran on and what is still missing', async ({ page }) => {
    await openSettings(page, { garden_cameras: [] }, ['patio', 'front'], (route, path) => path === '/api/garden/identification'
        ? route.fulfill({ json: { ...identificationStatus, country: null } })
        : undefined);
    await openBeta(page);
    await expect(page.locator('[data-beta-status]')).toHaveText('On · no camera chosen · model not downloaded yet · no country set');
    await expect(page.locator('[data-garden-next-step]')).toHaveText([
        /Choose a camera to watch for Garden animals\./,
        /Download the Automatic check model\./,
        /Set your location, so Garden knows your country/
    ]);
    await page.locator('[data-garden-next-step="download_model"]').getByRole('button', { name: 'Open Models' }).click();
    const models = page.getByRole('heading', { name: 'Models' }).getByRole('button');
    await expect(models).toHaveAttribute('aria-expanded', 'true');
    await expect(models).toBeFocused();
    await expect(page.locator('[data-garden-model="automatic_check"]').getByRole('button', { name: 'Download 224 MB' })).toBeVisible();
});

test('a ready Garden reads as on with no steps and no amber', async ({ page }) => {
    await openSettings(page, { garden_cameras: ['patio'] }, ['patio'], (route, path) => path === '/api/garden/identification'
        ? route.fulfill({ json: { ...identificationStatus, models: [{ ...identificationStatus.models[0], installed: true }, identificationStatus.models[1]], last_execution: {
            model_id: 'garden-speciesnet-4.0.3a', provider: 'intel_npu', requested_provider: 'intel_npu', devices: ['NPU'], checked_at: '2026-11-03T06:34:22Z', fallback_reason: null
        } } })
        : undefined);
    await openBeta(page);
    await expect(page.locator('[data-beta-status]')).toHaveText('On · 1 camera · automatic checks on NPU');
    await expect(page.locator('[data-beta-status]')).toHaveAttribute('data-beta-status', 'calm');
    await expect(page.locator('[data-garden-next-steps]')).toHaveCount(0);
});

test('the Garden switch works from the keyboard and reports its state', async ({ page }) => {
    const { writes } = await openSettings(page, { beta_garden_animals: false });
    await openBeta(page);
    const toggle = page.getByRole('switch', { name: 'Garden animals' });
    await expect(toggle).toHaveAttribute('aria-checked', 'false');
    await toggle.focus();
    await expect(toggle).toBeFocused();
    await page.keyboard.press('Space');
    await expect(toggle).toHaveAttribute('aria-checked', 'true');
    await expect(page.locator('[data-garden-beta-settings]')).toBeVisible();
    await page.keyboard.press('Enter');
    await expect(toggle).toHaveAttribute('aria-checked', 'false');
    await expect(page.locator('[data-garden-beta-settings]')).toHaveCount(0);
    await page.keyboard.press('Enter');
    await expect(toggle).toHaveAttribute('aria-checked', 'true');
    // The switch only stages the change; Apply Settings sends it with the page.
    expect(writes).toEqual([]);
    await page.getByRole('button', { name: /Apply Settings/i }).click();
    await expect.poll(() => writes.length).toBe(1);
    expect(writes[0]).toMatchObject({ beta_garden_animals: true });
});

test('a collapsible section opens and closes from the keyboard', async ({ page }) => {
    await openSettings(page);
    await openBeta(page);
    const alerts = page.getByRole('heading', { name: 'Alerts' }).getByRole('button');
    await alerts.focus();
    await page.keyboard.press('Enter');
    await expect(alerts).toHaveAttribute('aria-expanded', 'true');
    await expect(page.locator('[data-garden-alerts-summary]')).toBeVisible();
    await page.keyboard.press('Space');
    await expect(alerts).toHaveAttribute('aria-expanded', 'false');
    await expect(page.locator('[data-garden-alerts-summary]')).toBeHidden();
});

test('the camera selector in Connection follows the staged Garden switch and keeps Garden cameras', async ({ page }) => {
    const { writes } = await openSettings(page, { beta_garden_animals: false, garden_cameras: ['patio'] });
    const patio = page.getByRole('radiogroup', { name: 'patio: watch for' });
    await expect(patio.locator('label')).toHaveText(['Off', 'Birds']);
    await expect(page.locator('[data-camera-garden-hint]')).toBeVisible();

    await openBeta(page);
    await page.getByRole('switch', { name: 'Garden animals' }).click();
    await page.getByRole('link', { name: 'Connection', exact: true }).click();
    await expect(patio.locator('label')).toHaveText(['Off', 'Birds', 'Garden animals', 'Both']);
    await expect(patio.getByRole('radio', { name: 'Both' })).toBeChecked();
    await expect(page.locator('[data-camera-garden-hint]')).toHaveCount(0);

    await openBeta(page);
    await page.getByRole('switch', { name: 'Garden animals' }).click();
    await page.getByRole('link', { name: 'Connection', exact: true }).click();
    await expect(patio.locator('label')).toHaveText(['Off', 'Birds']);
    await page.getByRole('button', { name: /Apply Settings/i }).click();
    await expect.poll(() => writes.length).toBe(1);
    // Off keeps the Garden cameras for when it is turned on again.
    expect(writes[0]).toMatchObject({ beta_garden_animals: false, garden_cameras: ['patio'] });
});

for (const width of [390, 320]) {
    test(`the Beta page fits a ${width}px phone with Garden off and on`, async ({ page }) => {
        await openSettings(page, { beta_garden_animals: false, garden_cameras: [] });
        await openBeta(page);
        await page.setViewportSize({ width, height: 844 });
        const fits = () => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth);
        const toggle = page.getByRole('switch', { name: 'Garden animals' });
        const inView = async () => {
            const box = await toggle.boundingBox();
            return box !== null && box.x >= 0 && box.x + box.width <= width;
        };
        await expect.poll(fits).toBe(true);
        expect(await inView()).toBe(true);
        await toggle.click();
        await openSection(page, 'Models');
        await openSection(page, 'Domestic birds you keep');
        await expect.poll(fits).toBe(true);
        expect(await inView()).toBe(true);
        const step = await page.locator('[data-garden-next-step="choose_camera"]').getByRole('button').boundingBox();
        expect(step && step.x >= 0 && step.x + step.width <= width && step.height >= 44).toBe(true);
    });
}
