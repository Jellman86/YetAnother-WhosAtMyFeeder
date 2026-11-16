import { expect, test, type Locator, type Page } from '@playwright/test';

// Settings → Cameras & connection → Cameras to watch: one row per Frigate camera choosing Off, Birds,
// Garden animals or Both. Each choice must land in the server's independent lists exactly:
// `cameras` (empty means every camera), `garden_cameras`, `garden_motion_cameras` and
// `camera_roles`.

type Settings = Record<string, unknown>;

const CAMERA_FIELDS = ['cameras', 'garden_cameras', 'garden_motion_cameras', 'camera_roles'] as const;

interface Harness {
    writes: Settings[];
}

async function openConnection(page: Page, overrides: Settings = {}, frigateCameras: string[] | null = ['patio', 'front', 'greenhouse']): Promise<Harness> {
    let settings: Settings = {
        frigate_url: 'http://frigate:5000', mqtt_server: 'mqtt', mqtt_port: 1883, mqtt_auth: false,
        cameras: ['patio', 'front'], camera_roles: {},
        garden_cameras: [], garden_motion_cameras: [], garden_labels: ['cat', 'dog'],
        garden_motion_confidence: 0.5, garden_automatic_naming: true, garden_naming_threshold: 0.8,
        classification_threshold: 0.7,
        beta_garden_animals: true,
        ...overrides
    };
    const harness: Harness = { writes: [] };
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
        if (path.endsWith('/frigate/config')) {
            if (frigateCameras === null) return route.fulfill({ status: 502, json: { detail: 'Frigate unreachable' } });
            return route.fulfill({ json: { cameras: Object.fromEntries(frigateCameras.map(name => [name, {}])) } });
        }
        if (path === '/api/garden/identification') return route.fulfill({ json: { country: 'GBR', catalogue_ready: true, busy: false, error: null, models: [], automatic_message: '' } });
        if (path === '/api/garden/motion') return route.fulfill({ json: { cameras: [], installed: false, model_bytes: 1, catalogue_ready: true, busy: false, state: 'disabled', message: '' } });
        if (path.endsWith('/audio/sources')) return route.fulfill({ json: [] });
        if (path.endsWith('/backfill/status')) return route.fulfill({ json: null });
        return route.fulfill({ json: {} });
    });
    await page.goto('/browser-tests/settings-backfill.html');
    await expect(page.locator('[data-camera-list]')).toBeVisible();
    return harness;
}

function watchFor(page: Page, camera: string): Locator {
    return page.getByRole('combobox', { name: `${camera}: watch for` });
}

// A blocked choice is a disabled <option>; Playwright's toBeDisabled() does not read that, so the
// tests check the attribute itself.
function choice(select: Locator, label: string): Locator {
    return select.getByRole('option', { name: label, exact: true });
}

function chosen(select: Locator): Locator {
    return select.locator('option:checked');
}

function motionSwitch(page: Page, camera: string): Locator {
    return page.locator(`[data-camera-watch="${camera}"]`).getByRole('switch', { name: /^Collect motion review photos/ });
}

function cameraFields(payload: Settings | undefined): Settings {
    return Object.fromEntries(CAMERA_FIELDS.map(field => [field, payload?.[field]]));
}

async function apply(page: Page, harness: Harness, count: number): Promise<Settings> {
    await page.getByRole('button', { name: 'Save changes', exact: true }).click();
    await expect.poll(() => harness.writes.length).toBe(count);
    // Wait for the saved settings to come back, so the next edit is not made under the reload.
    await expect(page.locator('[data-settings-save-bar]')).toHaveCount(0);
    return cameraFields(harness.writes[count - 1]);
}

test('a camera set to Garden animals only, then Both, then Off saves exactly those lists', async ({ page }) => {
    const harness = await openConnection(page, { camera_roles: { patio: 'nest' } });
    const patio = watchFor(page, 'patio');
    await expect(chosen(patio)).toHaveText('Birds');

    await patio.selectOption({ label: 'Garden animals' });
    await expect(page.locator('[data-camera-watch="patio"] [data-camera-role]')).toHaveCount(0);
    await motionSwitch(page, 'patio').click();
    await expect(motionSwitch(page, 'patio')).toHaveAttribute('aria-checked', 'true');
    expect(await apply(page, harness, 1)).toEqual({
        cameras: ['front'], garden_cameras: ['patio'], garden_motion_cameras: ['patio'], camera_roles: {}
    });

    await patio.selectOption({ label: 'Both' });
    await page.getByRole('combobox', { name: 'patio: bird role' }).selectOption({ label: 'Nest' });
    expect(await apply(page, harness, 2)).toEqual({
        cameras: ['front', 'patio'], garden_cameras: ['patio'], garden_motion_cameras: ['patio'], camera_roles: { patio: 'nest' }
    });

    await patio.selectOption({ label: 'Off' });
    await expect(motionSwitch(page, 'patio')).toHaveCount(0);
    expect(await apply(page, harness, 3)).toEqual({
        cameras: ['front'], garden_cameras: [], garden_motion_cameras: [], camera_roles: {}
    });
});

