import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';

// The sidebar's System status rows and the Dashboard's feed line claim only what was measured:
// the page's stream to YA-WAMF says the page is connected, and only a broker session that is up
// is "live". Every state is a word; the dot beside it is never the only cue.

async function open(page: Page, query: string): Promise<string[]> {
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(`/browser-tests/status-feed.html?${query}`);
    await expect(row(page, 'feed')).toBeVisible();
    return errors;
}

const list = (page: Page) => page.locator('[data-fixture-sidebar]');
const rail = (page: Page) => page.locator('[data-fixture-rail]');
const row = (page: Page, id: string) => list(page).locator(`[data-status-row="${id}"]`);
const state = (page: Page, id: string) => row(page, id).locator('[data-status-state]');
const railRow = (page: Page, id: string) => rail(page).locator(`[data-status-row="${id}"]`);
const line = (page: Page) => page.locator('[data-day-bar-feed]');

test('a connected page with the broker down is never shown as live', async ({ page }) => {
    const errors = await open(page, 'stream=1&mqtt=disconnected&frigate=unreachable');
    await expect(row(page, 'feed')).toHaveAttribute('data-status-feed', 'broker_down');
    await expect(row(page, 'feed')).toHaveAttribute('data-status-tone', 'attention');
    await expect(row(page, 'feed').locator('[data-status-label]')).toHaveText('Frigate events');
    await expect(state(page, 'feed')).toHaveText('Not connected');
    await expect(row(page, 'feed')).toHaveAttribute('title', 'Not receiving camera events. The MQTT broker is not connected.');
    // Audio cannot be listening without the broker, and the one cause is flagged once, not twice.
    await expect(state(page, 'audio')).toHaveText('Not listening');
    await expect(row(page, 'audio')).toHaveAttribute('data-status-tone', 'neutral');
    await expect(line(page)).toHaveText('Not receiving camera events. The MQTT broker is not connected.');
    await expect(page.getByText('Live feed')).toHaveCount(0);
    expect(errors).toEqual([]);
});

test('a Frigate that does not answer is named even with the broker up', async ({ page }) => {
    await open(page, 'stream=1&mqtt=connected&frigate=unreachable');
    await expect(state(page, 'feed')).toHaveText('Frigate not answering');
    await expect(row(page, 'feed')).toHaveAttribute('data-status-tone', 'attention');
    // Audio detections arrive through the broker, which is up.
    await expect(state(page, 'audio')).toHaveText('Listening');
    await expect(line(page)).toHaveText('Frigate is not answering, so new detections cannot be saved');
});

test('live means the page stream and the broker session are both up', async ({ page }) => {
    await open(page, 'stream=1&mqtt=connected&frigate=reachable&alerts=1');
    await expect(row(page, 'feed')).toHaveAttribute('data-status-tone', 'ok');
    await expect(state(page, 'feed')).toHaveText('Live');
    await expect(state(page, 'audio')).toHaveText('Listening');
    await expect(state(page, 'alerts')).toHaveText('On');
    await expect(row(page, 'alerts')).toHaveAttribute('data-status-tone', 'ok');
    await expect(line(page)).toHaveText('Live feed');
});

test('a broker that is still connecting is waiting for events, not live and not a fault', async ({ page }) => {
    await open(page, 'stream=1&mqtt=connecting');
    await expect(state(page, 'feed')).toHaveText('Waiting for events');
    await expect(row(page, 'feed')).toHaveAttribute('data-status-tone', 'neutral');
});

test('audio and alerts switched off are Off by choice, never amber', async ({ page }) => {
    await open(page, 'stream=1&mqtt=connected&frigate=reachable&audio=0&alerts=0');
    for (const id of ['audio', 'alerts']) {
        await expect(state(page, id)).toHaveText('Off');
        await expect(row(page, id)).toHaveAttribute('data-status-tone', 'neutral');
    }
    await expect(list(page).locator('[data-status-tone="attention"]')).toHaveCount(0);
});

test('without a measurement only the page connection is claimed, as a guest sees it', async ({ page }) => {
    await open(page, 'stream=1&mqtt=none&alerts=none');
    await expect(state(page, 'feed')).toHaveText('Connected');
    await expect(state(page, 'audio')).toHaveText('On');
    // A guest cannot read the owner's notification settings: the row is left out, not guessed.
    await expect(row(page, 'alerts')).toHaveCount(0);
    await expect(line(page)).toHaveText('Connected to YA-WAMF');
});

