import { test, expect, type Page, type Route } from '@playwright/test';

// Set EXPLORER_SHOTS to a directory to keep review screenshots outside the test output.
const environment = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env ?? {};
const shots = environment.EXPLORER_SHOTS;

const minutesAgo = (minutes: number) => new Date(Date.now() - minutes * 60 * 1000).toISOString();

function record(id: string, at: string) {
    return {
        frigate_event: id, display_name: 'Prunella modularis', scientific_name: 'Prunella modularis', common_name: 'Dunnock',
        camera_name: 'birdcam', detection_time: at, score: 0.91, has_clip: false
    };
}

function visit(id: string, at: string) {
    const representative = record(id, at);
    return {
        visit_id: id, start_time: at, end_time: at, capture_count: 1, best_score: 0.91, needs_review: false,
        audio_confirmed: false, representative, latest: representative, peak_capture: null
    };
}

/** Each test decides how the visits and captures endpoints answer; everything else is a quiet default. */
interface Boundary {
    visits?: (route: Route, url: URL) => Promise<void> | void;
    events?: (route: Route, url: URL) => Promise<void> | void;
    gardenVisits?: (route: Route, url: URL) => Promise<void> | void;
}

const allVisits = (count: number) => Array.from({ length: count }, (_, index) => visit(`v${index}`, minutesAgo(10 + index * 5)));

function pageOf(url: URL, items: ReturnType<typeof visit>[]) {
    const limit = Number(url.searchParams.get('limit') ?? 24);
    const offset = Number(url.searchParams.get('offset') ?? 0);
    return { total: items.length, gap_seconds: 60, visits: items.slice(offset, offset + limit) };
}

async function openExplorer(page: Page, boundary: Boundary, query = '') {
    const errors: string[] = [];
    page.on('pageerror', error => { if (!error.message.includes('ResizeObserver loop')) errors.push(error.message); });
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route(url => url.pathname.startsWith('/api/'), route => {
        const url = new URL(route.request().url());
        const path = url.pathname;
        if (path === '/api/visits') return boundary.visits ? boundary.visits(route, url) : route.fulfill({ json: pageOf(url, allVisits(2)) });
        if (path === '/api/events') {
            if (boundary.events) return boundary.events(route, url);
            return route.fulfill({ json: [record('c0', minutesAgo(10)), record('c1', minutesAgo(15))] });
        }
        if (path === '/api/events/count') return route.fulfill({ json: { count: 2 } });
        if (path === '/api/garden/visits' && boundary.gardenVisits) return boundary.gardenVisits(route, url);
        if (path === '/api/garden/visits') return route.fulfill({ json: { visits: [], total: 0, capture_total: 0, limit: 24, offset: 0 } });
        if (path.endsWith('/filters')) return route.fulfill({ json: { species: [], cameras: [], camera_counts: {}, totals: { total: 2, favorites: 0, audio_matched: 0 } } });
        if (path.endsWith('.jpg')) return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="120"><rect width="160" height="120" fill="#4d7c0f"/></svg>' });
        if (path.endsWith('/labels') || path.endsWith('/species')) return route.fulfill({ json: [] });
        return route.fulfill({ json: { count: 0 } });
    });
    await page.goto(`/browser-tests/owner-history.html?surface=explorer${query}`);
    return errors;
}

const count = (page: Page) => page.locator('[data-explorer-count]');
const results = (page: Page) => page.locator('[data-explorer-results]');

test('a failed first read says so with Try again, never "No events yet" or "0 visits"', async ({ page }) => {
    let fail = true;
    const errors = await openExplorer(page, {
        visits: (route, url) => fail ? route.fulfill({ status: 500, json: { detail: 'boom' } }) : route.fulfill({ json: pageOf(url, allVisits(2)) })
    });
    const alert = page.getByRole('alert').filter({ hasText: 'The visits could not be loaded. Your history is unchanged.' });
    await expect(alert).toBeVisible();
    await expect(alert).toHaveAttribute('data-explorer-error', 'error');
    await expect(count(page)).toHaveText('Count unavailable');
    await expect(count(page)).toHaveAttribute('role', 'status');
    await expect(page.getByText('No events yet')).toHaveCount(0);
    await expect(page.getByText(/^0 visits$/)).toHaveCount(0);
    await expect(page.locator('[data-explorer-empty]')).toHaveCount(0);
    const retry = alert.getByRole('button', { name: 'Try again' });
    expect((await retry.boundingBox())?.height ?? 0).toBeGreaterThanOrEqual(44);
    if (shots) await page.screenshot({ path: `${shots}/explorer-error-first-load.png` });

    fail = false;
    await retry.click();
    await expect(page.locator('[data-explorer-visit="v0"] [data-detection-card]')).toBeVisible();
    await expect(page.getByRole('alert')).toHaveCount(0);
    await expect(count(page)).toHaveText('2 visits');
    expect(errors).toEqual([]);
});

