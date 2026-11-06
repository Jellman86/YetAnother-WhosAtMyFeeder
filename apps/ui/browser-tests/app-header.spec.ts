import { expect, test } from '@playwright/test';

// The real App shell includes the media-query listener and sidebar transition.
test('app headers fit 320px with 200% text after desktop resize', async ({ page }, testInfo) => {
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route(url => url.pathname.startsWith('/api/'), async route => {
        const path = new URL(route.request().url()).pathname;
        const responses: Record<string, unknown> = {
            '/api/auth/status': { auth_required: false, is_authenticated: true, needs_initial_setup: false },
            '/api/settings': { cameras: ['patio'], garden_cameras: ['patio', 'greenhouse'], beta_garden_animals: true },
            '/api/garden/visits': { visits: [], total: 0, capture_total: 0, limit: 24, offset: 0 },
            '/api/visits': { total: 0, gap_seconds: 60, visits: [] },
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
    // The retired Garden page address opens Garden review in the Explorer.
    await page.goto('/garden');
    await expect(page.getByRole('heading', { name: 'Explorer', exact: true, level: 1 })).toBeVisible();
    await expect.poll(() => new URL(page.url()).pathname + new URL(page.url()).search).toBe('/events?visitors=garden&review=pending');
    await expect(page.locator('[data-explorer-garden-review="pending"]')).toHaveAttribute('aria-pressed', 'true');
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
    await expect(page.locator('aside').getByRole('button', { name: 'Explorer', exact: true })).toBeVisible();
    await expect(page.locator('aside').getByRole('button', { name: 'Garden animals', exact: true })).toHaveCount(0);
    await expect.poll(() => page.locator('aside').evaluate(node => node.getBoundingClientRect().right <= innerWidth)).toBe(true);
    await page.locator('aside').getByRole('button', { name: 'Explorer', exact: true }).click();
    await expect.poll(() => page.locator('aside').evaluate(node => node.getBoundingClientRect().right <= 0)).toBe(true);
    await refresh.focus();
    await expect(refresh).toBeFocused();
    const reloaded = page.waitForResponse(response => new URL(response.url()).pathname === '/api/garden/visits');
    await page.keyboard.press('Enter');
    await reloaded;
    await expect(refresh).toBeEnabled();
    const camera = page.locator('main header button[aria-haspopup="dialog"]');
    await camera.focus();
    await page.keyboard.press('Enter');
    const viewer = page.getByRole('dialog', { name: 'Live camera viewer', exact: true });
    await expect(viewer).toBeVisible();
    await expect(viewer).toContainText('patio');
    await expect(viewer).toContainText('1 / 2');
    // A camera watched only for Garden animals is still one the viewer can cycle to.
    await page.keyboard.press('ArrowRight');
    await expect(viewer).toContainText('greenhouse');
    await expect(viewer).toContainText('2 / 2');
    await page.keyboard.press('Escape');
    await expect(camera).toBeFocused();
    await page.evaluate(() => window.scrollTo(0, 0));
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth && scrollX === 0)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath('app-header-320-large-text.png'), fullPage: true });
    expect(errors).toEqual([]);
});

type ShellAccess = 'owner' | 'guest';

async function mockShell(page: import('@playwright/test').Page, access: ShellAccess): Promise<void> {
    const status = access === 'owner'
        ? { auth_required: false, is_authenticated: true, needs_initial_setup: false }
        : { auth_required: true, public_access_enabled: true, is_authenticated: false, needs_initial_setup: false };
    await page.route(url => url.pathname.startsWith('/api/'), async route => {
        const path = new URL(route.request().url()).pathname;
        const responses: Record<string, unknown> = {
            '/api/auth/status': status,
            '/api/garden/visits': { visits: [], total: 0, capture_total: 0, limit: 24, offset: 0 },
            '/api/visits': { total: 0, gap_seconds: 60, visits: [] },
            '/api/events/filters': { cameras: ['patio'], species: [] },
            '/api/frigate/cameras/status': { cameras: [] },
            '/api/update-status': { update_available: false },
        };
        if (access === 'owner') responses['/api/settings'] = { cameras: ['patio'] };
        if (path in responses) return route.fulfill({ json: responses[path] });
        return route.fulfill({ status: 503, json: { detail: 'Unavailable in shell fixture' } });
    });
    await page.route('**/health', route => route.fulfill({ json: { status: 'healthy' } }));
}

async function headingOnes(page: import('@playwright/test').Page): Promise<string[]> {
    return page.locator('h1').evaluateAll(nodes => nodes.map(node => node.textContent?.trim() ?? ''));
}

