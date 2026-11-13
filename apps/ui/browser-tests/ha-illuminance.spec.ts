import { expect, test, type Page } from '@playwright/test';
import { openSettings } from './settings-page-mock';

// A Home Assistant light sensor (#945): the settings field, its live test and the stored value on a
// record. Home Assistant itself is never called; the server's answers are fixtures.
// Set HA_ILLUMINANCE_SHOTS to a directory to keep review screenshots outside the test output.
const shots = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env.HA_ILLUMINANCE_SHOTS;

const CONNECTED = {
    ha_weather_enabled: true,
    ha_weather_base_url: 'http://homeassistant.local:8123',
    ha_weather_access_token: '***REDACTED***',
    ha_weather_entity: 'weather.home'
};

interface TestRequest { scope?: string; illuminance_entity?: string; weather_entity?: string }

async function answerLiveTest(page: Page, illuminance: Record<string, unknown>): Promise<TestRequest[]> {
    const requests: TestRequest[] = [];
    await page.route(url => url.pathname === '/api/settings/ha-weather/test', async route => {
        const body = route.request().postDataJSON() as TestRequest;
        requests.push(body);
        if (body.scope === 'illuminance') {
            return route.fulfill({ json: {
                status: illuminance.status, message: 'Illuminance entity read.', readings: {}, weather: 'not_configured',
                illuminance: { entity_id: body.illuminance_entity, ...illuminance }
            } });
        }
        return route.fulfill({ json: {
            status: 'ok', message: '3 reading(s) received from Home Assistant.', weather: 'ok', illuminance: null,
            readings: { temperature: 9, condition_text: 'Cloudy', cloud_cover: 80 }
        } });
    });
    return requests;
}

async function openHomeAssistantCard(page: Page, saved: Record<string, unknown> = CONNECTED) {
    const harness = await openSettings(page, saved);
    await page.getByRole('link', { name: 'Integrations', exact: true }).click();
    await expect(page.locator('#ha-weather-illuminance')).toBeVisible();
    return harness;
}

test('the illuminance entity is optional, sits beside the weather entity and saves with the page', async ({ page }) => {
    const harness = await openHomeAssistantCard(page);
    const field = page.getByRole('textbox', { name: 'Illuminance entity' });
    await expect(field).toHaveValue('');
    await expect(field).toHaveAccessibleDescription(/Optional\. A light sensor that reports lx/);
    await expect(page.getByText('Unsaved Changes', { exact: true })).toHaveCount(0);

    // Same column, directly under the weather entity and above the overrides disclosure.
    const weatherBox = await page.locator('#ha-weather-entity').boundingBox();
    const fieldBox = await field.boundingBox();
    const overridesBox = await page.getByText('Per-reading sensor overrides', { exact: true }).boundingBox();
    if (!weatherBox || !fieldBox || !overridesBox) throw new Error('Home Assistant fields are not laid out');
    expect(fieldBox.x).toBe(weatherBox.x);
    expect(fieldBox.width).toBe(weatherBox.width);
    expect(fieldBox.height).toBe(weatherBox.height);
    expect(fieldBox.y).toBeGreaterThan(weatherBox.y);
    expect(overridesBox.y).toBeGreaterThan(fieldBox.y);

    await field.fill('  sensor.feeder_illuminance ');
    await expect(field).not.toHaveAttribute('aria-invalid', 'true');
    if (shots) await page.locator('#ha-weather-illuminance').locator('xpath=ancestor::section[1]').screenshot({ path: `${shots}/settings-illuminance-field.png` });
    await page.getByRole('button', { name: 'Apply Settings', exact: true }).click();
    await expect.poll(() => harness.writes.length).toBe(1);
    expect(harness.writes[0]).toMatchObject({ ha_weather_illuminance_entity: 'sensor.feeder_illuminance', ha_weather_entity: 'weather.home' });
});

test('a value that is not an entity id is explained in words beside the field', async ({ page }) => {
    await openHomeAssistantCard(page);
    const field = page.getByRole('textbox', { name: 'Illuminance entity' });
    await field.fill('Feeder light sensor');
    await expect(field).toHaveAttribute('aria-invalid', 'true');
    await expect(field).toHaveAccessibleDescription(/This is not an entity id\. Use the id Home Assistant shows/);
    await expect(page.locator('#ha-weather-illuminance-error')).toBeVisible();
    if (shots) await page.locator('#ha-weather-illuminance').locator('xpath=ancestor::section[1]').screenshot({ path: `${shots}/settings-illuminance-invalid.png` });

    await field.fill('sensor.feeder_illuminance');
    await expect(page.locator('#ha-weather-illuminance-error')).toHaveCount(0);
    await expect(field).not.toHaveAttribute('aria-invalid', 'true');
});

