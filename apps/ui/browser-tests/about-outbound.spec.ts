import { expect, test } from '@playwright/test';
import { replayFeeder, settled } from './accessibility-mock';

// About lists what leaves the network from the features that send it: who makes each request,
// what it sends, and whether it happens here. It makes no promise that the list is everything.
test.use({ viewport: { width: 1440, height: 900 } });

test('the list names the browser and server requests, and the map tiles do not follow eBird', async ({ page }, testInfo) => {
    await replayFeeder(page, 'light', {}, (json, url) => (url.pathname === '/api/settings'
        ? {
            ...(json as Record<string, unknown>),
            ebird_enabled: false, birdweather_enabled: true, birdweather_station_token: '',
            // AI is switched on with no key saved, so no request can be made.
            llm_enabled: true, llm_api_key: '',
            // Usage statistics off, health reports on: two opt-ins.
            telemetry_enabled: false, telemetry_health_enabled: true,
            inaturalist_enabled: false,
            // Every bird channel off, and Garden alerts on a channel of their own.
            notifications_discord_enabled: false, notifications_telegram_enabled: false,
            notifications_pushover_enabled: false, notifications_email_enabled: false,
            beta_garden_animals: true, garden_notifications_enabled: true,
            garden_notifications_use_bird_channels: false, garden_notification_channels: ['telegram'],
            location_latitude: null, location_longitude: null, location_automatic: true
        }
        : json));
    await page.goto('/about');
    const section = page.locator('section[aria-labelledby="about-outbound-title"]');
    await expect(section).toBeVisible({ timeout: 15_000 });
    await settled(page);

    await expect(page.getByText('Nothing leaves your network except the calls listed below.')).toHaveCount(0);
    await expect(section.locator('[data-outbound-origin="server"]')).toHaveText('Sent by this server');
    await expect(section.locator('[data-outbound-origin="browser"]')).toHaveText('Sent by each viewer’s browser');

    const state = (key: string) => section.locator(`[data-outbound="${key}"]`);
    // Requests the old list left out, on every install.
    await expect(state('fonts')).toContainText('Google Fonts');
    await expect(state('fonts')).toHaveAttribute('data-outbound-state', 'always');
    await expect(state('wikipedia')).toHaveAttribute('data-outbound-state', 'always');
    await expect(state('photos')).toContainText('Wikimedia and iNaturalist');
    // One vocabulary: On, Off, Always, When used.
    await expect(section).not.toContainText('Enabled');
    await expect(section).not.toContainText('Disabled');
    // eBird is off, and the map tiles are still listed as used: the location map draws them.
    await expect(state('ebird')).toHaveAttribute('data-outbound-state', 'off');
    await expect(state('ebird')).toContainText('Off');
    await expect(state('osm')).toContainText('When used');
    // Health reports send with usage statistics off, so each has its own row and state.
    await expect(state('telemetry')).toHaveAttribute('data-outbound-state', 'off');
    await expect(state('telemetry_health')).toHaveAttribute('data-outbound-state', 'on');
    await expect(state('telemetry_health')).toContainText('installation ID');
    // Garden alerts go out on their own channel while every bird channel is off.
    await expect(state('notify')).toHaveAttribute('data-outbound-state', 'off');
    await expect(state('garden_notify')).toHaveAttribute('data-outbound-state', 'on');
    // A switch that cannot send is not shown as on: no AI key, no BirdWeather token.
    await expect(state('llm')).toHaveAttribute('data-outbound-state', 'off');
    await expect(state('birdweather')).toHaveAttribute('data-outbound-state', 'off');
    await expect(state('geolocate')).toHaveAttribute('data-outbound-state', 'on');
    await expect(state('weather')).toHaveAttribute('data-outbound-state', 'on');
    // Every row says what it sends or who sees what, coordinates included.
    await expect(state('weather')).toContainText('Sends the feeder’s coordinates.');
    await expect(state('birdweather')).toContainText('coordinates');
    // Connecting, testing and diagnostics are apart from normal operation.
    await expect(section.locator('[data-outbound-origin="on_demand"]')).toHaveText('When you connect, test or run diagnostics');
    for (const key of ['oauth_browser', 'oauth_server', 'tests', 'diagnostics']) {
        await expect(state(key)).toHaveAttribute('data-outbound-state', 'on_use');
    }
    await expect(state('tests')).toContainText('placehold.co');

    await section.scrollIntoViewIfNeeded();
    await section.screenshot({ path: testInfo.outputPath('about-outbound.png') });
});

test('a guest is not told that settings they cannot read are off', async ({ page }) => {
    await replayFeeder(page, 'light', {}, (json, url) => {
        if (url.pathname === '/api/auth/status') {
            return { ...(json as Record<string, unknown>), is_authenticated: false, auth_required: true, public_access_enabled: true };
        }
        return json;
    });
    await page.route((url) => url.pathname === '/api/settings', (route) => route.fulfill({ status: 401, json: { detail: 'Not authenticated' } }));
    await page.goto('/about');
    const section = page.locator('section[aria-labelledby="about-outbound-title"]');
    await expect(section).toBeVisible({ timeout: 15_000 });
    for (const key of ['telemetry', 'telemetry_health', 'birdweather', 'notify', 'garden_notify', 'weather']) {
        await expect(section.locator(`[data-outbound="${key}"]`)).toHaveAttribute('data-outbound-state', 'unknown');
        await expect(section.locator(`[data-outbound="${key}"]`)).toContainText('Owner only');
    }
    await expect(section.locator('[data-outbound="fonts"]')).toHaveAttribute('data-outbound-state', 'always');
});