test('each owner page has one h1, named as its navigation item, and a tab title to match', async ({ page }) => {
    await mockShell(page, 'owner');
    await page.setViewportSize({ width: 1280, height: 900 });

    for (const [path, title] of [['/events', 'Explorer'], ['/species', 'Leaderboard'], ['/about', 'About'], ['/notifications', 'Notifications']]) {
        await page.goto(path);
        await expect(page.getByRole('heading', { level: 1, name: title, exact: true })).toBeVisible();
        expect(await headingOnes(page), path).toEqual([title]);
        await expect(page).toHaveTitle(`${title} · YA-WAMF`);
    }

    // The bell is the Notifications page's only way in, so it carries the current-page mark.
    const bell = page.locator('main > header').getByRole('button', { name: /^Notifications/ });
    await expect(bell).toHaveAttribute('aria-current', 'page');
    await page.goto('/events');
    await expect(page.locator('main > header').getByRole('button', { name: /^Notifications/ })).not.toHaveAttribute('aria-current', 'page');
    await expect(page.locator('aside').getByRole('button', { name: 'Explorer', exact: true })).toHaveAttribute('aria-current', 'page');

    // The Dashboard's day bar names the window; the header above it keeps only the controls.
    await page.goto('/');
    await expect(page.locator('[data-dashboard-day-bar]')).toBeVisible();
    expect(await headingOnes(page)).toEqual(['Last 24 hours']);
    await expect(page.locator('main > header').getByRole('button', { name: 'Settings', exact: true })).toBeVisible();
    await expect(page).toHaveTitle('Dashboard · YA-WAMF');
    await expect(page.locator('[data-status-tile="alerts"]')).toHaveCount(1);
});

test('a visitor gets one named h1 per page and no guess about notifications', async ({ page }) => {
    await mockShell(page, 'guest');
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto('/events');
    await expect(page.getByRole('heading', { level: 1, name: 'Explorer', exact: true })).toBeVisible();
    expect(await headingOnes(page)).toEqual(['Explorer']);
    // None of the owner's page controls appear for a visitor.
    await expect(page.locator('main > header button')).toHaveCount(0);
    await expect(page.locator('[data-status-tile="live"]')).toHaveCount(1);
    await expect(page.locator('[data-status-tile="alerts"]')).toHaveCount(0);

    await page.goto('/');
    await expect(page.locator('[data-dashboard-day-bar]')).toBeVisible();
    expect(await headingOnes(page)).toEqual(['Last 24 hours']);
});

test('an unknown address says so and offers the way back', async ({ page }) => {
    await mockShell(page, 'owner');
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto('/not-a-page');
    const notFound = page.locator('[data-not-found]');
    await expect(notFound.getByRole('heading', { level: 1, name: 'This page does not exist' })).toBeVisible();
    await expect(notFound).toContainText('The address may be from an older version.');
    expect(await headingOnes(page)).toEqual(['This page does not exist']);
    await expect(page).toHaveTitle('This page does not exist · YA-WAMF');
    await notFound.getByRole('button', { name: 'Open the dashboard' }).click();
    await expect.poll(() => new URL(page.url()).pathname).toBe('/');
    await expect(page.locator('[data-not-found]')).toHaveCount(0);
    await expect(page).toHaveTitle('Dashboard · YA-WAMF');
});

test('the phone drawer is out of the tab order when closed and modal when open', async ({ page }) => {
    await mockShell(page, 'owner');
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/events');
    await expect(page.getByRole('heading', { level: 1, name: 'Explorer' })).toBeVisible();

    const menu = page.getByRole('button', { name: 'Toggle menu', exact: true });
    const drawer = page.locator('#app-sidebar');
    await expect(menu).toHaveAttribute('aria-expanded', 'false');
    await expect(menu).toHaveAttribute('aria-controls', 'app-sidebar');
    await expect(drawer).toHaveJSProperty('inert', true);

    const focusInDrawer = () => page.evaluate(() => Boolean(document.activeElement?.closest('#app-sidebar')));
    await page.locator('body').focus();
    for (let step = 0; step < 6; step++) {
        await page.keyboard.press('Tab');
        expect(await focusInDrawer(), `tab stop ${step + 1}`).toBe(false);
    }

    await menu.focus();
    await page.keyboard.press('Enter');
    await expect(menu).toHaveAttribute('aria-expanded', 'true');
    await expect(drawer).toHaveJSProperty('inert', false);
    // Focus starts on the page you are on.
    await expect(drawer.getByRole('button', { name: 'Explorer', exact: true })).toBeFocused();
    for (let step = 0; step < 20; step++) {
        await page.keyboard.press('Tab');
        expect(await focusInDrawer(), `trapped tab ${step + 1}`).toBe(true);
    }
    await page.keyboard.press('Shift+Tab');
    expect(await focusInDrawer()).toBe(true);

    await page.keyboard.press('Escape');
    await expect(menu).toHaveAttribute('aria-expanded', 'false');
    await expect(drawer).toHaveJSProperty('inert', true);
    await expect(menu).toBeFocused();
    await expect.poll(() => drawer.evaluate(node => node.getBoundingClientRect().right <= 0)).toBe(true);
});
