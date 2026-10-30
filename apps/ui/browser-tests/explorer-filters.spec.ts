import { test, expect, type Page } from '@playwright/test';

const species = [
    { value: 'Prunella modularis', display_name: 'Dunnock', common_name: 'Dunnock', scientific_name: 'Prunella modularis', count: 12 },
    { value: 'Erithacus rubecula', display_name: 'European Robin', common_name: 'European Robin', scientific_name: 'Erithacus rubecula', count: 8 },
    ...Array.from({ length: 24 }, (_, index) => ({ value: `species-${index}`, display_name: `Species ${index + 1}`, count: 1 }))
];

async function openFilters(page: Page) {
    const requests: URL[] = [];
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route(url => url.pathname.startsWith('/api/'), route => {
        const url = new URL(route.request().url());
        requests.push(url);
        if (url.pathname === '/api/events/filters') {
            return route.fulfill({ json: { species, cameras: ['birdcam', 'garden'], camera_counts: { birdcam: 12, garden: 8 }, totals: { total: 44, favorites: 3, audio_matched: 2, hidden: 1 } } });
        }
        if (url.pathname === '/api/visits') return route.fulfill({ json: { total: 0, gap_seconds: 60, visits: [] } });
        if (url.pathname === '/api/events/count') return route.fulfill({ json: { count: 1 } });
        if (url.pathname === '/api/events' || url.pathname.endsWith('/labels')) return route.fulfill({ json: [] });
        return route.fulfill({ json: {} });
    });
    await page.goto('/browser-tests/owner-history.html?surface=explorer');
    const toggle = page.locator('[data-explorer-filter-toggle]');
    await expect(page.locator('[data-events-filter-bar]')).toBeVisible();
    if ((page.viewportSize()?.width ?? 1280) < 1024) {
        await expect(toggle).toBeVisible();
        await toggle.click();
    }
    await expect(page.getByRole('button', { name: /^Dunnock.*12$/ })).toBeVisible();
    return requests;
}

for (const viewport of [{ width: 1280, height: 600 }, { width: 390, height: 844 }]) {
    test(`species remain usable after selecting a filter at ${viewport.width}x${viewport.height}`, async ({ page }) => {
        await page.setViewportSize(viewport);
        const requests = await openFilters(page);
        const list = page.locator('[data-explorer-species-list]');
        await expect.poll(() => list.evaluate(node => node.clientHeight)).toBeGreaterThanOrEqual(176);
        await page.getByRole('button', { name: /^Dunnock.*12$/ }).click();
        await expect(page.getByRole('button', { name: /^Dunnock.*12$/ })).toHaveAttribute('aria-pressed', 'true');
        await expect.poll(() => list.evaluate(node => node.clientHeight)).toBeGreaterThanOrEqual(176);
        await page.getByRole('button', { name: /^European Robin.*8$/ }).click();
        await expect(page.getByRole('button', { name: /^European Robin.*8$/ })).toHaveAttribute('aria-pressed', 'true');
        await expect.poll(() => requests.some(url => url.pathname === '/api/visits' && url.searchParams.get('species') === 'Erithacus rubecula')).toBe(true);
        const search = page.getByRole('searchbox', { name: 'Search species' });
        await search.fill('Prunella');
        await expect(list.getByRole('button')).toHaveCount(1);
        await search.fill('Species 24');
        await list.getByRole('button', { name: 'Species 24 1', exact: true }).click();
        await expect(list.getByRole('button')).toHaveAttribute('aria-pressed', 'true');
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    });
}

