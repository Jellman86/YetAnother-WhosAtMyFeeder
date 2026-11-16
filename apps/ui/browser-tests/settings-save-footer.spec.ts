import { test, expect, type Locator, type Page } from '@playwright/test';

// The save footer and the saved-status message are shared by every Settings
// section. With text enlarged to 200% on a narrow phone they must wrap rather
// than push Save changes, Discard changes or the notification past the edge of the screen.
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

        test('the save bar keeps both its buttons fully on screen and reachable by keyboard', async ({ page }) => {
            const saves = await openConnectionSettings(page);
            await page.locator('#mqtt-server').fill('mqtt-broker');
            const apply = page.getByRole('button', { name: 'Save changes', exact: true });
            await expect(apply).toBeInViewport({ ratio: 1 });
            await expectInsideViewport(page, apply);
            await expect(page.getByRole('region', { name: 'Unsaved changes' }).getByText('1 unsaved change in')).toBeInViewport({ ratio: 1 });
            const discard = page.getByRole('button', { name: 'Discard changes', exact: true });
            await expect(discard).toBeInViewport({ ratio: 1 });
            await expectInsideViewport(page, discard);
            await expectNoHorizontalOverflow(page);

            await apply.focus();
            await expect(apply).toBeFocused();
            await page.keyboard.press('Enter');
            await expect.poll(() => saves.length).toBe(1);
            expect(saves[0].mqtt_server).toBe('mqtt-broker');
        });

        test('the save bar takes well under half the phone, with the save rule one tap away', async ({ page }) => {
            await openConnectionSettings(page);
            await page.locator('#mqtt-server').fill('mqtt-broker');
            const bar = page.getByRole('region', { name: 'Unsaved changes' });
            await expect(bar).toBeVisible();
            const height = (await bar.boundingBox())?.height ?? Infinity;
            // About two thirds of a 390px phone before; under half there now. At 320px the column is
            // too narrow for both buttons on one row, so they stack, and the bar stays under two thirds.
            expect(height).toBeLessThan(740 * (width === 320 ? 0.65 : 0.45));
            // The rule is not repeated on every change; it opens in place and says what waits.
            await expect(bar.locator('[data-settings-save-rule]')).toHaveCount(0);
            const how = bar.getByRole('button', { name: 'How saving works', exact: true });
            await expect(how).toHaveAttribute('aria-expanded', 'false');
            await how.click();
            await expect(bar.locator('#settings-save-rule')).toContainText('Changes to settings wait until you choose Save changes.');
            await expectNoHorizontalOverflow(page);
        });

        test('the saved notification wraps inside the screen', async ({ page }) => {
            await openConnectionSettings(page);
            await page.locator('#mqtt-server').fill('mqtt-broker');
            await page.getByRole('button', { name: 'Save changes', exact: true }).click();

            const toast = page.locator('[data-toast-container] [data-toast]').filter({ hasText: 'Settings saved' });
            await expect(toast).toBeInViewport({ ratio: 1 });
            await expectInsideViewport(page, toast);
            await expectInsideViewport(page, toast.getByRole('button', { name: 'Close notification' }));
            await expectNoHorizontalOverflow(page);
        });
    });
}

test('a control reached with Tab is never hidden under the save bar', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openConnectionSettings(page);
    await page.locator('#mqtt-server').fill('broker.lan');
    const bar = page.locator('[data-settings-save-bar]');
    await expect(bar).toBeVisible();
    await page.locator('#frigate-url').focus();
    const hidden: string[] = [];
    for (let step = 0; step < 40; step += 1) {
        await page.keyboard.press('Tab');
        const overlap = await page.evaluate(() => {
            const focused = document.activeElement as HTMLElement | null;
            const barElement = document.querySelector('[data-settings-save-bar]');
            // After the last stop focus leaves the page and falls back to <body>: nothing is hidden then.
            if (!focused || focused === document.body || !barElement || barElement.contains(focused)) return null;
            const box = focused.getBoundingClientRect();
            if (box.height === 0) return null;
            const name = focused.id || `${focused.tagName.toLowerCase()}.${focused.className.toString().split(' ').slice(0, 4).join('.')} "${(focused.textContent ?? '').trim().slice(0, 24)}"`;
            return box.bottom > barElement.getBoundingClientRect().top + 1 ? name : null;
        });
        if (overlap) hidden.push(overlap);
    }
    expect(hidden).toEqual([]);
});