test('a failed refresh keeps the earlier results, dimmed, beneath the alert', async ({ page }) => {
    const errors = await openExplorer(page, { events: route => route.fulfill({ status: 500, json: { detail: 'boom' } }) });
    await expect(page.locator('[data-explorer-visit="v0"] [data-detection-card]')).toBeVisible();
    // Selecting reads individual captures, which this boundary refuses.
    await page.getByRole('button', { name: 'Multi-select' }).click();
    const alert = page.getByRole('alert').filter({ hasText: 'The captures could not be loaded. Your history is unchanged.' });
    await expect(alert).toHaveAttribute('data-explorer-error', 'results');
    await expect(results(page)).toHaveAttribute('data-explorer-stale', 'true');
    await expect.poll(() => results(page).evaluate(node => getComputedStyle(node).opacity)).toBe('0.6');
    await expect(page.locator('[data-explorer-visit="v0"] [data-detection-card]')).toBeVisible();
    await expect(count(page)).toHaveText('Count unavailable');
    if (shots) await page.screenshot({ path: `${shots}/explorer-error-stale.png` });
    expect(errors).toEqual([]);
});

test('the first read shows placeholders in the card anatomy and no count until one is measured', async ({ page }) => {
    let release: () => void = () => {};
    const held = new Promise<void>(resolve => { release = resolve; });
    const errors = await openExplorer(page, {
        visits: async (route, url) => { await held; await route.fulfill({ json: pageOf(url, allVisits(2)) }); }
    });
    await expect(page.locator('[data-explorer-placeholder="card"]').first()).toBeVisible();
    await expect(results(page)).toHaveAttribute('aria-busy', 'true');
    await expect(count(page)).toHaveAttribute('data-explorer-count', 'pending');
    await expect(count(page)).not.toContainText(/\d/);
    await expect(page.getByText('No events yet')).toHaveCount(0);
    // A placeholder card is the size of a real one: a 4:3 photo over the body.
    const photo = page.locator('[data-explorer-placeholder="card"]').first().locator('[data-loading-placeholder]').first();
    const box = await photo.boundingBox();
    expect(Math.abs((box?.width ?? 0) * 3 / 4 - (box?.height ?? 0))).toBeLessThanOrEqual(1);
    if (shots) await page.screenshot({ path: `${shots}/explorer-first-load.png` });

    release();
    await expect(page.locator('[data-explorer-visit="v0"] [data-detection-card]')).toBeVisible();
    await expect(page.locator('[data-explorer-placeholder]')).toHaveCount(0);
    await expect(results(page)).toHaveAttribute('aria-busy', 'false');
    await expect(count(page)).toHaveText('2 visits');
    expect(errors).toEqual([]);
});

test('list placeholders take the row anatomy and stand still under reduced motion', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.addInitScript(() => localStorage.setItem('yawamf:explorer-view', 'list'));
    const errors = await openExplorer(page, { visits: () => new Promise<void>(() => {}) });
    const rows = page.locator('[data-explorer-list] [data-explorer-placeholder="row"]');
    await expect(rows.first()).toBeVisible();
    expect(await rows.count()).toBeGreaterThan(3);
    const animations = await page.locator('[data-loading-placeholder]').evaluateAll(nodes => [...new Set(nodes.map(node => getComputedStyle(node).animationName))]);
    expect(animations).toEqual(['none']);
    expect(errors).toEqual([]);
});

test('a refetch dims the results it is replacing and marks them busy', async ({ page }) => {
    let hold = false;
    let release: () => void = () => {};
    const errors = await openExplorer(page, {
        visits: async (route, url) => {
            if (hold) await new Promise<void>(resolve => { release = resolve; });
            await route.fulfill({ json: pageOf(url, allVisits(30)) });
        }
    });
    await expect(page.locator('[data-explorer-visit="v0"] [data-detection-card]')).toBeVisible();
    hold = true;
    await page.getByRole('button', { name: 'Next page' }).click();
    await expect(results(page)).toHaveAttribute('aria-busy', 'true');
    await expect(results(page)).toHaveAttribute('data-explorer-stale', 'true');
    await expect.poll(() => results(page).evaluate(node => getComputedStyle(node).opacity)).toBe('0.6');
    release();
    await expect(page.locator('[data-explorer-visit="v24"]')).toBeVisible();
    await expect(results(page)).toHaveAttribute('aria-busy', 'false');
    await expect.poll(() => results(page).evaluate(node => getComputedStyle(node).opacity)).toBe('1');
    expect(errors).toEqual([]);
});

