import { expect, test, type Page } from '@playwright/test';
import { discardButton, openSaveDetails, openSettings, saveBar, saveButton, saveDetails } from './settings-page-mock';

// Integrations holds every external service and Notifications every way YA-WAMF tells you
// something. This drives both through the real Settings page: what each section shows, that a
// draft in a moved control survives leaving its section, that each channel's photo switch saves,
// and that the custom rules behind the delivery sentence can be set.

const rail = (page: Page) => page.locator('[data-settings-navigation]');
const section = (page: Page, name: string) => rail(page).getByRole('link', { name, exact: true });
const group = (page: Page, id: string) => page.locator(`#${id}`);
const noSidewaysScroll = (page: Page): Promise<boolean> => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

for (const width of [1440, 390] as const) {
    test.describe(`at ${width}px`, () => {
        // The page opens at the fixture's desktop size, where its section list is the sign it has
        // drawn, and is then given the width under test.
        const atWidth = (page: Page): Promise<void> => page.setViewportSize({ width, height: 900 });

        test('Integrations shows every service on its first screen, each with its switch and its state in words', async ({ page }) => {
            await openSettings(page, { birdnet_enabled: true, audio_topic: 'birdnet/text', ebird_enabled: true }, { route: '/settings/integrations' });
            await atWidth(page);
            await expect(page.getByRole('heading', { level: 2, name: 'Integrations', exact: true })).toBeVisible();
            for (const name of ['BirdNET-Go', 'Home Assistant weather', 'iNaturalist', 'eBird', 'BirdWeather', 'AI provider']) {
                await expect(page.getByRole('heading', { level: 3, name, exact: true }), name).toBeVisible();
            }
            // Nothing is measured in the background, so a state never says "connected".
            await expect(group(page, 'settings-group-integrations-birdnet').locator('[data-settings-card-status]')).toHaveText('On and set up. Not tested on this visit: test results are not kept.');
            await expect(group(page, 'settings-group-integrations-ebird').locator('[data-settings-card-status]')).toHaveText('On, but not set up: add an API key.');
            await expect(group(page, 'settings-group-integrations-birdweather').locator('[data-settings-card-status]')).toHaveText('Off.');
            await expect(group(page, 'settings-group-integrations-ha-weather').locator('[data-settings-card-status]')).toHaveText('Off.');
            // Only where species pages get their information is behind More options.
            await expect(page.locator('[data-settings-more] > h3 > button')).toHaveAttribute('aria-expanded', 'false');
            await expect(page.locator('[data-enrichment-summary]')).toHaveCount(0);
            // Frigate, MQTT and the location are named in words, with a link to each.
            const elsewhere = page.locator('[data-integrations-elsewhere]');
            await expect(elsewhere).toContainText('they are set in Cameras & connection');
            await expect(elsewhere.getByRole('link', { name: 'Open Frigate and MQTT' })).toHaveAttribute('href', '/settings/cameras#connection');
            await expect(elsewhere.getByRole('link', { name: 'Open your feeder’s location' })).toHaveAttribute('href', '/settings/cameras#location');
            expect(await noSidewaysScroll(page)).toBe(true);
        });

        test('Notifications shows the sentence, every channel and Garden alerts on its first screen', async ({ page }) => {
            await openSettings(page, { beta_garden_animals: true, notifications_discord_enabled: true, notifications_discord_webhook_url: '***REDACTED***' }, { route: '/settings/notifications' });
            await atWidth(page);
            await expect(page.getByRole('heading', { level: 2, name: 'Notifications', exact: true })).toBeVisible();
            for (const name of ['Global notification filters', 'Channels', 'Garden animal alerts']) {
                await expect(page.getByRole('heading', { level: 3, name, exact: true }), name).toBeVisible();
            }
            for (const channel of ['discord', 'pushover', 'telegram', 'email']) {
                await expect(page.locator(`[data-notification-channel="${channel}"]`), channel).toBeVisible();
            }
            await expect(page.locator('[data-notification-channel="discord"]').getByRole('switch', { name: 'Send the photo' })).toHaveAttribute('aria-checked', 'true');
            await expect(page.locator('[data-settings-more] > h3 > button')).toHaveAttribute('aria-expanded', 'false');
            expect(await noSidewaysScroll(page)).toBe(true);
        });
    });
}