test('the window is always open, rarer filters fold away and name what is chosen inside them', async ({ page, browserName }) => {
    await page.setViewportSize({ width: 1280, height: 600 });
    await openFilters(page);
    const when = page.locator('[data-explorer-date-facet]');
    const only = page.locator('[data-explorer-only-facet]');
    const cameras = page.locator('[data-explorer-camera-facet]');
    for (const section of [only, cameras]) await expect(section).not.toHaveAttribute('open');
    // The most changed filter sits first and needs no opening.
    await expect(when.getByRole('button', { name: 'Custom', exact: true })).toBeVisible();
    await when.getByRole('button', { name: 'Custom', exact: true }).click();
    await page.getByLabel('Start date').fill('2026-10-01');
    await page.getByLabel('End date').fill('2026-10-04');
    await only.locator('summary').click();
    await page.getByRole('button', { name: 'Favorites 3', exact: true }).click();
    await page.getByRole('button', { name: 'Multiple bird species', exact: true }).click();
    await only.locator('summary').click();
    await expect(only.locator('summary')).toContainText('2 on');
    await cameras.locator('summary').click();
    await page.getByRole('button', { name: 'garden 8', exact: true }).click();
    await cameras.locator('summary').click();
    await expect(cameras.locator('summary')).toContainText('garden');
    const search = page.getByRole('searchbox', { name: 'Search species' });
    await search.scrollIntoViewIfNeeded();
    await search.fill('Robin');
    await search.press('Tab');
    // Safari's system Tab preference can skip buttons; explicitly establish focus there.
    if (browserName === 'webkit') await page.getByRole('button', { name: /^European Robin.*8$/ }).focus();
    await expect(page.getByRole('button', { name: /^European Robin.*8$/ })).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('button', { name: /^European Robin.*8$/ })).toHaveAttribute('aria-pressed', 'true');
    await page.getByRole('button', { name: 'Clear all', exact: true }).click();
    await expect(page.locator('[data-explorer-token]')).toHaveCount(0);
});

test('the species list grows in place inside one scrolling rail', async ({ page, browserName, isMobile }) => {
    test.skip(browserName === 'webkit' && isMobile, 'Mobile WebKit has no mouse wheel; touch access is covered by the filter selection tests.');
    await page.setViewportSize({ width: 1280, height: 600 });
    await openFilters(page);
    const facets = page.locator('[data-explorer-facets]');
    const list = page.locator('[data-explorer-species-list]');
    const more = page.locator('[data-explorer-species-more]');
    // The most recorded species first; the rest wait behind one named control.
    await expect(list.getByRole('button')).toHaveCount(8);
    await expect(more).toHaveText('Show all 26 species');
    await expect(more).toHaveAttribute('aria-expanded', 'false');
    await more.click();
    await expect(list.getByRole('button')).toHaveCount(26);
    await expect(more).toHaveAttribute('aria-expanded', 'true');
    // No scroller inside the scroller: the wheel always moves the rail.
    expect(await list.evaluate(node => node.scrollHeight - node.clientHeight)).toBeLessThanOrEqual(1);
    await list.hover();
    const before = await facets.evaluate(node => node.scrollTop);
    await page.mouse.wheel(0, 600);
    await expect.poll(() => facets.evaluate(node => node.scrollTop)).toBeGreaterThan(before);
    await page.locator('[data-explorer-camera-facet] summary').scrollIntoViewIfNeeded();
    await expect(page.locator('[data-explorer-camera-facet] summary')).toBeInViewport();
});

test('how results are shown is chosen in the filters, explained in words, and kept by Clear all', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    const requests = await openFilters(page);
    const show = page.getByRole('group', { name: 'Show' });
    const visits = show.locator('[data-explorer-show="visits"]');
    const captures = show.locator('[data-explorer-show="captures"]');
    const hint = page.locator('#explorer-show-hint');
    await expect(visits).toHaveAttribute('aria-pressed', 'true');
    await expect(visits).toHaveText('Visits');
    await expect(captures).toHaveText('Captures');
    // The chosen option is explained once, beneath the switch, rather than every option twice.
    await expect(hint).toHaveText("One bird's stay: its captures less than a minute apart.");
    await expect(visits).toHaveAccessibleDescription("One bird's stay: its captures less than a minute apart.");
    // The toolbar no longer carries a second switch for the same choice.
    await expect(page.getByRole('group', { name: 'Group captures' })).toHaveCount(0);

    const before = requests.length;
    await captures.click();
    await expect(captures).toHaveAttribute('aria-pressed', 'true');
    await expect(hint).toHaveText('Every capture on its own.');
    await expect.poll(() => requests.slice(before).some(url => url.pathname === '/api/events')).toBe(true);

    await page.getByRole('button', { name: /^Dunnock.*12$/ }).click();
    await page.getByRole('button', { name: 'Clear all', exact: true }).click();
    await expect(captures).toHaveAttribute('aria-pressed', 'true');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
