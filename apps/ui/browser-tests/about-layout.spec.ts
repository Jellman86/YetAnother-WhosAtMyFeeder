import { expect, test, type Page } from '@playwright/test';
import { replayFeeder, settled } from './accessibility-mock';

/**
 * About uses the width it is given. From 1280 px what a reader looks up rather than reads through
 * (what it stores and sends, and the credits) stands in a side column beside the portrait, the
 * pipeline and this instance; below that it follows them in reading order. At no width does the
 * page scroll sideways, and its running prose keeps a reading measure.
 */
const READY = { timeout: 15_000 };
const WIDTHS = [
    { width: 390, height: 844 },
    { width: 768, height: 1024 },
    { width: 1024, height: 768 },
    { width: 1440, height: 900 },
    { width: 1920, height: 1080 }
];

async function open(page: Page, size: { width: number; height: number }): Promise<void> {
    await page.setViewportSize(size);
    await replayFeeder(page, 'light');
    await page.goto('/about');
    await expect(page.locator('#about-outbound-title')).toBeVisible(READY);
    await settled(page);
}

for (const size of WIDTHS) {
    test(`About does not scroll sideways at ${size.width} px`, async ({ page }) => {
        await open(page, size);
        expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(0);
    });
}

test('at 1440 px the reference stands in a side column beside the main column', async ({ page }) => {
    await open(page, WIDTHS[3]);
    const main = await page.locator('[data-about-main]').boundingBox();
    const side = await page.locator('[data-about-side]').boundingBox();
    expect(main && side && side.x >= main.x + main.width - 1).toBe(true);
    // The two columns start together, so the reference is read beside the portrait, not under it.
    expect(main && side && Math.abs(side.y - main.y)).toBeLessThan(2);
    // The pipeline has room for four steps a row in the narrower main column.
    const steps = page.locator('[data-about-pipeline] li');
    const tops = await steps.evaluateAll((items) => items.map((item) => Math.round(item.getBoundingClientRect().top)));
    expect(tops.filter((top) => top === tops[0]).length).toBe(4);
});

test('at 1024 px the reference follows the main column, in reading order', async ({ page }) => {
    await open(page, WIDTHS[2]);
    const main = await page.locator('[data-about-main]').boundingBox();
    const side = await page.locator('[data-about-side]').boundingBox();
    expect(main && side && side.y >= main.y + main.height - 1).toBe(true);
});

test('the running prose keeps a reading measure on a wide screen', async ({ page }) => {
    await open(page, WIDTHS[4]);
    const measure = await page.locator('#about-project .max-w-prose').evaluate((node) => {
        const style = getComputedStyle(node);
        const probe = document.createElement('span');
        probe.textContent = '0';
        probe.style.font = style.font;
        node.appendChild(probe);
        const ch = probe.getBoundingClientRect().width;
        probe.remove();
        return node.getBoundingClientRect().width / ch;
    });
    expect(measure).toBeLessThanOrEqual(72);
});
