import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { replayFeeder, settled, type Theme } from './accessibility-mock';

/**
 * axe-core over the real app, with a month of data on every page, in both themes. A serious or
 * critical violation fails the build: contrast under 4.5:1, a control with no name or a name that
 * hides its visible words, list and definition-list structure, an unnamed progress bar.
 *
 * axe cannot assess focus order, target size beyond its own rule, or meaning carried by colour, so
 * this is a floor under the manual checks, not a replacement for them.
 */
const THEMES: Theme[] = ['light', 'dark'];
// A route is its own lazy chunk; on a busy CI runner its first paint can take several seconds.
const READY = { timeout: 15_000 };

const ROUTES: { name: string; path: string; ready: (page: Page) => Promise<void> }[] = [
    { name: 'Dashboard', path: '/', ready: (page) => expect(page.locator('[data-field-log-row]').first()).toBeVisible(READY) },
    { name: 'Explorer', path: '/events', ready: (page) => expect(page.locator('[data-detection-card], [data-detection-row]').first()).toBeVisible(READY) },
    { name: 'Leaderboard', path: '/species', ready: (page) => expect(page.locator('[data-capture-wall-segment]').first()).toBeVisible(READY) },
    { name: 'Audio history', path: '/audio', ready: (page) => expect(page.locator('[data-audio-top-species-button]').first()).toBeVisible(READY) },
    { name: 'Notifications', path: '/notifications', ready: (page) => expect(page.getByText('Taxonomy sync').first()).toBeVisible(READY) },
    { name: 'About', path: '/about', ready: (page) => expect(page.locator('#about-outbound-title')).toBeVisible(READY) },
    { name: 'Add observation', path: '/observations/new', ready: (page) => expect(page.getByRole('heading', { level: 1 })).toBeVisible(READY) },
    { name: 'Model evaluation', path: '/diagnostics/model-eval', ready: (page) => expect(page.getByRole('heading', { level: 1 })).toBeVisible(READY) },
    { name: 'Health', path: '/settings/health', ready: (page) => expect(page.locator('[data-sidebar-status-link]')).toBeVisible(READY) },
    { name: 'Not found', path: '/no-such-page', ready: (page) => expect(page.locator('#not-found-heading')).toBeVisible(READY) }
];

interface Finding { rule: string; impact: string; target: string; summary: string }

/** Every serious or critical axe finding on the page, one line each, so a failure names the element. */
async function seriousFindings(page: Page, include?: string): Promise<Finding[]> {
    const builder = new AxeBuilder({ page });
    if (include) builder.include(include);
    const results = await builder.analyze();
    return results.violations
        .filter((violation) => violation.impact === 'serious' || violation.impact === 'critical')
        .flatMap((violation) => violation.nodes.map((node) => ({
            rule: violation.id,
            impact: violation.impact ?? '',
            target: node.target.join(' '),
            summary: (node.failureSummary ?? '').replace(/\s+/g, ' ').slice(0, 220)
        })));
}

