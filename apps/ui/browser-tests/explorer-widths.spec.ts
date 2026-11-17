import { expect, test, type Page } from '@playwright/test';
import { replayFeeder, settled } from './accessibility-mock';

/**
 * The Explorer uses the width it is given: its filter rail is docked beside the results from 1024 px
 * and waits behind Filters in a sheet below that, and its grid adds columns as the window widens
 * rather than widening its cards.
 */
const READY = { timeout: 15_000 };

async function open(page: Page, size: { width: number; height: number }): Promise<void> {
    await page.setViewportSize(size);
    await replayFeeder(page, 'light');
    await page.goto('/events');
    await expect(page.locator('[data-detection-card]').first()).toBeVisible(READY);
    await settled(page);
}

/** How many columns the results grid lays its cards in. */
async function gridColumns(page: Page): Promise<number> {
    return page.locator('[data-explorer-grid]').evaluate((grid) => getComputedStyle(grid).gridTemplateColumns.split(' ').filter(Boolean).length);
}

for (const size of [{ width: 1024, height: 768 }, { width: 1440, height: 900 }, { width: 1920, height: 1080 }]) {
    test(`at ${size.width} px the filter rail is docked beside the results`, async ({ page }) => {
        await open(page, size);
        const rail = await page.locator('#explorer-filter-rail').boundingBox();
        const grid = await page.locator('[data-explorer-grid]').boundingBox();
        expect(rail && grid && rail.width > 100 && rail.x + rail.width <= grid.x + 1).toBe(true);
        await expect(page.getByRole('button', { name: 'Filters', exact: true })).toHaveCount(0);
    });
}

for (const size of [{ width: 390, height: 844 }, { width: 768, height: 1024 }]) {
    test(`at ${size.width} px the filters wait behind Filters, in a sheet`, async ({ page }) => {
        await open(page, size);
        const opener = page.getByRole('button', { name: 'Filters', exact: true });
        await expect(opener).toBeVisible();
        // Above the results the rail holds only the search and the way to the filters, not the filters.
        const rail = await page.locator('#explorer-filter-rail').boundingBox();
        expect(rail?.height ?? 0).toBeLessThan(200);
        await opener.click();
        const sheet = page.getByRole('dialog', { name: 'Filters' });
        await expect(sheet).toBeVisible();
        await expect(sheet.getByText('Visitors', { exact: true }).first()).toBeVisible();
    });
}

test('the results grid adds columns as the window widens, and never widens one card across the page', async ({ page }) => {
    const columns: number[] = [];
    for (const size of [{ width: 390, height: 844 }, { width: 768, height: 1024 }, { width: 1440, height: 900 }, { width: 1920, height: 1080 }]) {
        await open(page, size);
        columns.push(await gridColumns(page));
        const card = await page.locator('[data-detection-card]').first().boundingBox();
        if (size.width >= 768) expect(card?.width ?? Infinity, `${size.width} px`).toBeLessThan(560);
    }
    expect(columns[0]).toBe(1);
    for (let index = 1; index < columns.length; index += 1) expect(columns[index]).toBeGreaterThanOrEqual(columns[index - 1]);
    expect(columns[3]).toBeGreaterThan(columns[1]);
});