test('a test that fails says so in the group\'s own state, with the time and the reason', async ({ page }) => {
    await openSettings(page, { birdweather_enabled: true, birdweather_station_token: '***REDACTED***' }, {
        route: '/settings/integrations',
        respond: (path, method) => (path === '/api/settings/birdweather/test' && method === 'POST'
            ? { json: { status: 'error', message: 'BirdWeather did not accept the station token.' } }
            : undefined)
    });
    const birdweather = group(page, 'settings-group-integrations-birdweather');
    const state = birdweather.locator('[data-settings-card-status]');
    await expect(state).toHaveText('On and set up. Not tested on this visit: test results are not kept.');
    await birdweather.getByRole('button', { name: 'Test connection' }).click();
    const dialog = page.getByRole('dialog', { name: 'BirdWeather connection test' });
    await expect(dialog).toContainText('BirdWeather did not accept the station token.');
    await dialog.getByRole('button', { name: 'Close' }).first().click();
    await expect(state).toHaveText(/^On, but the test failed at \d{1,2}:\d{2}.*: BirdWeather did not accept the station token\.$/);
    // Typing a new token retires the result: it described the old one.
    await birdweather.locator('#birdweather-token').fill('new-token');
    await expect(state).toHaveText('On and set up. Not tested on this visit: test results are not kept.');
});

test('an unsaved change to a moved setting survives leaving its section, and the save bar names where it is now', async ({ page }) => {
    const harness = await openSettings(page, { birdnet_enabled: true, birdnet_url: 'http://birdnet:8080', audio_topic: 'birdnet/text', location_automatic: false, location_latitude: 51.5, location_longitude: -0.1 }, {
        route: '/settings/integrations',
        respond: (path) => (path.endsWith('/location/reverse-geocode') ? { json: { place_guess: 'Westminster', state: 'England', country: 'United Kingdom' } } : undefined)
    });
    await page.locator('#birdnet-url').fill('http://birdnet.lan:8080');
    await expect(saveBar(page)).toContainText('1 unsaved change');
    await expect(section(page, 'Integrations')).toContainText('unsaved');

    // The location moved to Cameras & connection: an edit there is counted in that section.
    await section(page, 'Cameras & connection').click();
    await expect(page.locator('#birdnet-url')).toHaveCount(0);
    await page.locator('#location-lat').fill('52.2');
    await expect(saveBar(page)).toContainText('unsaved changes');
    await openSaveDetails(page);
    await expect(saveDetails(page).getByRole('button', { name: 'Cameras & connection', exact: true })).toBeVisible();
    await expect(saveDetails(page).getByRole('button', { name: 'Integrations', exact: true })).toBeVisible();

    await section(page, 'Access & privacy').click();
    await section(page, 'Integrations').click();
    await expect(page.locator('#birdnet-url')).toHaveValue('http://birdnet.lan:8080');
    await saveButton(page).click();
    await expect.poll(() => harness.writes.length).toBe(1);
    expect(harness.writes[0]).toMatchObject({ birdnet_url: 'http://birdnet.lan:8080', location_latitude: 52.2 });
    await expect(saveBar(page)).toHaveCount(0);
});