for (const theme of THEMES) {
    test.describe(`${theme} theme`, () => {
        test.use({ viewport: { width: 1440, height: 900 } });

        for (const route of ROUTES) {
            test(`${route.name} has no serious accessibility violation`, async ({ page }) => {
                await replayFeeder(page, theme);
                await page.goto(route.path);
                await route.ready(page);
                await settled(page);
                // The Health tab's own panels belong to Settings; here it is the shell around them that is checked.
                expect(await seriousFindings(page, route.name === 'Health' ? '#app-sidebar' : undefined)).toEqual([]);
            });
        }

        test('the record dialog has no serious accessibility violation', async ({ page }) => {
            await replayFeeder(page, theme);
            await page.goto('/');
            await page.locator('[data-field-log-row] [data-field-log-action]').first().click();
            await expect(page.getByRole('dialog')).toBeVisible();
            // The record is a lazy chunk: its actions are the last thing it draws.
            await expect(page.locator('[data-detection-delete]')).toBeVisible();
            await settled(page);
            expect(await seriousFindings(page)).toEqual([]);
        });

        test('the sign-in screen has no accessibility violation at all, and one main landmark', async ({ page }) => {
            await replayFeeder(page, theme, {
                '/api/auth/status': { auth_required: true, public_access_enabled: false, is_authenticated: false, needs_initial_setup: false }
            });
            await page.goto('/');
            await expect(page.getByRole('heading', { level: 1, name: 'Sign in' })).toBeVisible();
            await settled(page);
            const results = await new AxeBuilder({ page }).analyze();
            expect(results.violations.map((violation) => violation.id)).toEqual([]);
            await expect(page.getByRole('main')).toHaveCount(1);
            // The skip link has somewhere to go.
            await expect(page.locator('#main-content')).toHaveCount(1);
        });
    });

    test.describe(`${theme} theme on a phone`, () => {
        test.use({ viewport: { width: 390, height: 844 } });

        test('the Dashboard and its open navigation drawer have no serious accessibility violation', async ({ page }) => {
            await replayFeeder(page, theme);
            await page.goto('/');
            await expect(page.locator('[data-field-log-row]').first()).toBeVisible();
            await settled(page);
            expect(await seriousFindings(page)).toEqual([]);
            await page.getByRole('banner').getByRole('button').first().click();
            await expect(page.locator('[data-sidebar-drawer="open"]')).toBeVisible();
            await settled(page);
            expect(await seriousFindings(page)).toEqual([]);
        });
    });
}

test('the sidebar status is a list inside a live region, and its link is named by its words', async ({ page }) => {
    await replayFeeder(page, 'light');
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/about');
    const tiles = page.locator('[data-status-tiles]');
    await expect(tiles).toBeVisible();
    // The list keeps its own role; the live region is its wrapper.
    await expect(tiles).not.toHaveAttribute('role');
    await expect(page.getByRole('status').filter({ has: tiles })).toHaveCount(1);
    expect(await tiles.getByRole('listitem').count()).toBeGreaterThanOrEqual(2);
    const link = page.locator('[data-sidebar-status-link]');
    await expect(link).toHaveAccessibleName('System health');
    await expect(link).not.toHaveAttribute('aria-label');
    // The link's hit area is the whole card, apart from the tiles.
    const card = await page.locator('[data-sidebar-status-card]').boundingBox();
    expect(card).not.toBeNull();
    await page.mouse.click((card?.x ?? 0) + 12, (card?.y ?? 0) + 12);
    await expect(page).toHaveURL(/\/settings\/health$/);
});

test.describe('text at 200%', () => {
    // WCAG 1.4.4: a 1280px window zoomed to 200% is 640 CSS px wide with the text twice the size.
    test.use({ viewport: { width: 640, height: 450 } });

    for (const route of ROUTES.filter((entry) => ['Dashboard', 'Explorer', 'Leaderboard', 'Audio history', 'Notifications', 'About'].includes(entry.name))) {
        test(`${route.name} keeps every word and never scrolls sideways`, async ({ page }) => {
            await replayFeeder(page, 'light');
            await page.addInitScript(() => localStorage.setItem('text_size', 'largest'));
            await page.goto(route.path);
            await route.ready(page);
            await settled(page);
            await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(0);
            // The drawer's navigation labels wrap; none is cut short.
            await page.getByRole('banner').getByRole('button').first().click();
            const labels = page.locator('#app-sidebar nav button span');
            await expect(labels.first()).toBeVisible();
            const cut = await labels.evaluateAll((nodes) => nodes.filter((node) => node.scrollWidth > node.clientWidth + 1).map((node) => node.textContent));
            expect(cut).toEqual([]);
        });
    }
});

