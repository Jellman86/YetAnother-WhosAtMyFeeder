import { expect, test } from '@playwright/test';

// The real App shell includes the media-query listener and sidebar transition.
test('app headers fit 320px with 200% text after desktop resize', async ({ page }, testInfo) => {
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route(url => url.pathname.startsWith('/api/'), async route => {
        const path = new URL(route.request().url()).pathname;
        const responses: Record<string, unknown> = {
            '/api/auth/status': { auth_required: false, is_authenticated: true, needs_initial_setup: false },
            '/api/settings': { cameras: ['patio'], garden_cameras: ['patio'], beta_garden_animals: true },
            '/api/garden': { items: [], total: 0, limit: 8, offset: 0 },
            '/api/garden/identification': { models: [], busy: false, catalogue_ready: false },
            '/api/garden/motion': { cameras: [], installed: false, state: 'disabled', message: 'Off' },
            '/api/events/filters': { cameras: ['patio'], species: [] },
            '/api/frigate/cameras/status': { cameras: [] },
            '/api/update-status': { update_available: false },
        };
        if (path in responses) return route.fulfill({ json: responses[path] });
        return route.fulfill({ status: 503, json: { detail: 'Unavailable in header fixture' } });
    });
    await page.route('**/health', route => route.fulfill({ json: { status: 'healthy' } }));
    const refresh = page.locator('main header').getByRole('button', { name: 'Refresh', exact: true });
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto('/garden');
    await expect(page.getByRole('heading', { name: 'Garden animals', exact: true })).toBeVisible();
    await expect(refresh).toBeVisible();
    await page.setViewportSize({ width: 320, height: 900 });
    await page.evaluate(() => document.documentElement.style.fontSize = '200%');
    const menu = page.getByRole('button', { name: 'Toggle menu', exact: true });
    await expect(menu).toBeVisible();
    await expect.poll(() => page.locator('#main-content').evaluate(node => {
        const bounds = node.getBoundingClientRect();
        return bounds.x === 0 && bounds.width === document.documentElement.clientWidth;
    })).toBe(true);
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const controls = page.locator('main header button:visible, .sticky.md\\:hidden button:visible');
    const bounds = await controls.evaluateAll(nodes => nodes.map(node => {
        const { x, width, height } = node.getBoundingClientRect();
        return { label: node.getAttribute('aria-label'), x, width, height };
    }));
    expect(bounds.length).toBeGreaterThanOrEqual(6);
    for (const bound of bounds) {
        expect(bound.width, `${bound.label} width`).toBeGreaterThanOrEqual(44);
        expect(bound.height, `${bound.label} height`).toBeGreaterThanOrEqual(44);
        expect(bound.x, `${bound.label} left`).toBeGreaterThanOrEqual(0);
        expect(bound.x + bound.width, `${bound.label} right`).toBeLessThanOrEqual(320);
    }
    await menu.click();
    await expect(page.locator('aside').getByRole('button', { name: 'Garden animals', exact: true })).toBeVisible();
    await expect.poll(() => page.locator('aside').evaluate(node => node.getBoundingClientRect().right <= innerWidth)).toBe(true);
    await page.locator('aside').getByRole('button', { name: 'Garden animals', exact: true }).click();
    await expect.poll(() => page.locator('aside').evaluate(node => node.getBoundingClientRect().right <= 0)).toBe(true);
    await refresh.focus();
    await expect(refresh).toBeFocused();
    const reloaded = page.waitForResponse(response => new URL(response.url()).pathname === '/api/garden');
    await page.keyboard.press('Enter');
    await reloaded;
    await expect(refresh).toBeEnabled();
    const camera = page.locator('main header button[aria-haspopup="dialog"]');
    await camera.focus();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('dialog', { name: 'Live camera viewer', exact: true })).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(camera).toBeFocused();
    await page.evaluate(() => window.scrollTo(0, 0));
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth && scrollX === 0)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath('app-header-320-large-text.png'), fullPage: true });
    expect(errors).toEqual([]);
});
