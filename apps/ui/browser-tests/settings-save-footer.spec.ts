import { test, expect, type Locator, type Page } from '@playwright/test';

// The save footer and the saved-status message are shared by every Settings
// section. With text enlarged to 200% on a narrow phone they must wrap rather
// than push Apply Settings or the message past the edge of the screen.
async function openConnectionSettings(page: Page) {
    const saves: Record<string, unknown>[] = [];
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route(url => url.pathname === '/health' || url.pathname.startsWith('/api/'), route => {
        const request = route.request();
        const path = new URL(request.url()).pathname;
        if (path === '/api/settings' && request.method() === 'POST') {
            saves.push(request.postDataJSON() as Record<string, unknown>);
            return route.fulfill({ json: { status: 'updated' } });
        }
        if (path === '/api/settings') {
            return route.fulfill({ json: {
                frigate_url: 'http://frigate:5000', mqtt_server: 'mqtt', mqtt_port: 1883, mqtt_auth: false
            } });
        }
        if (path === '/api/models/installed' || path === '/api/models/available') return route.fulfill({ json: [] });
        if (path.endsWith('/audio/sources')) return route.fulfill({ json: [] });
        if (path.endsWith('/frigate/config')) return route.fulfill({ json: { cameras: {} } });
        if (path.endsWith('/backfill/status')) return route.fulfill({ json: null });
        return route.fulfill({ json: {} });
    });
    await page.goto('/browser-tests/settings-backfill.html');
    await expect(page.locator('#mqtt-server')).toHaveValue('mqtt');
    await page.addStyleTag({ content: 'html{font-size:200%!important}' });
    return saves;
}

async function expectInsideViewport(page: Page, locator: Locator) {
    const box = await locator.boundingBox();
    const width = await page.evaluate(() => window.innerWidth);
    expect(box).not.toBeNull();
    expect(box?.x ?? -1).toBeGreaterThanOrEqual(0);
    expect((box?.x ?? 0) + (box?.width ?? 0)).toBeLessThanOrEqual(width + 1);
}

async function expectNoHorizontalOverflow(page: Page) {
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(1);
}

for (const width of [320, 393]) {
    test.describe(`at ${width}px with 200% text`, () => {
        test.use({ viewport: { width, height: 740 } });

        test('the save footer keeps Apply Settings fully on screen and reachable by keyboard', async ({ page }) => {
            const saves = await openConnectionSettings(page);
            await page.locator('#mqtt-server').fill('mqtt-broker');
            const apply = page.getByRole('button', { name: 'Apply Settings', exact: true });
            await expect(apply).toBeInViewport({ ratio: 1 });
            await expectInsideViewport(page, apply);
            await expect(page.getByText('Unsaved Changes', { exact: true })).toBeInViewport({ ratio: 1 });
            await expectNoHorizontalOverflow(page);

            await apply.focus();
            await expect(apply).toBeFocused();
            await page.keyboard.press('Enter');
            await expect.poll(() => saves.length).toBe(1);
            expect(saves[0].mqtt_server).toBe('mqtt-broker');
        });

        test('the saved message and its notification wrap inside the screen', async ({ page }) => {
            await openConnectionSettings(page);
            await page.locator('#mqtt-server').fill('mqtt-broker');
            await page.getByRole('button', { name: 'Apply Settings', exact: true }).click();
            const saved = page.getByRole('status').filter({ hasText: 'Settings saved' });
            await expect(saved).toBeVisible();
            await expectInsideViewport(page, saved);

            const toast = page.locator('[data-toast-container] [data-toast]').filter({ hasText: 'Settings saved' });
            await expect(toast).toBeInViewport({ ratio: 1 });
            await expectInsideViewport(page, toast);
            await expectInsideViewport(page, toast.getByRole('button', { name: 'Close notification' }));
            await expectNoHorizontalOverflow(page);
        });
    });
}
