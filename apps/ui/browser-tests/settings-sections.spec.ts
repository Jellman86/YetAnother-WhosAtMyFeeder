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
            await expect(group(page, 'settings-group-integrations-birdnet').locator('[data-settings-card-status]')).toHaveText('On and set up. Not tested yet; test results aren\u2019t kept between visits.');
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
    await expect(state).toHaveText('On and set up. Not tested yet; test results aren\u2019t kept between visits.');
    await birdweather.getByRole('button', { name: 'Test connection' }).click();
    const dialog = page.getByRole('dialog', { name: 'BirdWeather connection test' });
    await expect(dialog).toContainText('BirdWeather did not accept the station token.');
    await dialog.getByRole('button', { name: 'Close' }).first().click();
    await expect(state).toHaveText(/^On, but the test failed at \d{1,2}:\d{2}.*: BirdWeather did not accept the station token\.$/);
    // Typing a new token retires the result: it described the old one.
    await birdweather.locator('#birdweather-token').fill('new-token');
    await expect(state).toHaveText('On and set up. Not tested yet; test results aren\u2019t kept between visits.');
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

test('custom rules are a choice in the sentence; their switches cannot be changed on any other choice', async ({ page }) => {
    const harness = await openSettings(page, { notifications_mode: 'realtime', notifications_notify_on_insert: true, notifications_notify_on_update: true, notifications_delay_until_video: false }, { route: '/settings/notifications' });
    // On "every update" the switches are shown, but disabled, with the reason beside them.
    await page.locator('[data-advanced-section] > button', { hasText: 'Custom rules' }).click();
    const later = page.getByRole('switch', { name: 'Later, if no alert has gone' });
    await expect(later).toBeDisabled();
    await expect(page.getByRole('switch', { name: 'When a visit starts' })).toBeDisabled();
    await expect(page.getByRole('switch', { name: 'Wait for the video check' })).toBeDisabled();
    await expect(page.locator('[data-custom-rules-note="inactive"]')).toContainText('can be changed only with custom rules');
    await later.click({ force: true });
    await expect(later).toHaveAttribute('aria-checked', 'true');
    // Looking at them, and pressing one, changed nothing.
    await expect(saveBar(page)).toHaveCount(0);

    // Custom rules is chosen in the sentence, which says what it costs: one alert per visit.
    await page.getByRole('button', { name: /^every update/ }).click();
    const menu = page.getByRole('dialog', { name: 'Notification mode' });
    await expect(menu.locator('[data-policy-custom-rules]')).toContainText('At most one alert per visit.');
    await menu.locator('[data-policy-custom-rules]').click();
    await expect(page.getByRole('button', { name: /^custom rules/ })).toBeVisible();
    await expect(page.locator('[data-custom-rules-note="active"]')).toContainText('A visit sends at most one alert');
    const starts = page.getByRole('switch', { name: 'When a visit starts' });
    await expect(starts).toBeFocused();
    await expect(starts).toBeEnabled();
    await expect(later).toBeEnabled();
    await later.click();
    await expect(later).toHaveAttribute('aria-checked', 'false');
    await saveButton(page).click();
    await expect.poll(() => harness.writes.length).toBe(1);
    expect(harness.writes[0]).toMatchObject({ notifications_mode: 'custom', notifications_notify_on_insert: true, notifications_notify_on_update: false, notifications_delay_until_video: false });

    // A preset in the sentence sets all three again, and locks them.
    await page.getByRole('button', { name: /^custom rules/ }).click();
    await page.getByRole('dialog', { name: 'Notification mode' }).getByRole('button', { name: /^every update/ }).click();
    await expect(later).toHaveAttribute('aria-checked', 'true');
    await expect(later).toBeDisabled();
    // Returning to custom rules restores the owner's custom triggers without leaving phantom changes.
    await page.getByRole('button', { name: /^every update/ }).click();
    await page.getByRole('dialog', { name: 'Notification mode' }).locator('[data-policy-custom-rules]').click();
    await expect(later).toHaveAttribute('aria-checked', 'false');
    await expect(later).toBeEnabled();
    await expect(saveBar(page)).toHaveCount(0);

    // Switching to a preset and clicking Discard also restores the saved custom rules.
    await page.getByRole('button', { name: /^custom rules/ }).click();
    await page.getByRole('dialog', { name: 'Notification mode' }).getByRole('button', { name: /^every update/ }).click();
    await expect(later).toHaveAttribute('aria-checked', 'true');
    await expect(later).toBeDisabled();
    await discardButton(page).click();
    await expect(later).toHaveAttribute('aria-checked', 'false');
    await expect(later).toBeEnabled();
});

