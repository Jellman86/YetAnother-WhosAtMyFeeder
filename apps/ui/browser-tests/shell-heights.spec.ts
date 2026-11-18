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

for (const size of [{ width: 1920, height: 900 }, { width: 1440, height: 800 }, { width: 1280, height: 720 }, { width: 1024, height: 768 }]) {
    for (const options of [{}, { german: true }, { german: true, readingFont: true }]) {
        const name = [options.german ? 'German' : 'English', options.readingFont ? 'the reading font' : ''].filter(Boolean).join(' with ');
        test(`at ${size.width} × ${size.height} in ${name} every place in the navigation is in view`, async ({ page }) => {
            await open(page, size, options);
            expect(await page.locator('#app-sidebar nav button').count()).toBeGreaterThanOrEqual(8);
            expect(await hiddenPlaces(page)).toEqual([]);
            const status = page.locator('[data-sidebar-status]');
            await expect(status).toBeVisible();
            const link = status.locator('[data-sidebar-status-link]');
            const readings = page.locator('[data-sidebar-status-readings]');
            if (!options.readingFont) {
                // The issues link is whole and in view without scrolling anything, under the status heading
                // and its first reading: only the rest of the readings give way.
                await expect(link).toBeInViewport({ ratio: 1 });
                const card = await page.locator('[data-sidebar-status-card]').boundingBox();
                const linkBox = await link.boundingBox();
                expect(card && linkBox && linkBox.y + linkBox.height <= card.y + card.height + 1, 'the issues link is inside its card').toBe(true);
                expect((await readings.boundingBox())?.height ?? 0).toBeGreaterThan(30);
                expect(await page.locator('[data-sidebar-scroll]').evaluate((node) => node.scrollHeight - node.clientHeight)).toBeLessThanOrEqual(1);
            } else {
                // With the much wider reading font the places and the status scroll together, and the link
                // is reached by scrolling that column, never hidden inside the card.
                // Scrolled to the middle of the column, as a reader would bring it into view, not flush with
                // its edge where a fraction of a pixel can stay under the clip.
                await link.evaluate((node) => node.scrollIntoView({ block: 'center' }));
                await expect(link).toBeInViewport({ ratio: 1 });
            }
        });
    }
}

test('at 2560 px the page and its footer are centred with gutters, and at 1920 px they use the width', async ({ page }) => {
    await open(page, { width: 2560, height: 1440 });
    const sidebar = await page.locator('#app-sidebar').boundingBox();
    const main = await page.locator('#main-content').boundingBox();
    const footer = await page.locator('footer > div').first().boundingBox();
    expect(sidebar).not.toBeNull();
    expect(main).not.toBeNull();
    expect(footer).not.toBeNull();
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

test('with the sidebar collapsed the page is still centred past 1920 px, and fills the window at 1920 px', async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem('sidebarCollapsed', 'true'));
    await open(page, { width: 2560, height: 1440 });
    const rail = await page.locator('#app-sidebar').boundingBox();
    const main = await page.locator('#main-content').boundingBox();
    expect(rail).not.toBeNull();
    expect(main).not.toBeNull();
    if (!rail || !main) return;
    expect(rail.width).toBeLessThan(120);
    const left = main.x - (rail.x + rail.width);
    const right = 2560 - (main.x + main.width);
    expect(left).toBeGreaterThan(80);
    expect(Math.abs(left - right)).toBeLessThan(2);

    await page.setViewportSize({ width: 1920, height: 1080 });
    // The collapsed rail leaves 1840 px, more than the container holds, so it is centred with modest gutters.
    const wide = await page.locator('#main-content').boundingBox();
    const narrowRail = await page.locator('#app-sidebar').boundingBox();
    expect(wide && narrowRail).toBeTruthy();
    if (!wide || !narrowRail) return;
    const gutter = wide.x - (narrowRail.x + narrowRail.width);
    expect(Math.abs(gutter - (1920 - (wide.x + wide.width)))).toBeLessThan(2);
    expect(wide.width / 1920).toBeGreaterThan(0.8);
});

