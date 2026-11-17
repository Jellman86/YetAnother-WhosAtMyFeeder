import { expect, test, type Page } from '@playwright/test';
import { replayFeeder, settled } from './accessibility-mock';

/**
 * The shell on a desktop that is wide but not tall, and on a very wide one. Every place in the
 * navigation stays fully in view: on a short window it is System status that gives way and scrolls
 * inside itself. Past a 1920 px desktop the page is centred with growing gutters rather than
 * stretched across the screen.
 */
const READY = { timeout: 15_000 };

async function open(page: Page, size: { width: number; height: number }, options: { german?: boolean; readingFont?: boolean } = {}): Promise<void> {
    await page.setViewportSize(size);
    if (options.german) await page.addInitScript(() => localStorage.setItem('preferred-language', 'de'));
    await replayFeeder(page, 'light', {}, (json, url) =>
        options.readingFont && url.pathname === '/api/settings' ? { ...(json as Record<string, unknown>), accessibility_dyslexia_font: true } : json
    );
    await page.goto('/about');
    await expect(page.locator('#app-sidebar nav')).toBeVisible(READY);
    await settled(page);
}

async function hiddenPlaces(page: Page): Promise<string[]> {
    return page.locator('#app-sidebar nav').evaluate((nav) => {
        const frame = nav.getBoundingClientRect();
        return [...nav.querySelectorAll('button')]
            .filter((item) => {
                const box = item.getBoundingClientRect();
                return box.top < frame.top - 1 || box.bottom > frame.bottom + 1 || box.bottom > innerHeight + 1;
            })
            .map((item) => item.getAttribute('aria-label') ?? '');
    });
}

for (const size of [{ width: 1920, height: 900 }, { width: 1440, height: 800 }]) {
    for (const options of [{}, { german: true }, { german: true, readingFont: true }]) {
        const name = [options.german ? 'German' : 'English', options.readingFont ? 'the reading font' : ''].filter(Boolean).join(' with ');
        test(`at ${size.width} × ${size.height} in ${name} every place in the navigation is in view`, async ({ page }) => {
            await open(page, size, options);
            expect(await page.locator('#app-sidebar nav button').count()).toBeGreaterThanOrEqual(8);
            expect(await hiddenPlaces(page)).toEqual([]);
            // System status is still there, and its way to Health can be scrolled to inside it.
            const status = page.locator('[data-sidebar-status]');
            await expect(status).toBeVisible();
            const link = status.locator('[data-sidebar-status-link]');
            await link.scrollIntoViewIfNeeded();
            await expect(link).toBeInViewport();
        });
    }
}

test('at 2560 px the page and its footer are centred with gutters, and at 1920 px they use the width', async ({ page }) => {
    await open(page, { width: 2560, height: 1440 });
    const sidebar = await page.locator('#app-sidebar').boundingBox();
    const main = await page.locator('#main-content').boundingBox();
    const footer = await page.locator('footer > div').first().boundingBox();
    expect(sidebar && main).toBeTruthy();
    if (!sidebar || !main || !footer) return;
    const left = main.x - (sidebar.x + sidebar.width);
    const right = 2560 - (main.x + main.width);
    expect(left).toBeGreaterThan(80);
    expect(Math.abs(left - right)).toBeLessThan(2);
    expect(Math.abs(footer.x - main.x)).toBeLessThan(2);

    await page.setViewportSize({ width: 1920, height: 1080 });
    const wide = await page.locator('#main-content').boundingBox();
    const rail = await page.locator('#app-sidebar').boundingBox();
    expect(wide && rail && wide.x + wide.width).toBeGreaterThan(1920 - 2);
    expect(wide && rail && wide.x - (rail.x + rail.width)).toBeLessThan(2);
});
