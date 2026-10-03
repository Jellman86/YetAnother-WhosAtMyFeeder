import { test, expect, type Page } from '@playwright/test';

async function open(page: Page): Promise<{ downloads: number }> {
    const requests = { downloads: 0 };
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route('**/poster.svg', route => route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"/>' }));
    // This checks acquisition/lifecycle, not video decoding.
    await page.route('**/api/about/showcase/*.webm', route => {
        requests.downloads += 1;
        return route.fulfill({ contentType: 'video/webm', body: 'fixture' });
    });
    await page.goto('/browser-tests/visit-film.html');
    await expect(page.locator('[data-visit-film]')).toHaveCount(2);
    return requests;
}

test('live in-app motion changes release both copies and restore one shared download', async ({ page }) => {
    const requests = await open(page);
    await expect(page.locator('video')).toHaveCount(2);
    expect(requests.downloads).toBe(1);
    await page.getByRole('button', { name: 'Toggle reduced motion' }).click();
    await expect(page.locator('video')).toHaveCount(0);
    await expect(page.locator('[data-visit-film] img')).toHaveCount(2);
    await page.getByRole('button', { name: 'Toggle reduced motion' }).click();
    await expect(page.locator('video')).toHaveCount(2);
    expect(requests.downloads).toBe(2);
    await page.getByRole('button', { name: 'Toggle cards' }).click();
    await expect(page.locator('video')).toHaveCount(0);
});

test('OS reduced motion prevents downloading and reacts live', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    const requests = await open(page);
    await page.waitForTimeout(200);
    expect(requests.downloads).toBe(0);
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    await expect(page.locator('video')).toHaveCount(2);
    expect(requests.downloads).toBe(1);
});

test('data saver prevents downloading and reacts when the connection changes', async ({ page }) => {
    await page.addInitScript(() => {
        const connection = Object.assign(new EventTarget(), { saveData: true });
        Object.defineProperty(navigator, 'connection', { configurable: true, value: connection });
    });
    const requests = await open(page);
    await page.waitForTimeout(200);
    expect(requests.downloads).toBe(0);
    await page.evaluate(() => {
        const connection = (navigator as Navigator & { connection: EventTarget & { saveData: boolean } }).connection;
        connection.saveData = false;
        connection.dispatchEvent(new Event('change'));
    });
    await expect(page.locator('video')).toHaveCount(2);
    expect(requests.downloads).toBe(1);
});