test('a dropped page stream reads as reconnecting whatever the broker did', async ({ page }) => {
    await open(page, 'stream=0&mqtt=connected');
    await expect(state(page, 'feed')).toHaveText('Reconnecting');
    await expect(line(page)).toHaveText('Reconnecting…');
});

test('the rows are a list in one live region, and each tone has its own dot shape', async ({ page }) => {
    await open(page, 'stream=1&mqtt=disconnected&alerts=1');
    const region = list(page).getByRole('status');
    await expect(region).toHaveCount(1);
    await expect(region.getByRole('list')).toHaveCount(1);
    await expect(region.getByRole('listitem')).toHaveCount(3);
    // A changed row is read whole: "Frigate events Not connected", not a bare "Not connected".
    await expect(row(page, 'feed')).toHaveAttribute('aria-atomic', 'true');
    const shapes = await list(page).locator('[data-status-row]').evaluateAll(rows => rows.map(node => {
        const dot = node.querySelector('[data-status-dot]') as HTMLElement;
        const style = getComputedStyle(dot);
        return {
            tone: node.getAttribute('data-status-tone'),
            round: style.borderTopLeftRadius !== '0px',
            filled: style.backgroundColor !== 'rgba(0, 0, 0, 0)',
            turned: style.rotate !== 'none' || style.transform !== 'none'
        };
    }));
    expect(shapes).toEqual([
        { tone: 'attention', round: false, filled: true, turned: true },
        { tone: 'neutral', round: true, filled: false, turned: false },
        { tone: 'ok', round: true, filled: true, turned: false }
    ]);
});

test('the icon rail carries the same words as names and tooltips', async ({ page }) => {
    await open(page, 'stream=1&mqtt=connected&frigate=reachable&audio=0&alerts=1');
    await expect(rail(page).getByRole('listitem')).toHaveCount(3);
    await expect(railRow(page, 'feed')).toHaveAttribute('title', 'Frigate events: Live');
    await expect(railRow(page, 'feed')).toHaveText('Frigate events: Live');
    await expect(railRow(page, 'audio')).toHaveAttribute('title', 'Audio: Off');
    await expect(railRow(page, 'alerts')).toHaveAttribute('title', 'Alerts: On');
    // Each icon is a pointer target of its own for its tooltip, and none spills out of the rail.
    const railBox = await rail(page).boundingBox();
    for (const id of ['feed', 'audio', 'alerts']) {
        const box = await railRow(page, id).boundingBox();
        expect(box?.width).toBeGreaterThanOrEqual(24);
        expect(box?.height).toBeGreaterThanOrEqual(24);
        expect((box?.x ?? 0) + (box?.width ?? 0)).toBeLessThanOrEqual((railBox?.x ?? 0) + (railBox?.width ?? 0));
    }
});

test('the longest state fits the sidebar width, and at 200% text nothing is cut off', async ({ page }) => {
    await open(page, 'stream=1&mqtt=connected&frigate=unreachable&alerts=1');
    // Inline text has no box of its own to overflow; every element that has one is measured.
    const overflowing = () => list(page).evaluate(node => {
        const right = node.getBoundingClientRect().right;
        return [...node.querySelectorAll<HTMLElement>('*')]
            .filter(el => el instanceof HTMLElement && !el.hasAttribute('data-status-dot'))
            .filter(el => el.getBoundingClientRect().right > right + 1
                || (getComputedStyle(el).display !== 'inline' && el.scrollWidth > el.clientWidth + 1))
            .map(el => el.outerHTML.slice(0, 90));
    });
    expect(await overflowing()).toEqual([]);
    await page.evaluate(() => { document.documentElement.style.fontSize = '200%'; });
    expect(await overflowing()).toEqual([]);
    await expect(state(page, 'feed')).toBeVisible();
});

for (const theme of ['light', 'dark'] as const) {
    test(`the status rows pass axe in the ${theme} theme, every state at once`, async ({ page }) => {
        for (const query of [
            'stream=1&mqtt=connected&frigate=reachable&alerts=1',
            'stream=1&mqtt=disconnected&audio=0&alerts=0',
            'stream=1&mqtt=connected&frigate=unreachable'
        ]) {
            await open(page, `${query}&theme=${theme}`);
            const results = await new AxeBuilder({ page }).include('[data-fixture-sidebar]').include('[data-fixture-rail]').analyze();
            expect(results.violations.map(violation => `${violation.id}: ${violation.nodes.map(node => node.target.join(' ')).join(', ')}`)).toEqual([]);
        }
    });
}