test('turning one camera off while every camera watches for birds lists the others explicitly', async ({ page }) => {
    const harness = await openConnection(page, { cameras: [] });
    await expect(page.locator('[data-bird-scope]')).toContainText('Every Frigate camera is watched for birds, including cameras added to Frigate later.');
    for (const camera of ['patio', 'front', 'greenhouse']) {
        await expect(chosen(watchFor(page, camera))).toHaveText('Birds');
    }

    await watchFor(page, 'front').selectOption({ label: 'Garden animals' });
    await expect(page.locator('[data-bird-scope]')).toContainText('Only the cameras chosen here are watched for birds.');
    expect(await apply(page, harness, 1)).toEqual({
        cameras: ['patio', 'greenhouse'], garden_cameras: ['front'], garden_motion_cameras: [], camera_roles: {}
    });

    await page.getByRole('button', { name: 'Watch every camera for birds' }).click();
    await expect(chosen(watchFor(page, 'front'))).toHaveText('Both');
    expect(await apply(page, harness, 2)).toEqual({
        cameras: [], garden_cameras: ['front'], garden_motion_cameras: [], camera_roles: {}
    });
});

test('the last bird camera cannot stop watching for birds, and says why', async ({ page }) => {
    const harness = await openConnection(page, { cameras: ['patio'] });
    const patio = watchFor(page, 'patio');
    await expect(choice(patio, 'Off')).toHaveAttribute('disabled');
    await expect(choice(patio, 'Garden animals')).toHaveAttribute('disabled');
    await expect(choice(patio, 'Both')).not.toHaveAttribute('disabled');
    await expect(patio).toHaveAccessibleDescription('At least one camera must watch for birds, so birds stay on for this camera.');
    await expect(page.locator('[data-camera-watch="patio"] [data-camera-watch-reason]')).toBeVisible();

    // Another bird camera lifts the block.
    await watchFor(page, 'front').selectOption({ label: 'Birds' });
    await expect(choice(patio, 'Off')).not.toHaveAttribute('disabled');
    await expect(page.locator('[data-camera-watch="patio"] [data-camera-watch-reason]')).toHaveCount(0);
    await patio.selectOption({ label: 'Off' });
    await expect(choice(watchFor(page, 'front'), 'Off')).toHaveAttribute('disabled');
    expect(await apply(page, harness, 1)).toEqual({
        cameras: ['front'], garden_cameras: [], garden_motion_cameras: [], camera_roles: {}
    });
});

test('with Garden off, each camera is a simple Birds or Off choice and Garden cameras are kept', async ({ page }) => {
    const harness = await openConnection(page, { beta_garden_animals: false, garden_cameras: ['patio'], garden_motion_cameras: ['patio'] });
    const patio = watchFor(page, 'patio');
    await expect(patio.locator('option')).toHaveText(['Off', 'Birds']);
    await expect(page.locator('[data-camera-garden-hint]')).toContainText('turn on Garden animals in Settings → Identifying birds');
    await patio.selectOption({ label: 'Off' });
    expect(await apply(page, harness, 1)).toEqual({
        cameras: ['front'], garden_cameras: ['patio'], garden_motion_cameras: ['patio'], camera_roles: {}
    });
});

test('a saved camera Frigate no longer lists stays visible, flagged, and can be cleared', async ({ page }) => {
    const harness = await openConnection(page, { cameras: ['patio', 'shed'], garden_cameras: ['pond'] });
    const shed = page.locator('[data-camera-watch="shed"]');
    await expect(shed.locator('[data-camera-missing]')).toHaveText('Not found in Frigate');
    await expect(page.locator('[data-camera-watch="pond"] [data-camera-missing]')).toHaveText('Not found in Frigate');
    await expect(page.locator('[data-camera-watch="patio"] [data-camera-missing]')).toHaveCount(0);
    await expect(shed.getByRole('button', { name: 'Preview shed' })).toHaveCount(0);
    await watchFor(page, 'shed').selectOption({ label: 'Off' });
    expect(await apply(page, harness, 1)).toEqual({
        cameras: ['patio'], garden_cameras: ['pond'], garden_motion_cameras: [], camera_roles: {}
    });
});

