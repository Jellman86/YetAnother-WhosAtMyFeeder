import { expect, test } from '@playwright/test';

// The sidebar's live tile and the Dashboard's feed line claim only what was measured: the page's
// stream to YA-WAMF says the page is connected, and only a broker session that is up is "live".

async function open(page: import('@playwright/test').Page, query: string) {
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(`/browser-tests/status-feed.html?${query}`);
    await expect(page.locator('[data-status-tile="live"]')).toBeVisible();
    return errors;
}

const tile = (page: import('@playwright/test').Page) => page.locator('[data-status-tile="live"]');
const line = (page: import('@playwright/test').Page) => page.locator('[data-day-bar-feed]');

test('a connected page with the broker down is never shown as live', async ({ page }) => {
    const errors = await open(page, 'stream=1&mqtt=disconnected&frigate=unreachable');
    await expect(tile(page)).toHaveAttribute('data-status-on', 'false');
    await expect(tile(page)).toHaveAttribute('data-status-feed', 'broker_down');
    await expect(tile(page)).toContainText('No events');
    await expect(tile(page)).toHaveAttribute('title', 'Live updates: Not receiving camera events, the MQTT broker is not connected');
    // The state is a word and a slashed icon, not only a colour.
    await expect(tile(page).locator('path[d="M4 4l16 16"]')).toHaveCount(1);
    await expect(line(page)).toHaveText('Not receiving camera events, the MQTT broker is not connected');
    await expect(page.getByText('Live Feed')).toHaveCount(0);
    expect(errors).toEqual([]);
});

test('a Frigate that does not answer is named even with the broker up', async ({ page }) => {
    await open(page, 'stream=1&mqtt=connected&frigate=unreachable');
    await expect(tile(page)).toContainText('No Frigate');
    await expect(line(page)).toHaveText('Frigate is not answering, so new detections cannot be saved');
});

test('live means the page stream and the broker session are both up', async ({ page }) => {
    await open(page, 'stream=1&mqtt=connected&frigate=reachable');
    await expect(tile(page)).toHaveAttribute('data-status-on', 'true');
    await expect(tile(page)).toContainText('Live');
    await expect(line(page)).toHaveText('Live Feed');
});

test('without a measurement only the page connection is claimed, as a guest sees it', async ({ page }) => {
    await open(page, 'stream=1&mqtt=none');
    await expect(tile(page)).toHaveAttribute('data-status-on', 'false');
    await expect(tile(page)).toContainText('Connected');
    await expect(line(page)).toHaveText('Connected to YA-WAMF');
});

test('a dropped page stream reads as reconnecting whatever the broker did', async ({ page }) => {
    await open(page, 'stream=0&mqtt=connected');
    await expect(tile(page)).toContainText('Offline');
    await expect(line(page)).toHaveText('Reconnecting…');
});
