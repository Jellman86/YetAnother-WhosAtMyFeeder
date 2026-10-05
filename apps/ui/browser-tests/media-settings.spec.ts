import { test, expect } from '@playwright/test';

test('cache limits and scanning use the existing settings controls without overflow', async ({ page }, testInfo) => {
    page.on('pageerror', error => { throw error; });
    await page.goto('/browser-tests/media-settings.html');
    await page.getByRole('spinbutton', { name: /^Most visits per species with photos and video/ }).fill('50');
    await page.getByRole('spinbutton', { name: /^Storage limit \(MiB\)/ }).fill('2048');
    await page.getByRole('button', { name: 'Advanced Snapshot quality', exact: true }).click();
    await page.getByRole('combobox', { name: 'Bird scanning effort', exact: true }).selectOption('standard');
    await expect(page.getByRole('status', { name: 'Selected cache settings' })).toHaveText('50 / 2048 / standard');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    const card = page.locator('section').filter({ has: page.getByRole('heading', { name: 'Photos and video', exact: true }) });
    // Photographs and visit media are always kept (#622): no switch turns them off.
    await expect(card.locator('[data-media-always-kept]')).toBeVisible();
    await expect(card.getByRole('switch', { name: /^Snapshots/ })).toHaveCount(0);
    await expect(card.getByRole('switch', { name: /^Media Cache/ })).toHaveCount(0);
    await expect(card.getByRole('switch', { name: /^Keep copies of Frigate's event clips/ })).toHaveCount(1);
    await expect(card.locator('[data-media-storage-unavailable]')).toHaveCount(0);
    const bounds = await card.boundingBox();
    expect(bounds?.width ?? 0).toBeGreaterThan(300);
    await card.screenshot({ path: testInfo.outputPath('media-settings.png') });
    await page.evaluate(() => document.documentElement.classList.add('theme-bluetit', 'dark'));
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await expect(card).toHaveCSS('background-color', 'rgba(15, 23, 42, 0.88)');
    await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(7, 13, 27)');
    await card.screenshot({ path: testInfo.outputPath('media-settings-dark.png'), animations: 'disabled' });
});

test('a media folder that cannot be written is said plainly on the card', async ({ page }) => {
    await page.goto('/browser-tests/media-settings.html?storage=unavailable');
    const notice = page.locator('[data-media-storage-unavailable]');
    await expect(notice).toBeVisible();
    await expect(notice).toHaveText(/can't be written, so photos and video are not being kept/);
});
