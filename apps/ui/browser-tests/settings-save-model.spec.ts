import { expect, test, type Page } from '@playwright/test';
import { discardButton, openSettings, saveBar, saveButton } from './settings-page-mock';

// Settings keeps one draft with one Save. The save bar must be honest about it: present only while
// a saved value would change, naming where the changes are, able to throw them away, and putting a
// refused value back on its own field in plain words.

const tabLink = (page: Page, name: string) => page.locator('[data-settings-navigation]').getByRole('link', { name, exact: true });

test('Integrations opens with nothing unsaved, even when the place lookup names a saved location differently', async ({ page }) => {
    let lookups = 0;
    await openSettings(page, {
        location_latitude: 51.5,
        location_longitude: -0.12,
        location_automatic: false,
        location_state: '',
        location_country: '',
        inaturalist_enabled: true,
        inaturalist_default_latitude: null,
        inaturalist_default_longitude: null,
        inaturalist_default_place_guess: null
    }, {
        respond: (path) => {
            if (!path.endsWith('/location/reverse-geocode')) return undefined;
            lookups += 1;
            return { json: { place_guess: 'Westminster, England', state: 'England', country: 'United Kingdom' } };
        }
    });
    await tabLink(page, 'Integrations').click();
    await expect(page.locator('#birdnet-url')).toBeVisible();
    await expect.poll(() => lookups).toBeGreaterThan(0);
    // Give a late effect the chance to write into the draft before asserting nothing did.
    await page.waitForTimeout(300);
    await expect(saveBar(page)).toHaveCount(0);

    // Moving the pin is an edit: the looked-up region now belongs to the draft.
    await page.locator('#location-lat').fill('52.2');
    await expect(saveBar(page)).toBeVisible();
    await expect(saveBar(page)).toContainText('Integrations');
});

test('the save bar counts the changes, names their tabs, and Discard restores every saved value', async ({ page }) => {
    const harness = await openSettings(page, {
        mqtt_auth: true,
        mqtt_username: 'feeder',
        mqtt_password: '***REDACTED***',
        llm_enabled: true,
        llm_provider: 'gemini',
        llm_api_key: '***REDACTED***',
        llm_model: 'gemini-3.1-pro-preview'
    });
    await expect(saveBar(page)).toHaveCount(0);

    await page.locator('#mqtt-server').fill('broker.lan');
    await page.locator('#frigate-url').fill('http://frigate.lan:5000');
    await tabLink(page, 'AI').click();
    await page.getByRole('button', { name: 'Claude', exact: true }).click();
    await expect(page.locator('#llm-model')).toHaveValue('claude-opus-4-8');

    // Frigate URL and MQTT broker on Connection; provider and the model it brings on AI.
    await expect(saveBar(page)).toContainText('4 unsaved changes');
    await expect(saveBar(page).getByRole('button', { name: 'Connection', exact: true })).toBeVisible();
    await expect(saveBar(page).getByRole('button', { name: 'AI', exact: true })).toBeVisible();

    await saveBar(page).getByRole('button', { name: 'Connection', exact: true }).click();
    await expect(page.locator('#mqtt-server')).toHaveValue('broker.lan');

    await discardButton(page).click();
    await expect(saveBar(page)).toHaveCount(0);
    await expect(page.locator('#mqtt-server')).toHaveValue('mqtt');
    await expect(page.locator('#frigate-url')).toHaveValue('http://frigate:5000');
    await tabLink(page, 'AI').click();
    await expect(page.locator('#llm-model')).toHaveValue('gemini-3.1-pro-preview');
    expect(harness.writes).toEqual([]);

    // A save after Discard sends the saved values, and a stored secret stays stored: its field is
    // empty and the redaction placeholder is never written back.
    await tabLink(page, 'Connection').click();
    await page.locator('#mqtt-server').fill('broker.lan');
    await saveButton(page).click();
    await expect.poll(() => harness.writes.length).toBe(1);
    expect(harness.writes[0]).toMatchObject({ mqtt_server: 'broker.lan', mqtt_password: '', llm_provider: 'gemini', llm_api_key: '' });
    expect(JSON.stringify(harness.writes[0])).not.toContain('***REDACTED***');
});

