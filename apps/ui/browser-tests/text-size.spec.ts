import { test, expect, type Page } from '@playwright/test';

// Set UI_SHOTS to a directory to keep review screenshots of the control.
const environment = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env ?? {};

const rootSize = (page: Page): Promise<number> => page.evaluate(() => parseFloat(getComputedStyle(document.documentElement).fontSize));

test('a chosen text size resizes the whole page and is kept on this device', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto('/browser-tests/text-size.html');
    const options = page.locator('[data-text-size-options]');
    await expect(options.getByRole('button')).toHaveCount(7);
    // Standard is the default, a step under the browser's own 16px.
    await expect(options.getByRole('button', { name: 'Standard', exact: true })).toHaveAttribute('aria-pressed', 'true');
    expect(await rootSize(page)).toBe(14);

    await options.getByRole('button', { name: 'Extra large', exact: true }).click();
    await expect(options.getByRole('button', { name: 'Extra large', exact: true })).toHaveAttribute('aria-pressed', 'true');
    expect(await rootSize(page)).toBe(20);
    await page.waitForTimeout(300);
    if (environment.UI_SHOTS) await page.screenshot({ path: `${environment.UI_SHOTS}/text-size-extra-large-1280.png` });

    await page.reload();
    await expect(page.locator('[data-text-size="extra_large"]')).toHaveAttribute('aria-pressed', 'true');
    expect(await rootSize(page)).toBe(20);

    await page.locator('[data-text-size="smallest"]').click();
    expect(await rootSize(page)).toBe(12);
    await page.locator('[data-text-size="large"]').click();
    expect(await rootSize(page)).toBe(16);
});

test('the size multiplies the growth on a large display rather than replacing it', async ({ page }) => {
    await page.setViewportSize({ width: 2304, height: 1200 });
    await page.goto('/browser-tests/text-size.html');
    expect(await rootSize(page)).toBe(17.5);
    await page.locator('[data-text-size="large"]').click();
    expect(await rootSize(page)).toBe(20);
});

test('a stored value the app does not know reads as standard', async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem('text_size', 'enormous'));
    await page.goto('/browser-tests/text-size.html');
    await expect(page.locator('[data-text-size="standard"]')).toHaveAttribute('aria-pressed', 'true');
    expect(await rootSize(page)).toBe(14);
});

for (const width of [320, 390]) {
    test(`the five sizes fit a ${width}px phone at the largest size with usable targets`, async ({ page }) => {
        await page.setViewportSize({ width, height: 900 });
        await page.goto('/browser-tests/text-size.html');
        await page.locator('[data-text-size="largest"]').click();
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        for (const option of await page.locator('[data-text-size]').all()) {
            const box = await option.boundingBox();
            expect(box?.width ?? 0).toBeGreaterThanOrEqual(44);
            expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
            expect(await option.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
        }
        if (environment.UI_SHOTS) await page.screenshot({ path: `${environment.UI_SHOTS}/text-size-largest-${width}.png` });
    });
}