test('a test result is still shown after opening another section and coming back', async ({ page }) => {
    await openSettings(page, { birdweather_enabled: true, birdweather_station_token: '***REDACTED***' }, {
        route: '/settings/integrations',
        respond: (path, method) => (path === '/api/settings/birdweather/test' && method === 'POST'
            ? { json: { status: 'error', message: 'BirdWeather did not accept the station token.' } }
            : undefined)
    });
    const state = group(page, 'settings-group-integrations-birdweather').locator('[data-settings-card-status]');
    await group(page, 'settings-group-integrations-birdweather').getByRole('button', { name: 'Test connection' }).click();
    await page.getByRole('dialog', { name: 'BirdWeather connection test' }).getByRole('button', { name: 'Close' }).first().click();
    const failed = /^On, but the test failed at \d{1,2}:\d{2}.*: BirdWeather did not accept the station token\.$/;
    await expect(state).toHaveText(failed);
    const said = await state.innerText();

    await section(page, 'Display').click();
    await expect(group(page, 'settings-group-integrations-birdweather')).toHaveCount(0);
    await section(page, 'Integrations').click();
    // The same result, with the same time: it was run on this visit, and the card still says so.
    await expect(state).toHaveText(said);
    // An edit to what it ran with still retires it.
    await page.locator('#birdweather-token').fill('new-token');
    await expect(state).toHaveText('On and set up. Not tested yet; test results aren\u2019t kept between visits.');
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

test('a row with only a switch reads at the card\'s measure, and the AI provider has its switch at its heading', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await openSettings(page, { beta_garden_animals: true }, { route: '/settings/notifications' });
    // "Send Garden alerts": a label, its help and a switch. The words take the room a field would.
    const garden = page.locator('[data-garden-alerts] [data-settings-row]').first();
    await expect(garden).toBeVisible();
    const measure = async (row: typeof garden): Promise<{ words: number; row: number }> => ({
        words: (await row.locator(':scope > div').first().boundingBox())?.width ?? 0,
        row: (await row.boundingBox())?.width ?? 0
    });
    const gardenSizes = await measure(garden);
    expect(gardenSizes.words).toBeGreaterThan(gardenSizes.row * 0.75);
    // The switch still ends on the card's right edge.
    const toggle = await garden.getByRole('switch').boundingBox();
    const rowBox = await garden.boundingBox();
    expect(Math.abs((toggle?.x ?? 0) + (toggle?.width ?? 0) - ((rowBox?.x ?? 0) + (rowBox?.width ?? 0)))).toBeLessThan(2);

    // The cooldown keeps that measure off and on: its minutes sit under its words.
    await page.locator('[data-settings-more] > h3 > button').click();
    const cooldown = page.locator('[data-notification-cooldown]');
    const off = await measure(cooldown);
    expect(off.words).toBeGreaterThan(off.row * 0.75);
    await cooldown.getByRole('switch', { name: 'Notification cooldown' }).click();
    await expect(page.locator('#notification-cooldown-minutes')).toBeVisible();
    expect((await measure(cooldown)).words).toBe(off.words);
    // The custom rule with a seconds field keeps the measure too.
    await page.locator('[data-advanced-section] > button', { hasText: 'Custom rules' }).click();
    const videoWait = await measure(page.locator('[data-settings-row]', { has: page.locator('#setting-notify-delay-video') }));
    expect(videoWait.words).toBeGreaterThan(videoWait.row * 0.75);
    // No run of space between the Telegram link's words and what follows them.
    const preview = page.getByText('Link on Telegram\'s button:', { exact: false }).first();
    const [label, value] = [await preview.boundingBox(), await page.getByText('none yet, so Telegram messages have no button.').boundingBox()];
    expect((value?.x ?? 0) - ((label?.x ?? 0) + (label?.width ?? 0))).toBeLessThanOrEqual(6);

    await section(page, 'Integrations').click();
    const ai = group(page, 'settings-group-ai-connection');
    const aiSwitch = ai.locator('header').getByRole('switch', { name: 'AI provider' });
    await expect(aiSwitch).toHaveAttribute('aria-checked', 'false');
    await expect(ai.locator('[data-settings-card-status]')).toHaveText('Off.');
    await expect(page.locator('#llm-model')).toHaveCount(0);
    await aiSwitch.click();
    await expect(ai.locator('[data-settings-card-status]')).toHaveText('On, but not set up: add an API key.');
    await expect(page.locator('#llm-model')).toBeVisible();
});

test('the status column calls it Notifications', async ({ page }) => {
    await openSettings(page, {}, {
        route: '/settings/notifications',
        respond: (path) => (path === '/api/status' ? { json: { captured_at: new Date().toISOString(), subsystems: [{ key: 'notifications', state: 'off', cause: 'none_enabled' }] } } : undefined)
    });
    const status = page.locator('[data-settings-section-status="side"]');
    await expect(status).toBeVisible();
    await expect(status).not.toContainText('Alerts');
});