test('a refused save puts each reason on its own field, in plain words, until the field is corrected', async ({ page }) => {
    await openSettings(page, {}, {
        refuseWrite: () => ({
            status: 422,
            json: { detail: [
                { type: 'value_error', loc: ['body', 'frigate_url'], msg: 'Value error, frigate_url must start with http:// or https://' },
                { type: 'less_than_equal', loc: ['body', 'mqtt_port'], msg: 'Input should be less than or equal to 65535', ctx: { le: 65535 } }
            ] }
        })
    });
    await page.locator('#frigate-url').fill('frigate.lan');
    await saveButton(page).click();

    const url = page.locator('#frigate-url');
    await expect(url).toHaveAttribute('aria-invalid', 'true');
    const describedBy = await url.getAttribute('aria-describedby');
    expect(describedBy).toBeTruthy();
    const reason = page.locator(`[id="${(describedBy ?? '').split(' ').at(-1)}"]`);
    await expect(reason).toHaveText('Start the address with http:// or https://, for example http://frigate:5000.');

    // The bar says nothing was saved and lists each refused field by its label, with its tab.
    await expect(saveBar(page)).toContainText('Nothing was saved');
    await expect(saveBar(page).getByRole('button', { name: 'Server URL (Connection)', exact: true })).toBeVisible();
    await expect(saveBar(page).getByRole('button', { name: 'Port (Connection)', exact: true })).toBeVisible();
    // No backend field key or validator wording reaches the screen, and the reason is shown once.
    await expect(page.locator('body')).not.toContainText('frigate_url');
    await expect(page.locator('body')).not.toContainText('Input should be');
    await expect(page.locator('[data-toast]')).toHaveCount(0);

    await url.fill('http://frigate.lan:5000');
    await expect(url).not.toHaveAttribute('aria-invalid', 'true');
    await expect(saveBar(page).getByRole('button', { name: 'Server URL (Connection)', exact: true })).toHaveCount(0);
});

test('a save that fails on the server says nothing was saved and what to try, once', async ({ page }) => {
    await openSettings(page, {}, { refuseWrite: () => ({ status: 500, json: { detail: 'Internal Server Error' } }) });
    await page.locator('#mqtt-server').fill('broker.lan');
    await saveButton(page).click();
    await expect(saveBar(page)).toContainText('Nothing was saved');
    await expect(saveBar(page)).toContainText('try Save changes again');
    await expect(page.getByText('Internal Server Error')).toHaveCount(0);
    await expect(page.locator('[data-toast]')).toHaveCount(0);
});

test('a successful save is reported once', async ({ page }) => {
    await openSettings(page);
    await page.locator('#mqtt-server').fill('broker.lan');
    await saveButton(page).click();
    await expect(page.locator('[data-toast]').filter({ hasText: 'Settings saved' })).toHaveCount(1);
    await expect(page.getByText('Settings saved')).toHaveCount(1);
    await expect(saveBar(page)).toHaveCount(0);
});

for (const viewport of [{ width: 390, height: 844 }, { width: 1440, height: 900 }]) {
    test(`at ${viewport.width}px the save bar never covers the end of the page`, async ({ page }) => {
        await page.setViewportSize(viewport);
        await openSettings(page);
        await page.locator('#mqtt-server').fill('broker.lan');
        await expect(saveBar(page)).toBeVisible();
        await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
        const content = await page.locator('[data-settings-content]').boundingBox();
        const bar = await saveBar(page).boundingBox();
        expect(content).not.toBeNull();
        expect(bar).not.toBeNull();
        expect((content?.y ?? 0) + (content?.height ?? 0)).toBeLessThanOrEqual((bar?.y ?? 0) + 1);
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
        expect(overflow).toBeLessThanOrEqual(1);
    });
}
