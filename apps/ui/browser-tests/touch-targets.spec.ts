import { test, expect, type Locator } from '@playwright/test';

async function targetSizes(controls: Locator): Promise<void> {
    const bounds = await controls.evaluateAll(nodes => nodes.map(node => {
        const { width, height, x, y } = node.getBoundingClientRect();
        return { label: node.getAttribute('aria-label') || node.textContent, width, height, x, y };
    }));
    expect(bounds.length).toBeGreaterThan(0);
    for (const target of bounds) {
        expect(target.width, `${target.label} width`).toBeGreaterThanOrEqual(44);
        expect(target.height, `${target.label} height`).toBeGreaterThanOrEqual(44);
    }
    for (let a = 0; a < bounds.length; a += 1) {
        for (let b = a + 1; b < bounds.length; b += 1) {
            const left = bounds[a], right = bounds[b];
            const overlap = Math.min(left.x + left.width, right.x + right.width) - Math.max(left.x, right.x) > .5
                && Math.min(left.y + left.height, right.y + right.height) - Math.max(left.y, right.y) > .5;
            expect(overlap, `${left.label} overlaps ${right.label}`).toBe(false);
        }
    }
}

test('navigation targets fit narrow phones and keep distinct hit regions', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 320, height: 800 });
    await page.route(url => url.pathname.startsWith('/api/'), async route => {
        if (new URL(route.request().url()).pathname === '/api/update-status') {
            await route.fulfill({ json: { update_available: false } });
        } else if (new URL(route.request().url()).pathname === '/api/system-telemetry') {
            await route.fulfill({ status: 503, json: { detail: 'Fixture telemetry unavailable' } });
        } else throw new Error(`Unexpected chrome fixture request: ${route.request().url()}`);
    });
    page.on('pageerror', error => { throw error; });
    await page.goto('/browser-tests/touch-targets.html');
    await targetSizes(page.getByRole('button', { name: /^(Open menu|Switch theme)$/ }));
    await page.getByRole('button', { name: 'Open menu' }).click();
    const sidebar = page.locator('aside');
    await expect(sidebar.getByRole('button', { name: 'Log Out', exact: true })).toBeVisible();
    await targetSizes(sidebar.locator('button:visible'));
    await sidebar.getByRole('button', { name: 'English', exact: true }).click();
    await targetSizes(sidebar.getByRole('menuitem'));
    await sidebar.getByRole('menu').focus();
    await page.keyboard.press('Escape');
    await expect(sidebar.getByRole('menu')).toHaveCount(0);
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath('navigation-targets-320.png'), fullPage: true });
    await sidebar.getByRole('button', { name: 'Collapse sidebar', exact: true }).click();
    await targetSizes(sidebar.locator('button:visible'));
});