test('the live test shows the measured light level in its own stage', async ({ page }) => {
    await openHomeAssistantCard(page);
    const requests = await answerLiveTest(page, { status: 'ok', lux: 1240.5, reason: null });
    await page.getByRole('textbox', { name: 'Illuminance entity' }).fill('sensor.feeder_illuminance');
    await page.getByRole('button', { name: 'Fetch a live reading', exact: true }).click();

    const dialog = page.getByRole('dialog', { name: 'Home Assistant weather test' });
    await expect(dialog.getByText('1,241 lx measured by sensor.feeder_illuminance.').first()).toBeVisible();
    await expect(dialog.getByText('Light level from the illuminance entity', { exact: true })).toBeVisible();
    await expect(dialog.getByText('3 reading(s) received from Home Assistant.', { exact: true })).toBeVisible();
    // The typed, unsaved entity is what was tested, one request per stage.
    expect(requests.map(request => request.scope)).toEqual(['weather', 'illuminance']);
    expect(requests[1].illuminance_entity).toBe('sensor.feeder_illuminance');
    if (shots) await dialog.screenshot({ path: `${shots}/live-test-light-measured.png` });
});

for (const [reason, sentence] of [
    ['unavailable', 'sensor.feeder_illuminance is unknown or unavailable in Home Assistant right now. Detections record no light level until it answers.'],
    ['not_illuminance', 'sensor.feeder_illuminance is not an illuminance sensor. Choose a sensor with the illuminance device class or the unit lx.'],
    ['out_of_range', 'sensor.feeder_illuminance reported a value outside 0 to 200,000 lx, so it is not recorded.']
] as const) {
    test(`the live test says why the light level is missing (${reason})`, async ({ page }) => {
        await openHomeAssistantCard(page);
        await answerLiveTest(page, { status: 'error', lux: null, reason });
        await page.getByRole('textbox', { name: 'Illuminance entity' }).fill('sensor.feeder_illuminance');
        await page.getByRole('button', { name: 'Fetch a live reading', exact: true }).click();

        const dialog = page.getByRole('dialog', { name: 'Home Assistant weather test' });
        await expect(dialog.getByText(sentence).first()).toBeVisible();
        await expect(dialog.getByText(/lx measured by/)).toHaveCount(0);
        if (shots && reason === 'unavailable') await dialog.screenshot({ path: `${shots}/live-test-light-missing.png` });
    });
}

test('with only a light sensor named, the live test runs the light stage alone', async ({ page }) => {
    await openHomeAssistantCard(page, { ...CONNECTED, ha_weather_entity: null, ha_weather_illuminance_entity: 'sensor.feeder_illuminance' });
    const requests = await answerLiveTest(page, { status: 'ok', lux: 0.42, reason: null });
    await expect(page.getByRole('textbox', { name: 'Illuminance entity' })).toHaveValue('sensor.feeder_illuminance');
    await page.getByRole('button', { name: 'Fetch a live reading', exact: true }).click();

    const dialog = page.getByRole('dialog', { name: 'Home Assistant weather test' });
    await expect(dialog.getByText('0.4 lx measured by sensor.feeder_illuminance.').first()).toBeVisible();
    await expect(dialog.getByText('Live readings from Home Assistant', { exact: true })).toHaveCount(0);
    expect(requests.map(request => request.scope)).toEqual(['illuminance']);
});

async function openRecord(page: Page, query: string): Promise<void> {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route(url => url.pathname.startsWith('/api/'), async route => {
        const path = new URL(route.request().url()).pathname;
        if (path.endsWith('/snapshot/candidates')) return route.fulfill({ json: { candidates: [], birds: [], current_source: 'frigate_snapshot' } });
        if (path.endsWith('/snapshot/status')) return route.fulfill({ json: { available: true, source: 'frigate_snapshot' } });
        if (path.endsWith('.jpg')) return route.fulfill({ contentType: 'image/svg+xml', body:
            '<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="600"><rect width="1000" height="600" fill="#64748b"/></svg>' });
        if (path.startsWith('/api/audio/context/') || path === '/api/species/search' || path.includes('/conversation')) return route.fulfill({ json: [] });
        return route.fulfill({ json: {} });
    });
    await page.goto(`/browser-tests/modal-text-layout.html${query}`);
    await expect(page.locator('[data-detection-detail-modal]')).toBeVisible();
}

test('a record states its measured light level in the conditions row', async ({ page }) => {
    await openRecord(page, '?light=1240.5');
    const conditions = page.locator('[data-detection-weather-row]');
    await expect(conditions).toHaveCount(1);
    await expect(conditions.locator('dd')).toHaveText('Cloudy 9.0°C · Cloud Cover 80% · Light 1,241 lx');
    if (shots) await conditions.screenshot({ path: `${shots}/record-conditions-light.png` });
});

test('a light level is shown even when no weather was recorded, and in the dark it keeps a decimal', async ({ page }) => {
    await openRecord(page, '?light=only');
    await expect(page.locator('[data-detection-weather-row] dd')).toHaveText('Light 0.4 lx');
});

test('a record with no measured light level says nothing about light', async ({ page }) => {
    await openRecord(page, '');
    await expect(page.locator('[data-detection-detail-modal]')).not.toContainText('Light');
    await expect(page.locator('[data-detection-weather-row]')).toHaveCount(0);
});