for (const channel of ['discord', 'pushover', 'telegram'] as const) {
    test(`${channel}: Send the photo saves, and a later save keeps it`, async ({ page }) => {
        const harness = await openSettings(page, {
            notifications_discord_enabled: true, notifications_discord_webhook_url: '***REDACTED***',
            notifications_pushover_enabled: true, notifications_pushover_user_key: '***REDACTED***', notifications_pushover_api_token: '***REDACTED***',
            notifications_telegram_enabled: true, notifications_telegram_bot_token: '***REDACTED***', notifications_telegram_chat_id: '***REDACTED***'
        }, { route: '/settings/notifications' });
        const photo = page.locator(`[data-notification-channel="${channel}"]`).getByRole('switch', { name: 'Send the photo' });
        await expect(photo).toHaveAttribute('aria-checked', 'true');
        await photo.click();
        await expect(photo).toHaveAttribute('aria-checked', 'false');
        await expect(saveBar(page)).toContainText('1 unsaved change');
        await saveButton(page).click();
        await expect.poll(() => harness.writes.length).toBe(1);
        expect(harness.writes[0][`notifications_${channel}_include_snapshot`]).toBe(false);
        for (const other of ['discord', 'pushover', 'telegram'].filter((name) => name !== channel)) {
            expect(harness.writes[0][`notifications_${other}_include_snapshot`], other).toBe(true);
        }
        // A stored secret stays stored: the redaction placeholder is never written back.
        expect(JSON.stringify(harness.writes[0])).not.toContain('***REDACTED***');
        await expect(saveBar(page)).toHaveCount(0);
        await expect(photo).toHaveAttribute('aria-checked', 'false');
    });
}

test('custom rules are reached from the sentence, and a changed switch is saved as a custom mode', async ({ page }) => {
    const harness = await openSettings(page, { notifications_mode: 'standard', notifications_notify_on_insert: true, notifications_notify_on_update: false, notifications_delay_until_video: false }, { route: '/settings/notifications' });
    await page.getByRole('button', { name: /^new visits/ }).click();
    const menu = page.getByRole('dialog', { name: 'Notification mode' });
    await expect(menu.locator('[data-policy-custom-rules]')).toContainText('Set the exact triggers with the Custom rules switches under this sentence.');
    await menu.locator('[data-policy-custom-rules]').click();
    const onInsert = page.getByRole('switch', { name: 'When a visit is first recorded' });
    await expect(onInsert).toBeFocused();
    await expect(onInsert).toHaveAttribute('aria-checked', 'true');
    // Opening them changes nothing.
    await expect(saveBar(page)).toHaveCount(0);

    await page.getByRole('switch', { name: 'When a visit changes' }).click();
    await expect(page.getByRole('button', { name: /^custom rules/ })).toBeVisible();
    await saveButton(page).click();
    await expect.poll(() => harness.writes.length).toBe(1);
    expect(harness.writes[0]).toMatchObject({ notifications_mode: 'custom', notifications_notify_on_insert: true, notifications_notify_on_update: true, notifications_delay_until_video: false });

    // A preset in the sentence sets all three again.
    await page.getByRole('button', { name: /^custom rules/ }).click();
    await page.getByRole('dialog', { name: 'Notification mode' }).getByRole('button', { name: /^new visits/ }).click();
    await expect(page.getByRole('switch', { name: 'When a visit changes' })).toHaveAttribute('aria-checked', 'false');
    await discardButton(page).click();
    await expect(page.getByRole('switch', { name: 'When a visit changes' })).toHaveAttribute('aria-checked', 'true');
});

test('search finds a moved setting and opens it where it is now', async ({ page }) => {
    await openSettings(page, { ebird_enabled: true, ebird_api_key: '***REDACTED***' });
    const box = page.locator('[data-settings-search-input]');
    await box.fill('ebird api key');
    const option = page.getByRole('option').first();
    await expect(option).toContainText('Integrations');
    await expect(option).not.toContainText('More options');
    await box.press('Enter');
    await expect(section(page, 'Integrations')).toHaveAttribute('aria-current', 'page');
    // Focus lands inside eBird's own group, on the key's control.
    await expect(page.locator('[data-settings-found]')).toHaveCount(1);
    await expect.poll(() => page.evaluate(() => Boolean(document.activeElement?.closest('#settings-group-integrations-ebird')))).toBe(true);
    await expect(page.locator('[data-settings-more] > h3 > button')).toHaveAttribute('aria-expanded', 'false');

    await box.fill('latitude');
    await box.press('Enter');
    await expect(section(page, 'Cameras & connection')).toHaveAttribute('aria-current', 'page');
    await expect(page.locator('[data-settings-found]')).toHaveCount(1);
});
