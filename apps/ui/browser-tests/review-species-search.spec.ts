import { test, expect, type Page } from '@playwright/test';

const goldcrest = { id: 'Regulus regulus', display_name: 'Regulus regulus', scientific_name: 'Regulus regulus', common_name: 'Goldcrest' };
const robin = { id: 'Erithacus rubecula', display_name: 'Erithacus rubecula', scientific_name: 'Erithacus rubecula', common_name: 'European Robin' };

function gate() {
    let release: () => void = () => undefined;
    const promise = new Promise<void>(resolve => { release = resolve; });
    return { promise, release };
}

async function open(page: Page, response?: (query: string) => Promise<{ status?: number; results: typeof goldcrest[] }>) {
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route(url => url.pathname.startsWith('/api/'), async route => {
        const url = new URL(route.request().url());
        if (url.pathname === '/api/species/search') {
            const query = url.searchParams.get('q') ?? '';
            const reply: { status?: number; results: typeof goldcrest[] } = response ? await response(query) : { results: query && !/goldcrest|regulus/i.test(query) ? [] : [goldcrest, robin] };
            return route.fulfill({ status: reply.status ?? 200, json: reply.results }).catch(() => undefined);
        }
        if (url.pathname.endsWith('.jpg')) return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="240"><rect width="320" height="240" fill="#334155"/></svg>' });
        if (url.pathname.endsWith('/snapshot/candidates')) return route.fulfill({ json: { candidates: [], birds: [] } });
        return route.fulfill({ json: [] });
    });
    await page.goto('/browser-tests/review-media.html?surface=queue&labels=scientific');
    await expect(page.getByRole('searchbox', { name: 'Search species' })).toBeVisible();
}

for (const query of ['Goldcrest', 'Regulus regulus']) {
    test(`attention search finds ${query} and identifies the canonical species`, async ({ page }) => {
        await open(page);
        await page.getByRole('searchbox', { name: 'Search species' }).fill(query);
        const choice = page.getByRole('button', { name: 'Goldcrest Regulus regulus Identify', exact: true });
        await expect(choice).toBeVisible();
        await choice.click();
        await expect(page.locator('[data-fixture-events]')).toHaveText('identify tit Regulus regulus');
    });
}

test('latest query wins when an older search answers late', async ({ page }) => {
    const held = gate();
    await open(page, async query => {
        if (query === 'Goldcrest') { await held.promise; return { results: [goldcrest] }; }
        return { results: [robin] };
    });
    const search = page.getByRole('searchbox', { name: 'Search species' });
    const started = page.waitForRequest(r => new URL(r.url()).searchParams.get('q') === 'Goldcrest');
    await search.fill('Goldcrest'); await started;
    await search.fill('Robin');
    await expect(page.getByRole('button', { name: 'European Robin Erithacus rubecula Identify' })).toBeVisible();
    held.release();
    await page.waitForTimeout(150);
    await expect(page.getByRole('button', { name: 'Goldcrest Regulus regulus Identify' })).toHaveCount(0);
});

test('clearing or skipping cannot restore an outstanding search', async ({ page }) => {
    const held = gate();
    await open(page, async query => {
        if (query === 'Goldcrest') { await held.promise; return { results: [goldcrest] }; }
        return { results: [robin] };
    });
    const search = page.getByRole('searchbox', { name: 'Search species' });
    const started = page.waitForRequest(r => new URL(r.url()).searchParams.get('q') === 'Goldcrest');
    await search.fill('Goldcrest'); await started;
    await search.fill('');
    await page.getByRole('button', { name: 'Skip for now', exact: true }).click();
    held.release();
    await expect(search).toHaveValue('');
    await page.waitForTimeout(150);
    await expect(page.getByRole('button', { name: 'Goldcrest Regulus regulus Identify' })).toHaveCount(0);
});

test('pending search does not claim there are no matches', async ({ page }) => {
    const held = gate();
    await open(page, async query => { if (query) await held.promise; return { results: [goldcrest] }; });
    const started = page.waitForRequest(r => new URL(r.url()).searchParams.get('q') === 'Goldcrest');
    await page.getByRole('searchbox', { name: 'Search species' }).fill('Goldcrest'); await started;
    await expect(page.getByRole('dialog')).not.toContainText('No species matches');
    await expect(page.getByRole('dialog').getByText('Loading…', { exact: true })).toBeVisible();
    held.release();
    await expect(page.getByRole('button', { name: 'Goldcrest Regulus regulus Identify' })).toBeVisible();
});

test('failed search is distinguished from a genuine empty result', async ({ page }) => {
    await open(page, async query => ({ status: query ? 503 : 200, results: [] }));
    const completed = page.waitForResponse(r => new URL(r.url()).searchParams.get('q') === 'Goldcrest');
    await page.getByRole('searchbox', { name: 'Search species' }).fill('Goldcrest'); await completed;
    await expect(page.getByRole('dialog')).not.toContainText('No species matches');
    await expect(page.getByRole('dialog')).toContainText(/couldn.t.*search|search.*unavailable|search.*failed/i);
});

test('the displayed current species is still searchable by common name', async ({ page }) => {
    const blueTit = { id: 'Cyanistes caeruleus', display_name: 'Cyanistes caeruleus', scientific_name: 'Cyanistes caeruleus', common_name: 'Eurasian Blue Tit' };
    await open(page, async query => ({ results: query ? [blueTit] : [goldcrest] }));
    await page.getByRole('searchbox', { name: 'Search species' }).fill('Eurasian Blue Tit');
    await expect(page.getByRole('button', { name: 'Eurasian Blue Tit Cyanistes caeruleus Identify' })).toBeVisible();
});

test('a completed empty search offers an honest no-match state', async ({ page }) => {
    await open(page, async () => ({ results: [] }));
    await page.getByRole('searchbox', { name: 'Search species' }).fill('NoSuchSpecies');
    await expect(page.getByRole('dialog')).toContainText('No species matches that');
});

test('rapid typing does not request a taxonomy lookup for every keystroke', async ({ page }) => {
    const queries: string[] = [];
    await open(page, async query => { if (query) queries.push(query); return { results: [goldcrest] }; });
    const search = page.getByRole('searchbox', { name: 'Search species' });
    await search.fill('G'); await search.fill('Go'); await search.fill('Goldcrest');
    await expect(page.getByRole('button', { name: 'Goldcrest Regulus regulus Identify' })).toBeVisible();
    expect(queries).toEqual(['Goldcrest']);
});

test('closing with a search outstanding cannot reopen the queue or identify a bird', async ({ page }) => {
    const held = gate();
    await open(page, async query => { if (query) await held.promise; return { results: [goldcrest] }; });
    const started = page.waitForRequest(r => new URL(r.url()).searchParams.get('q') === 'Goldcrest');
    await page.getByRole('searchbox', { name: 'Search species' }).fill('Goldcrest'); await started;
    await page.getByRole('button', { name: 'Close', exact: true }).click(); held.release();
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await expect(page.locator('[data-fixture-events]')).toHaveText('');
});
