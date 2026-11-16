import { expect, test } from '@playwright/test';
import { replayFeeder, settled } from './accessibility-mock';

// About lists what leaves the network from the features that send it: who makes each request,
// what it sends, and whether it happens here. It makes no promise that the list is everything.
test.use({ viewport: { width: 1440, height: 900 } });

test('the list names the browser and server requests, and the map tiles do not follow eBird', async ({ page }, testInfo) => {
    await replayFeeder(page, 'light', {}, (json, url) => (url.pathname === '/api/settings'
        ? {
            ...(json as Record<string, unknown>),
            ebird_enabled: false, llm_enabled: false, telemetry_enabled: false, birdweather_enabled: false,
            inaturalist_enabled: false, notifications_discord_enabled: true, notifications_telegram_enabled: false,
            notifications_pushover_enabled: false, notifications_email_enabled: false,
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
    // eBird is off, and the map tiles are still listed as used: the location map draws them.
    await expect(state('ebird')).toContainText('Disabled');
    await expect(state('osm')).toContainText('When used');
    await expect(state('osm')).not.toContainText('Disabled');
    // Each optional request follows its own setting.
    await expect(state('notify')).toContainText('Enabled');
    await expect(state('llm')).toContainText('Disabled');
    await expect(state('geolocate')).toContainText('Enabled');
    await expect(state('weather')).toContainText('Enabled');
    // Every row says what it sends or who sees what.
    await expect(state('weather')).toContainText('Sends the feeder’s coordinates.');

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
    for (const key of ['telemetry', 'birdweather', 'notify', 'weather']) {
        await expect(section.locator(`[data-outbound="${key}"]`)).toHaveAttribute('data-outbound-state', 'unknown');
        await expect(section.locator(`[data-outbound="${key}"]`)).toContainText('Owner only');
    }
    await expect(section.locator('[data-outbound="fonts"]')).toHaveAttribute('data-outbound-state', 'always');
});