test('the page declares the language on screen, and a long German label is shown whole', async ({ page }) => {
    await replayFeeder(page, 'light');
    await page.addInitScript(() => localStorage.setItem('preferred-language', 'de'));
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/about');
    await expect(page.locator('html')).toHaveAttribute('lang', 'de');
    const labels = page.locator('#app-sidebar nav button span');
    await expect(labels.filter({ hasText: 'Beobachtung hinzufügen' })).toBeVisible();
    const cut = await labels.evaluateAll((nodes) => nodes.filter((node) => node.scrollWidth > node.clientWidth + 1).map((node) => node.textContent));
    expect(cut).toEqual([]);
});

for (const theme of THEMES) {
    test(`keyboard focus draws an opaque ring that stands out from the page (${theme})`, async ({ page }) => {
        await replayFeeder(page, theme);
        await page.setViewportSize({ width: 1440, height: 900 });
        await page.goto('/events');
        await expect(page.locator('#app-sidebar nav button').first()).toBeVisible();
        await settled(page);
        const ring = await page.evaluate(() => {
            const parse = (colour: string): number[] => (colour.match(/[\d.]+/g) ?? []).map(Number);
            const luminance = ([red, green, blue]: number[]): number => {
                const channel = (value: number): number => { const unit = value / 255; return unit <= 0.03928 ? unit / 12.92 : ((unit + 0.055) / 1.055) ** 2.4; };
                return 0.2126 * channel(red) + 0.7152 * channel(green) + 0.0722 * channel(blue);
            };
            const contrast = (first: number[], second: number[]): number => {
                const [lighter, darker] = [luminance(first), luminance(second)].sort((a, b) => b - a);
                return (lighter + 0.05) / (darker + 0.05);
            };
            const style = getComputedStyle(document.documentElement);
            const focus = parse(`rgb(${style.getPropertyValue('--focus')})`);
            const grounds = ['--surface', '--surface-raised'].map((name) => parse(`rgb(${style.getPropertyValue(name)})`));
            grounds.push(parse(getComputedStyle(document.body).backgroundColor));
            return { alpha: focus.length, ratios: grounds.map((ground) => contrast(focus, ground)) };
        });
        expect(ring.alpha, 'the focus colour is three opaque channels').toBe(3);
        for (const ratio of ring.ratios) expect(ratio).toBeGreaterThanOrEqual(3);

        // The ring is really drawn in that colour on keyboard focus, on a kit button and a kit field.
        const navButton = page.locator('#app-sidebar nav button').first();
        await page.keyboard.press('Tab');
        await page.keyboard.press('Tab');
        await page.keyboard.press('Tab');
        await expect(navButton).toBeFocused();
        const drawn = await navButton.evaluate((node) => getComputedStyle(node).boxShadow);
        const expected = await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--focus').trim().split(/\s+/).join(', '));
        expect(drawn).toContain(`rgb(${expected})`);
    });
}

test('About holds still on a phone when the feeder portrait lands without a picture', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await replayFeeder(page, 'light');
    // The portrait is the slow read; the recorded feeder has no picture of its latest visit.
    await page.route((url) => url.pathname === '/api/about/portrait', async (route) => {
        await new Promise((resolve) => setTimeout(resolve, 1200));
        await route.fallback();
    });
    await page.goto('/about');
    await expect(page.locator('[data-feeder-portrait-loading]')).toBeVisible();
    const before = await page.locator('#about-workflow').evaluate((node) => node.getBoundingClientRect().top + scrollY);
    await expect(page.locator('[data-feeder-portrait]')).toBeVisible();
    await expect(page.locator('[data-feeder-portrait-no-visit]')).toBeVisible();
    const after = await page.locator('#about-workflow').evaluate((node) => node.getBoundingClientRect().top + scrollY);
    // The picture's slot is kept, so what follows moves by a line of text at most, not a photograph.
    expect(Math.abs(after - before)).toBeLessThanOrEqual(24);
});
