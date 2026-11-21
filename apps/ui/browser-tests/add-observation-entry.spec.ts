import { expect, test, type Page } from '@playwright/test';
import { replayFeeder, settled } from './accessibility-mock';

/**
 * Add observation is an action, not a place. The owner opens it from the header's controls (beside
 * Refresh) or the Explorer's labelled button; on a phone, whose header has no room for a fifth
 * control, it is a place in the menu instead. A guest is offered none of them, and the old address
 * still opens the page.
 */
const READY = { timeout: 15_000 };
const GUEST = { auth_required: true, is_authenticated: false, public_access_enabled: true };

async function open(page: Page, path: string, size: { width: number; height: number }, guest = false): Promise<void> {
    await page.setViewportSize(size);
    await replayFeeder(page, 'light', {}, (json, url) =>
        guest && url.pathname === '/api/auth/status' ? { ...(json as Record<string, unknown>), ...GUEST } : json
    );
    await page.goto(path);
    await expect(page.locator('main h1').first()).toBeVisible(READY);
    await expect(page.locator('main [data-route-loading]')).toHaveCount(0, READY);
    await settled(page);
}

const headerEntry = (page: Page) => page.locator('main header').getByRole('link', { name: 'Add observation', exact: true });
const explorerEntry = (page: Page) => page.locator('[data-add-observation="labelled"]');
const menuPlace = (page: Page) => page.locator('#app-sidebar nav [data-nav-path="/observations/new"]');

async function expectAddObservationPage(page: Page): Promise<void> {
    await expect.poll(() => new URL(page.url()).pathname).toBe('/observations/new');
    await expect(page.getByRole('heading', { level: 1, name: 'Add observation', exact: true })).toBeVisible(READY);
}

test('the owner opens Add observation from the header, which then marks the page as current', async ({ page }) => {
    await open(page, '/events', { width: 1440, height: 900 });
    const entry = headerEntry(page);
    await expect(entry).toBeVisible();
    await expect(entry).toHaveAttribute('title', 'Add observation');
    await expect(entry).toHaveAttribute('href', '/observations/new');
    await expect(entry).not.toHaveAttribute('aria-current', /.*/);
    // The sidebar no longer lists it.
    await expect(menuPlace(page)).toHaveCount(0);
    await expect(page.locator('#app-sidebar nav').getByText('Add observation', { exact: true })).toHaveCount(0);
    // A square control like its neighbours, between Refresh and the camera.
    const order = await page.locator('main header').first().evaluate((header) => {
        const controls = [...header.querySelectorAll<HTMLElement>('a[data-add-observation], button')].filter((node) => node.offsetParent !== null);
        return controls.map((node) => (node.getAttribute('aria-haspopup') === 'dialog' ? 'camera' : node.getAttribute('aria-label') ?? ''));
    });
    expect(order.indexOf('Refresh')).toBeGreaterThan(-1);
    expect(order.indexOf('Add observation')).toBe(order.indexOf('Refresh') + 1);
    expect(order[order.indexOf('Add observation') + 1]).toBe('camera');
    const [add, refresh] = await Promise.all([entry.boundingBox(), page.locator('main header').getByRole('button', { name: 'Refresh', exact: true }).boundingBox()]);
    expect(add && refresh && Math.round(add.width) === Math.round(refresh.width) && Math.round(add.height) === Math.round(refresh.height)).toBe(true);

    await entry.click();
    await expectAddObservationPage(page);
    // The sidebar no longer marks the page, so the header does: by its name to a screen reader, and by
    // a filled ground (a shape, not a tint alone) to the eye.
    await expect(entry).toHaveAttribute('aria-current', 'page');
    const ground = await entry.evaluate((node) => getComputedStyle(node).backgroundColor);
    expect(ground).not.toBe('rgba(0, 0, 0, 0)');
    await expect(page.locator('#app-sidebar nav [aria-current="page"]')).toHaveCount(0);
});

