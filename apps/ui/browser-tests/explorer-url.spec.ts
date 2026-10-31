import { test, expect, type Page } from '@playwright/test';

// The Explorer keeps its filters in the address, replacing the history entry on each change:
// a reload or a pasted link opens the same view, and Back leaves the Explorer rather than
// stepping through every filter tried.

const species = [
    { value: 'Prunella modularis', display_name: 'Dunnock', common_name: 'Dunnock', scientific_name: 'Prunella modularis', count: 12 },
    { value: 'Erithacus rubecula', display_name: 'European Robin', common_name: 'European Robin', scientific_name: 'Erithacus rubecula', count: 8 }
];

async function mockApi(page: Page): Promise<URL[]> {
    const requests: URL[] = [];
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route(url => url.pathname.startsWith('/api/'), route => {
        const url = new URL(route.request().url());
        requests.push(url);
        if (url.pathname === '/api/events/filters') {
            return route.fulfill({ json: { species, cameras: ['birdcam', 'garden'], camera_counts: { birdcam: 12, garden: 8 }, totals: { total: 44, favorites: 3, audio_matched: 2, hidden: 1 } } });
        }
        if (url.pathname === '/api/visits') return route.fulfill({ json: { total: 60, gap_seconds: 60, visits: [] } });
        if (url.pathname === '/api/events/count') return route.fulfill({ json: { count: 60 } });
        if (url.pathname === '/api/events' || url.pathname.endsWith('/labels')) return route.fulfill({ json: [] });
        return route.fulfill({ json: {} });
    });
    return requests;
}

async function openExplorer(page: Page, query = ''): Promise<URL[]> {
    await page.setViewportSize({ width: 1280, height: 900 });
    const requests = await mockApi(page);
    await page.goto(`/browser-tests/owner-history.html?surface=explorer${query}`);
    await expect(page.getByRole('button', { name: /^Dunnock.*12$/ })).toBeVisible();
    return requests;
}

function lastRead(requests: URL[], path: string): URL | undefined {
    return requests.filter(url => url.pathname === path).at(-1);
}

async function chooseFilters(page: Page): Promise<void> {
    await page.getByRole('button', { name: /^Dunnock.*12$/ }).click();
    const when = page.locator('[data-explorer-date-facet]');
    await when.getByRole('button', { name: 'Custom', exact: true }).click();
    await page.getByLabel('From', { exact: true }).fill('2026-10-01');
    await page.getByLabel('To', { exact: true }).fill('2026-10-28');
    const only = page.locator('[data-explorer-only-facet]');
    await only.locator('summary').click();
    await page.getByRole('button', { name: 'Favorites 3', exact: true }).click();
    await page.locator('[data-explorer-show="captures"]').click();
}

test('a reload keeps the chosen filters and asks the API for them again', async ({ page }) => {
    const requests = await openExplorer(page);
    const entries = await page.evaluate(() => history.length);
    await chooseFilters(page);

    await expect.poll(() => new URL(page.url()).searchParams.get('end')).toBe('2026-10-28');
    const address = new URL(page.url()).searchParams;
    expect(address.get('species')).toBe('Prunella modularis');
    expect(address.get('date')).toBe('custom');
    expect(address.get('start')).toBe('2026-10-01');
    expect(address.get('favorites')).toBe('1');
    expect(address.get('show')).toBe('captures');
    // The fixture's own flags are left as they were.
    expect(address.get('surface')).toBe('explorer');
    // Each change replaced the entry; none was added.
    expect(await page.evaluate(() => history.length)).toBe(entries);

    requests.length = 0;
    await page.reload();
    await expect(page.getByRole('button', { name: /^Dunnock.*12$/ })).toHaveAttribute('aria-pressed', 'true');
    await expect(page.getByLabel('From', { exact: true })).toHaveValue('2026-10-01');
    await expect(page.getByLabel('To', { exact: true })).toHaveValue('2026-10-28');
    await expect(page.locator('[data-explorer-show="captures"]')).toHaveAttribute('aria-pressed', 'true');
    await expect(page.locator('[data-explorer-token]').filter({ hasText: /1 Oct( 2026)? to 28 Oct( 2026)?/ })).toBeVisible();
    await expect.poll(() => lastRead(requests, '/api/events')?.searchParams.get('species')).toBe('Prunella modularis');
    const read = lastRead(requests, '/api/events');
    expect(read?.searchParams.get('start_date')).toBe('2026-10-01');
    expect(read?.searchParams.get('end_date')).toBe('2026-10-28');
    expect(read?.searchParams.get('favorites')).toBe('true');
});

test('Clear all takes the filters out of the address but keeps how results are shown', async ({ page }) => {
    await openExplorer(page);
    await chooseFilters(page);
    await expect.poll(() => new URL(page.url()).searchParams.has('species')).toBe(true);
    await page.locator('[data-explorer-clear-all]').click();
    await expect.poll(() => new URL(page.url()).search).toBe('?surface=explorer&show=captures');
});

