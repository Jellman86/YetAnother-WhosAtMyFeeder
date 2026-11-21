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
    const menu = page.getByRole('button', { name: 'Menu', exact: true });
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
    await expect(page.locator('[data-status-row="alerts"]')).toHaveCount(1);
});

test('a visitor gets one named h1 per page and no guess about notifications', async ({ page }) => {
    await mockShell(page, 'guest');
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto('/events');
    await expect(page.getByRole('heading', { level: 1, name: 'Explorer', exact: true })).toBeVisible();
    expect(await headingOnes(page)).toEqual(['Explorer']);
    // None of the owner's page controls appear for a visitor.
    await expect(page.locator('main > header button')).toHaveCount(0);
    await expect(page.locator('[data-status-row="feed"]')).toHaveCount(1);
    await expect(page.locator('[data-status-row="alerts"]')).toHaveCount(0);

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

    const menu = page.getByRole('button', { name: 'Menu', exact: true });
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

test('a camera frame that fails to load says so and gives the next step, clear of the camera chip on a phone', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await mockShell(page, 'owner');
    await page.goto('/events');
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 15_000 });
    await page.getByRole('button', { name: 'Camera status' }).click();
    const viewer = page.getByRole('dialog', { name: 'Live camera viewer' });
    const message = viewer.getByText('This frame could not be loaded', { exact: true });
    await expect(message).toBeVisible();
    await expect(viewer.locator('[data-camera-frame-help]')).toHaveText(
        'Retry asks Frigate for the frame again. If it keeps failing, Health shows whether Frigate is answering.'
    );
    const retry = viewer.getByRole('button', { name: 'Retry', exact: true });
    await expect(retry).toBeVisible();
    // With no picture to lie over, the camera's name comes first and the message below it,
    // and the whole message, Retry included, stays inside the frame.
    const helpText = viewer.locator('[data-camera-frame-help]');
    const [chip, text, button, frame] = await Promise.all([
        viewer.getByText('patio', { exact: true }).boundingBox(),
        message.boundingBox(),
        retry.boundingBox(),
        viewer.locator('[data-camera-frame="message"]').boundingBox()
    ]);
    if (!chip || !text || !button || !frame) throw new Error('The camera viewer did not lay out');
    expect(text.y).toBeGreaterThanOrEqual(chip.y + chip.height);
    expect(button.y).toBeGreaterThanOrEqual(text.y + text.height - 1);
    expect(button.y + button.height).toBeLessThanOrEqual(frame.y + frame.height + 1);
    await expect(helpText).toBeInViewport({ ratio: 0.99 });

    // At 200% text the message is taller than a 16:9 frame at this width, and can be taller than
    // the screen. The box is as tall as its words, nothing is covered, and Retry follows the
    // sentence that names the failure, so it is visible and inside the dialog without scrolling.
    await page.evaluate(() => { document.documentElement.style.fontSize = '200%'; });
    await expect(retry).toBeVisible();
    await expect(retry).toBeInViewport({ ratio: 0.99 });
    const [dialog, largeChip, largeText, largeButton, largeHelp] = await Promise.all([
        viewer.boundingBox(),
        viewer.getByText('patio', { exact: true }).boundingBox(),
        message.boundingBox(),
        retry.boundingBox(),
        helpText.boundingBox()
    ]);
    if (!dialog || !largeChip || !largeText || !largeButton || !largeHelp) throw new Error('The camera viewer did not lay out at 200% text');
    expect(largeText.y).toBeGreaterThanOrEqual(largeChip.y + largeChip.height);
    // The camera's name and state stop short of the close button.
    const [chipBox, closeBox] = await Promise.all([viewer.locator('[aria-live="polite"]').first().boundingBox(), viewer.getByRole('button', { name: 'Close', exact: true }).boundingBox()]);
    if (!chipBox || !closeBox) throw new Error('The camera chip or the close button is missing');
    expect(chipBox.x + chipBox.width).toBeLessThanOrEqual(closeBox.x);
    const chipWords = await viewer.locator('[aria-live="polite"]').first().locator('span').evaluateAll((spans) => Math.max(...spans.map((span) => span.getBoundingClientRect().right)));
    expect(chipWords).toBeLessThanOrEqual(closeBox.x);
    expect(largeButton.y).toBeGreaterThanOrEqual(largeText.y + largeText.height - 1);
    expect(largeButton.y + largeButton.height).toBeLessThanOrEqual(dialog.y + dialog.height + 1);
    expect(dialog.y + dialog.height).toBeLessThanOrEqual(844);
    expect(largeHelp.y).toBeGreaterThanOrEqual(largeButton.y + largeButton.height - 1);
    // The explanation is never clipped: what does not fit is reached by scrolling the dialog.
    await helpText.scrollIntoViewIfNeeded();
    await expect(helpText).toBeInViewport({ ratio: 0.99 });
    await retry.click({ trial: true });
});

// A browser zoomed so the window is 767.5 CSS px wide sits between "767 px and narrower" and Tailwind's
// md (768 px and wider). The shell once used the first for its phone form and the second to dock the
// sidebar, so there it had neither a menu button nor a docked sidebar, and no way to the places. A
// frame zoomed 2× stands in for the browser's zoom: its document is 767.5 CSS px wide.
test('at a zoomed width of 767.5 px the places are still reachable', async ({ page, baseURL }) => {
    await page.route(url => url.pathname.startsWith('/api/'), async route => {
        const path = new URL(route.request().url()).pathname;
        const responses: Record<string, unknown> = {
            '/api/auth/status': { auth_required: false, is_authenticated: true, needs_initial_setup: false },
            '/api/settings': { cameras: ['patio'] },
            '/api/frigate/cameras/status': { cameras: [] },
            '/api/update-status': { update_available: false },
        };
        if (path in responses) return route.fulfill({ json: responses[path] });
        return route.fulfill({ status: 503, json: { detail: 'Unavailable in header fixture' } });
    });
    await page.route('**/health', route => route.fulfill({ json: { status: 'healthy' } }));
    await page.setViewportSize({ width: 1600, height: 900 });
    await page.setContent(`<iframe id="zoomed" title="App" src="${baseURL}/about" style="width:767.5px;height:440px;border:0;zoom:2"></iframe>`);
    const app = page.frameLocator('#zoomed');
    await expect(app.getByRole('heading', { level: 1, name: 'About', exact: true })).toBeVisible({ timeout: 15_000 });
    const frame = page.frames().find((candidate) => candidate.url().endsWith('/about'));
    expect(frame).toBeTruthy();
    if (!frame) return;
    // The frame really is between the two: not 767 px or narrower, and not 768 px or wider.
    expect(await frame.evaluate(() => [matchMedia('(max-width: 767px)').matches, matchMedia('(min-width: 768px)').matches])).toEqual([false, false]);
    const placeInView = () => frame.evaluate(() => {
        const place = document.querySelector<HTMLElement>('#app-sidebar nav [data-nav-path="/events"]');
        if (!place) return false;
        const box = place.getBoundingClientRect();
        return box.width > 0 && box.left >= 0 && box.right <= innerWidth && !place.closest('[inert]');
    });
    const menu = app.getByRole('button', { name: 'Menu', exact: true });
    if (await menu.count()) await menu.click();
    await expect.poll(placeInView).toBe(true);
});
