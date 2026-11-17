import { expect, test, type Page } from '@playwright/test';
import { replayFeeder, settled } from './accessibility-mock';

/**
 * The Leaderboard and Audio history use the space each device gives them: on a phone the controls
 * are compact and the filters wait in a sheet; on a desktop secondary figures stand in a side column
 * and charts take the full width; at no width does the page scroll sideways. Every chart carries its
 * data as a table, and the wall's preview stays inside the page's main landmark.
 */
const READY = { timeout: 15_000 };
const WIDTHS = [
    { width: 390, height: 844 },
    { width: 768, height: 1024 },
    { width: 1024, height: 768 },
    { width: 1440, height: 900 },
    { width: 1920, height: 1080 }
];

async function open(page: Page, path: string, ready: string, size: { width: number; height: number }): Promise<void> {
    await page.setViewportSize(size);
    await replayFeeder(page, 'light');
    await page.goto(path);
    await expect(page.locator(ready).first()).toBeVisible(READY);
    await settled(page);
}

for (const size of WIDTHS) {
    for (const [name, path, ready] of [['the Leaderboard', '/species', '[data-leaderboard-species-portrait]'], ['Audio history', '/audio', '[data-audio-top-species-button]']] as const) {
        test(`${name} does not scroll sideways at ${size.width} px`, async ({ page }) => {
            await open(page, path, ready, size);
            expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(0);
        });
    }
}

test('on a phone the Leaderboard controls are one compact row, with the rarer choice under More', async ({ page }) => {
    await open(page, '/species', '[data-leaderboard-species-portrait]', WIDTHS[0]);
    const controls = page.locator('[data-leaderboard-controls]');
    await expect(page.locator('[data-leaderboard-span-select]')).toBeVisible();
    await expect(page.locator('[data-leaderboard-span-bar]')).toBeHidden();
    await expect(controls.getByRole('checkbox', { name: 'Include Unknown bird' })).toBeHidden();
    expect((await controls.boundingBox())?.height ?? Infinity).toBeLessThan(140);
    await page.locator('[data-leaderboard-more-controls] summary').click();
    await expect(controls.getByRole('checkbox', { name: 'Include Unknown bird' })).toBeVisible();
    await page.locator('[data-leaderboard-span-select]').selectOption('week');
    await expect(page.locator('[data-leaderboard-analytics-window]')).toContainText('Week');
});

test('at 1440 px the standing figures sit beside the wall, and the rankings table and charts take the full width', async ({ page }) => {
    await open(page, '/species', '[data-leaderboard-species-portrait]', WIDTHS[3]);
    const wall = await page.locator('[data-capture-wall]').boundingBox();
    const side = await page.locator('[data-leaderboard-side]').boundingBox();
    expect(wall && side && side.x > wall.x + wall.width - 1).toBe(true);
    // The ranking is a table at this width, and it and the charts reach the side column's far edge.
    await expect(page.locator('[data-leaderboard-table-rankings]')).toBeVisible();
    for (const selector of ['[data-leaderboard-rankings]', '[data-leaderboard-analytics]']) {
        const box = await page.locator(selector).boundingBox();
        expect(box && side && box.x + box.width >= side.x + side.width - 1, selector).toBe(true);
    }
});

test('every Leaderboard chart has its data as a table', async ({ page }) => {
    await open(page, '/species', '[data-leaderboard-species-portrait]', WIDTHS[3]);
    const figures = page.locator('[data-leaderboard-analytics] figure');
    await expect(figures).toHaveCount(3);
    for (const figure of await figures.all()) {
        await figure.scrollIntoViewIfNeeded();
        await figure.locator('summary').filter({ hasText: 'Show the data as a table' }).click();
        await expect(figure.locator('table tbody tr').first()).toBeVisible();
        expect(await figure.locator('table th[scope="row"]').count()).toBeGreaterThan(0);
    }
});

test('the wall\'s preview opens inside the main landmark', async ({ page }) => {
    await open(page, '/species', '[data-capture-wall]', WIDTHS[3]);
    const tile = page.locator('[data-capture-wall] [data-capture-wall-tile]').first();
    await tile.scrollIntoViewIfNeeded();
    await tile.hover();
    const popout = page.locator('[data-capture-wall-popout]');
    await expect(popout).toBeVisible();
    expect(await popout.evaluate((node) => Boolean(node.closest('main')))).toBe(true);
});

test('on a phone Audio history puts the log first and its filters in a sheet', async ({ page }) => {
    await open(page, '/audio', '[data-audio-top-species-button]', WIDTHS[0]);
    await expect(page.locator('[data-audio-history-filters] form')).toBeHidden();
    const opener = page.locator('[data-audio-filters-open]');
    await expect(opener).toBeVisible();
    // The log is read before the summary that stands beside it on a desktop.
    const order = await page.evaluate(() => {
        const log = document.querySelector('[data-audio-history-log]');
        const summary = document.querySelector('[data-audio-history-summary]');
        return Boolean(log && summary && log.compareDocumentPosition(summary) & Node.DOCUMENT_POSITION_FOLLOWING);
    });
    expect(order).toBe(true);
    await opener.click();
    const sheet = page.getByRole('dialog', { name: 'Filters' });
    await expect(sheet).toBeVisible();
    await expect(sheet.getByRole('slider')).toHaveAttribute('aria-valuetext', /%$/);
    // Focus moves into the sheet, as a modal's does, so Escape is the sheet's to take.
    await expect.poll(() => page.evaluate(() => Boolean(document.activeElement?.closest('[role="dialog"]')))).toBe(true);
    await page.keyboard.press('Escape');
    await expect(sheet).toBeHidden();
    await expect(opener).toBeFocused();
});

test('every Audio history chart has its data as a table', async ({ page }) => {
    await open(page, '/audio', '[data-audio-top-species-button]', WIDTHS[3]);
    const figures = page.locator('[data-audio-history-analytics] figure');
    await expect(figures).toHaveCount(3);
    for (const figure of await figures.all()) {
        await figure.scrollIntoViewIfNeeded();
        await figure.locator('summary').filter({ hasText: 'Show the data as a table' }).click();
        await expect(figure.locator('table tbody tr').first()).toBeVisible();
    }
});