test('Back leaves the Explorer for where it was opened from, and Forward returns with the filters', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    const requests = await mockApi(page);
    await page.goto('/browser-tests/owner-history.html?surface=species');
    await page.goto('/browser-tests/owner-history.html?surface=explorer');
    await expect(page.getByRole('button', { name: /^Dunnock.*12$/ })).toBeVisible();
    await page.getByRole('button', { name: /^Dunnock.*12$/ }).click();
    await page.locator('[data-explorer-date-facet]').getByRole('button', { name: 'Week', exact: true }).click();
    await expect.poll(() => new URL(page.url()).searchParams.get('date')).toBe('week');

    await page.goBack();
    expect(new URL(page.url()).searchParams.get('surface')).toBe('species');

    requests.length = 0;
    await page.goForward();
    await expect(page.getByRole('button', { name: /^Dunnock.*12$/ })).toHaveAttribute('aria-pressed', 'true');
    await expect(page.locator('[data-explorer-date-facet]').getByRole('button', { name: 'Week', exact: true })).toHaveAttribute('aria-pressed', 'true');
    expect(new URL(page.url()).searchParams.get('species')).toBe('Prunella modularis');
});

test('another history entry for the Explorer is read again when Back reaches it', async ({ page }) => {
    // The app links into the Explorer with filters while it may already be open.
    const requests = await openExplorer(page, '&species=Prunella%20modularis');
    await expect(page.getByRole('button', { name: /^Dunnock.*12$/ })).toHaveAttribute('aria-pressed', 'true');
    await page.evaluate(() => {
        history.pushState(null, '', `${location.pathname}?surface=explorer&species=Erithacus%20rubecula`);
        window.dispatchEvent(new PopStateEvent('popstate'));
    });
    await expect(page.getByRole('button', { name: /^European Robin.*8$/ })).toHaveAttribute('aria-pressed', 'true');
    await expect.poll(() => lastRead(requests, '/api/visits')?.searchParams.get('species')).toBe('Erithacus rubecula');

    await page.evaluate(() => history.back());
    await expect(page.getByRole('button', { name: /^Dunnock.*12$/ })).toHaveAttribute('aria-pressed', 'true');
    await expect.poll(() => lastRead(requests, '/api/visits')?.searchParams.get('species')).toBe('Prunella modularis');
});

test('a pasted link opens with its filters and ignores values it cannot trust', async ({ page }) => {
    const requests = await openExplorer(page, '&species=Erithacus%20rubecula&camera=garden&date=week&start=2026-99-01&page=2&show=everything&favorites=maybe');
    await expect(page.getByRole('button', { name: /^European Robin.*8$/ })).toHaveAttribute('aria-pressed', 'true');
    await expect(page.locator('[data-explorer-camera-facet] summary')).toContainText('garden');
    await expect(page.locator('[data-explorer-date-facet]').getByRole('button', { name: 'Week', exact: true })).toHaveAttribute('aria-pressed', 'true');
    // Visits stay grouped: "everything" is not a way to show results.
    await expect(page.locator('[data-explorer-show="visits"]')).toHaveAttribute('aria-pressed', 'true');
    await expect.poll(() => lastRead(requests, '/api/visits')?.searchParams.get('offset')).toBe('24');
    const read = lastRead(requests, '/api/visits');
    expect(read?.searchParams.get('species')).toBe('Erithacus rubecula');
    expect(read?.searchParams.get('camera')).toBe('garden');
    expect(read?.searchParams.has('favorites')).toBe(false);

    // The next change states only what is applied.
    await page.locator('[data-explorer-only-facet] summary').click();
    await page.getByRole('button', { name: 'Favorites 3', exact: true }).click();
    await expect.poll(() => new URL(page.url()).searchParams.get('favorites')).toBe('1');
    const address = new URL(page.url()).searchParams;
    expect(address.has('start')).toBe(false);
    expect(address.get('show')).toBeNull();
    expect(address.get('page')).toBeNull();
});

test('a link cannot give a visitor the owner-only filters', async ({ page }) => {
    const requests = await openExplorer(page, '&guest=1&hidden=1&multiple=1&review=pending&species=Prunella%20modularis');
    await expect(page.getByRole('button', { name: /^Dunnock.*12$/ })).toHaveAttribute('aria-pressed', 'true');
    await expect.poll(() => lastRead(requests, '/api/visits')?.searchParams.get('species')).toBe('Prunella modularis');
    const read = lastRead(requests, '/api/visits');
    expect(read?.searchParams.has('only_hidden')).toBe(false);
    expect(read?.searchParams.has('multiple_species_only')).toBe(false);
});