test('changing page starts at the top of the results with focus on the count', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    const errors = await openExplorer(page, { visits: (route, url) => route.fulfill({ json: pageOf(url, allVisits(30)) }) });
    await expect(page.locator('[data-explorer-visit="v0"] [data-detection-card]')).toBeVisible();
    const next = page.getByRole('button', { name: 'Next page' });
    await next.scrollIntoViewIfNeeded();
    expect(await page.evaluate(() => scrollY)).toBeGreaterThan(400);
    await next.click();
    await expect(page.locator('[data-explorer-visit="v24"]')).toBeVisible();
    await expect(count(page)).toBeFocused();
    await expect.poll(() => count(page).evaluate(node => node.getBoundingClientRect().top)).toBeLessThan(100);
    await expect.poll(() => count(page).evaluate(node => node.getBoundingClientRect().top)).toBeGreaterThanOrEqual(-1);
    expect(errors).toEqual([]);
});

test('selection is a pressed toggle named by what it picks, shown by a ring and a check, never a blur', async ({ page }) => {
    const errors = await openExplorer(page, {});
    await expect(page.locator('[data-explorer-visit="v0"] [data-detection-card]')).toBeVisible();
    await page.getByRole('button', { name: 'Multi-select' }).click();
    await expect(page.locator('[data-explorer-selection-count]')).toHaveText('No captures selected');
    const toggles = page.getByRole('button', { name: /^Select Dunnock, \d{1,2}:\d{2}/ });
    await expect(toggles).toHaveCount(2);
    const first = toggles.first();
    await expect(first).toHaveAttribute('aria-pressed', 'false');
    const card = page.locator('[data-detection-card]').first();
    await expect(card.locator('[data-detection-card-check]')).toHaveAttribute('data-detection-card-check', 'unselected');

    await first.click();
    await expect(first).toHaveAttribute('aria-pressed', 'true');
    await expect(card.locator('[data-detection-card-check]')).toHaveAttribute('data-detection-card-check', 'selected');
    await expect(page.locator('[data-explorer-selection-count]')).toHaveText('1 capture selected');
    // Nothing over the card blurs the photo or the name.
    const blurred = await card.evaluate(node => [node, ...node.querySelectorAll('*')].some(element => {
        const style = getComputedStyle(element);
        return style.backdropFilter !== 'none' && style.backdropFilter !== '' && element.getBoundingClientRect().width > node.getBoundingClientRect().width / 2;
    }));
    expect(blurred).toBe(false);
    await expect(card.getByRole('heading', { name: 'Dunnock' })).toBeVisible();
    if (shots) await page.screenshot({ path: `${shots}/explorer-selected-card.png` });

    await toggles.nth(1).click();
    await expect(page.locator('[data-explorer-selection-count]')).toHaveText('2 captures selected');

    // The list row exposes the same state.
    await page.locator('[data-explorer-view-toggle="list"]').click();
    const rows = page.locator('[data-detection-row]').getByRole('button', { name: /^Select Dunnock, \d{1,2}:\d{2}/ });
    await expect(rows.first()).toHaveAttribute('aria-pressed', 'true');
    await rows.first().click();
    await expect(rows.first()).toHaveAttribute('aria-pressed', 'false');
    await expect(page.locator('[data-explorer-selection-count]')).toHaveText('1 capture selected');
    expect(errors).toEqual([]);
});

for (const [label, enlarge] of [
    ['the largest text size', async (page: Page) => page.evaluate(() => document.documentElement.style.setProperty('--text-scale', '1.5'))],
    ['a 200% root font', async (page: Page) => page.evaluate(() => { document.documentElement.style.fontSize = '200%'; })]
] as const) {
    test(`cards fit a 320px phone at ${label}`, async ({ page }) => {
        await page.setViewportSize({ width: 320, height: 900 });
        const errors = await openExplorer(page, {});
        await expect(page.locator('[data-explorer-visit="v0"] [data-detection-card]')).toBeVisible();
        await enlarge(page);
        await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        const grid = page.locator('[data-explorer-grid]');
        const card = page.locator('[data-explorer-visit="v0"] [data-detection-card]');
        const [gridBox, cardBox] = [await grid.boundingBox(), await card.boundingBox()];
        expect((cardBox?.x ?? 0) + (cardBox?.width ?? 0)).toBeLessThanOrEqual((gridBox?.x ?? 0) + (gridBox?.width ?? 0) + 0.5);
        if (shots) await page.screenshot({ path: `${shots}/explorer-320-${label.replace(/\W+/g, '-')}.png` });
        expect(errors).toEqual([]);
    });
}

test('an empty Garden view points to Review, Dismissed, not the retired Garden page', async ({ page }) => {
    const errors = await openExplorer(page, {}, '&garden=1');
    await expect(page.locator('[data-explorer-visit="v0"] [data-detection-card]')).toBeVisible();
    const option = page.locator('[data-explorer-subjects-option="garden"]');
    if (!(await option.isVisible())) await page.locator('[data-explorer-filter-toggle]').click();
    await option.click();
    const empty = page.locator('[data-explorer-garden-empty]');
    await expect(empty).toContainText('Dismissed captures are under Review, Dismissed.');
    await expect(empty).not.toContainText('Garden page');
    expect(errors).toEqual([]);
});