test('an unread Frigate list shows saved cameras without calling them missing', async ({ page }) => {
    await openConnection(page, { cameras: [], garden_cameras: ['pond'] }, null);
    await expect(page.locator('[data-camera-list-state]')).toContainText('The camera list could not be read from Frigate.');
    await expect(page.locator('[data-camera-missing]')).toHaveCount(0);
    const pond = watchFor(page, 'pond');
    await expect(chosen(pond)).toHaveText('Both');
    await expect(choice(pond, 'Garden animals')).toHaveAttribute('disabled');
    await expect(pond).toHaveAccessibleDescription('Every camera watches for birds. Sync cameras from Frigate before turning birds off for one camera.');
});

test('the watch choice works from the keyboard and shows focus', async ({ page }) => {
    await openConnection(page);
    const patio = watchFor(page, 'patio');
    // Arrive by keyboard (back one stop and forward again), so the focus is keyboard focus.
    await patio.focus();
    await page.keyboard.press('Shift+Tab');
    await page.keyboard.press('Tab');
    await expect(patio).toBeFocused();
    await page.keyboard.press('ArrowDown');
    await expect(chosen(patio)).toHaveText('Garden animals');
    await expect(patio).toBeFocused();
    const ring = await patio.evaluate(select => {
        const style = getComputedStyle(select);
        return style.boxShadow !== 'none' || (style.outlineStyle !== 'none' && style.outlineWidth !== '0px');
    });
    expect(ring).toBe(true);
});

test('Beta features summarises Garden cameras and opens the list in Connection', async ({ page }) => {
    await openConnection(page, { garden_cameras: ['patio', 'greenhouse'], garden_motion_cameras: ['greenhouse', 'front'] });
    await page.getByRole('link', { name: 'Identifying birds', exact: true }).click();
    const summary = page.locator('[data-garden-camera-summary]');
    await expect(summary).toContainText('Watching patio and greenhouse for Garden animals.');
    await expect(summary).toContainText('Motion review photos are collected on greenhouse.');
    await expect(page.getByRole('combobox', { name: /: watch for$/ })).toHaveCount(0);
    await summary.getByRole('button', { name: 'Choose cameras in Connection' }).click();
    await expect(page.locator('main[data-fixture-route]')).toHaveAttribute('data-fixture-route', '/settings/cameras');
    await expect(page.locator('[data-camera-list]')).toBeFocused();
});

for (const width of [320, 393]) {
    test(`camera rows fit ${width}px with 200% text and keep 44px targets`, async ({ page }) => {
        await openConnection(page, { garden_cameras: ['patio'], camera_roles: { front: 'nest' } });
        await page.setViewportSize({ width, height: 900 });
        await page.addStyleTag({ content: 'html{font-size:200%!important}' });
        const list = page.locator('[data-camera-list]');
        await expect(watchFor(page, 'patio')).toBeVisible();
        for (const row of await list.locator('[data-camera-watch]').all()) {
            // Name whatever sticks out past the row, so a failure says what to fix.
            const outside = await row.evaluate(node => {
                const edge = node.getBoundingClientRect().right + 1;
                return [...node.querySelectorAll<HTMLElement>('*')]
                    .filter(element => element.getBoundingClientRect().right > edge)
                    .map(element => `${element.tagName.toLowerCase()}.${element.className.toString().split(' ').slice(0, 3).join('.')}`);
            });
            expect(outside).toEqual([]);
            expect(await row.evaluate(node => node.scrollWidth <= node.clientWidth + 1)).toBe(true);
        }
        for (const target of await list.locator('[data-camera-watch] select, [data-camera-watch] button:not([role="switch"])').all()) {
            const box = await target.boundingBox();
            expect(box && box.height >= 44 && box.x >= 0 && box.x + box.width <= width).toBe(true);
        }
        await expect.poll(() => page.evaluate(() => [...document.querySelectorAll<HTMLElement>('main *')]
            .filter(element => element.getBoundingClientRect().right > innerWidth + 1)
            .map(element => `${element.tagName.toLowerCase()}.${element.className.toString().split(' ').slice(0, 3).join('.')}`))).toEqual([]);
        await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    });
}
