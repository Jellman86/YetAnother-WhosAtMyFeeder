import { expect, test, type Page } from '@playwright/test';
import { replayFeeder, settled } from './accessibility-mock';

/**
 * Health uses the width it is given. The System card, with its chart and table, keeps the page's
 * full width; from 1280 px what happened takes the main column and the history and the export, which
 * are looked up rather than read through, stand in a side column beside it. At no width does the
 * page scroll sideways.
 */
async function open(page: Page, size: { width: number; height: number }): Promise<void> {
    await page.setViewportSize(size);
    await replayFeeder(page, 'light');
    await page.goto('/system-health');
    await expect(page.locator('[data-health-timeline]')).toBeVisible({ timeout: 15_000 });
    await settled(page);
}

for (const size of [{ width: 390, height: 844 }, { width: 768, height: 1024 }, { width: 1024, height: 768 }, { width: 1440, height: 900 }, { width: 1920, height: 1080 }]) {
    test(`Health does not scroll sideways at ${size.width} px`, async ({ page }) => {
        await open(page, size);
        expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(0);
    });
}

test('at 1440 px the history stands beside what happened, and the System card keeps the full width', async ({ page }) => {
    await open(page, { width: 1440, height: 900 });
    const main = await page.locator('[data-health-main]').boundingBox();
    const side = await page.locator('[data-health-side]').boundingBox();
    expect(main && side && side.x >= main.x + main.width - 1).toBe(true);
    expect(main && side && Math.abs(side.y - main.y)).toBeLessThan(2);
    const incidents = await page.locator('[data-health-earlier-incidents]').boundingBox();
    const exportPanel = await page.locator('[data-diagnostics-export]').boundingBox();
    for (const box of [incidents, exportPanel]) expect(box && side && box.x >= side.x - 1 && box.x + box.width <= side.x + side.width + 1).toBe(true);
    // The System card, chart and table included, spans both columns.
    const system = await page.locator('main section').first().boundingBox();
    expect(system && side && system.x + system.width).toBeGreaterThanOrEqual((side?.x ?? 0) + (side?.width ?? 0) - 1);
});

test('at 1024 px the history follows what happened, its two lists side by side', async ({ page }) => {
    await open(page, { width: 1024, height: 768 });
    const main = await page.locator('[data-health-main]').boundingBox();
    const incidents = await page.locator('[data-health-earlier-incidents]').boundingBox();
    expect(main && incidents && incidents.y >= main.y + main.height - 1).toBe(true);
});