test('the owner opens Add observation from the Explorer\'s labelled button', async ({ page }) => {
    await open(page, '/events', { width: 1440, height: 900 });
    const button = explorerEntry(page);
    await expect(button).toBeVisible();
    await expect(button).toHaveAccessibleName('Add observation');
    await expect(button).toHaveClass(/\bbtn\b/);
    await expect(button.locator('svg')).toHaveCount(1);
    // The last of the Explorer header row's controls.
    const last = await page.locator('[data-explorer-controls]').evaluate((row) => row.lastElementChild?.getAttribute('data-add-observation'));
    expect(last).toBe('labelled');
    await button.click();
    await expectAddObservationPage(page);
});

test('the old address still opens the page', async ({ page }) => {
    await open(page, '/observations/new', { width: 1440, height: 900 });
    await expectAddObservationPage(page);
    await expect(headerEntry(page)).toHaveAttribute('aria-current', 'page');
});

test('the header entry is reached by keyboard after Refresh, shows its focus ring, and opens on Enter', async ({ page }) => {
    await open(page, '/events', { width: 1440, height: 900 });
    const refresh = page.locator('main header').getByRole('button', { name: 'Refresh', exact: true });
    await expect(refresh).toBeEnabled();
    await refresh.focus();
    await page.keyboard.press('Tab');
    const entry = headerEntry(page);
    await expect(entry).toBeFocused();
    const ring = await entry.evaluate((node) => ({ visible: node.matches(':focus-visible'), shadow: getComputedStyle(node).boxShadow }));
    expect(ring.visible).toBe(true);
    expect(ring.shadow).not.toBe('none');
    await page.keyboard.press('Enter');
    await expectAddObservationPage(page);
});

test('a guest is offered Add observation nowhere: not in the header, the Explorer or the menu', async ({ page }) => {
    await open(page, '/events', { width: 1440, height: 900 }, true);
    await expect(page.locator('[data-add-observation]')).toHaveCount(0);
    await expect(menuPlace(page)).toHaveCount(0);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator('button[aria-controls="app-sidebar"]').click();
    await expect(page.locator('#app-sidebar nav')).toBeVisible();
    await expect(menuPlace(page)).toHaveCount(0);
    await expect(page.locator('[data-add-observation]')).toHaveCount(0);
});

test('on a 390 px phone the header keeps its four controls and the title whole; Add observation is in the menu', async ({ page }) => {
    await open(page, '/species', { width: 390, height: 844 });
    const header = page.locator('main header').first();
    await expect(headerEntry(page)).toHaveCount(0);
    const fit = await header.evaluate((node) => {
        const controls = [...node.querySelectorAll<HTMLElement>('button, a')].filter((control) => control.offsetParent !== null);
        const title = node.querySelector('h1');
        const lineHeight = title ? parseFloat(getComputedStyle(title).lineHeight) : 0;
        return {
            overflow: node.scrollWidth - node.clientWidth,
            outside: controls.filter((control) => {
                const box = control.getBoundingClientRect();
                return box.left < 0 || box.right > innerWidth;
            }).length,
            titleLines: title ? Math.round(title.getBoundingClientRect().height / lineHeight) : 0
        };
    });
    expect(fit.overflow).toBeLessThanOrEqual(0);
    expect(fit.outside).toBe(0);
    // A fifth control squeezed "Leaderboard" until it broke inside the word.
    expect(fit.titleLines).toBe(1);

    await page.locator('button[aria-controls="app-sidebar"]').click();
    const place = menuPlace(page);
    await expect(place).toBeVisible();
    await expect(place).toHaveAccessibleName('Add observation');
    await place.click();
    await expectAddObservationPage(page);
    await page.locator('button[aria-controls="app-sidebar"]').click();
    await expect(place).toHaveAttribute('aria-current', 'page');
});

test('on a 390 px phone the Explorer leads its header row with the labelled button, inside the screen', async ({ page }) => {
    await open(page, '/events', { width: 390, height: 844 });
    const button = explorerEntry(page);
    await expect(button).toBeVisible();
    const box = await button.boundingBox();
    expect(box && box.x >= 0 && box.x + box.width <= 390 && box.height >= 44).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await button.click();
    await expectAddObservationPage(page);
});
