import { expect, test } from '@playwright/test';
for (const variant of ['title', 'body']) {
    test(`untrusted popup ${variant} stays text under the app inline-script policy`, async ({ page }) => {
        await page.route('https://**/*', route => route.abort());
        await page.goto(`/browser-tests/map-popup.html?variant=${variant}`);
        await page.locator('.leaflet-marker-icon').first().click();
        const popup = page.locator('.leaflet-popup-content');
        await expect(popup).toContainText('<img src="data:,"');
        await expect(popup.locator('img, svg, script, iframe')).toHaveCount(0);
        await expect.poll(() => page.evaluate(() => document.documentElement.dataset.popupExecuted ?? null)).toBeNull();
    });
}
