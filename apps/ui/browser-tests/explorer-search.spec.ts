import { test, expect, type Page, type Route } from '@playwright/test';

// The Explorer's one search box: species, groups, cameras, dates and record ids. The spec
// supplies the HTTP boundary, so what is asserted is what the page asks for and shows.

const environment = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env ?? {};
const shots = environment.EXPLORER_SHOTS;

const greatTit = { taxon_id: 101, rank: 'species', scientific_name: 'Parus major', name: 'Great Tit', bird_species: 1, bird_detections: 12, garden_species: 0, garden_captures: 0 };
const bluetit = { taxon_id: 102, rank: 'species', scientific_name: 'Cyanistes caeruleus', name: 'Eurasian Blue Tit', bird_species: 1, bird_detections: 7, garden_species: 0, garden_captures: 0 };
const tits = { taxon_id: 50, rank: 'family', scientific_name: 'Paridae', name: 'Tits', bird_species: 2, bird_detections: 19, garden_species: 0, garden_captures: 0 };
const carnivores = { taxon_id: 400, rank: 'order', scientific_name: 'Carnivora', name: 'Carnivorans', bird_species: 0, bird_detections: 0, garden_species: 1, garden_captures: 3 };
const dunnock = { value: 'Prunella modularis', display_name: 'Dunnock', common_name: 'Dunnock', scientific_name: 'Prunella modularis', count: 9 };
const parus = { value: 'Parus major', display_name: 'Great Tit', common_name: 'Great Tit', scientific_name: 'Parus major', count: 12 };

const FRIGATE_ID = '1793624285.74056-6j3htl';
const GARDEN_ID = 'f'.repeat(32);

interface Mock {
    requests: URL[];
    searchQueries: string[];
    /** Answers one search; a test replaces it to delay or fail. */
    answer: (query: string, route: Route) => Promise<void> | void;
}

const TAXA: Record<string, unknown[]> = {
    tit: [tits, greatTit, bluetit],
    parus: [greatTit],
    fox: [carnivores],
    carni: [carnivores]
};

async function mockApi(page: Page, options: { cameras?: string[]; record?: unknown } = {}): Promise<Mock> {
    const cameras = options.cameras ?? ['birdcam', 'feeder'];
    const mock: Mock = {
        requests: [],
        searchQueries: [],
        answer: (query, route) => {
            const key = Object.keys(TAXA).find(word => query.toLowerCase().includes(word));
            const record = query === FRIGATE_ID || query === GARDEN_ID ? options.record ?? null : null;
            return route.fulfill({ json: { taxa: key ? TAXA[key] : [], truncated: false, record } });
        }
    };
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route(url => url.pathname.startsWith('/api/'), route => {
        const url = new URL(route.request().url());
        mock.requests.push(url);
        if (url.pathname === '/api/explorer/search') {
            const query = url.searchParams.get('q') ?? '';
            mock.searchQueries.push(query);
            return mock.answer(query, route);
        }
        if (url.pathname === '/api/events/filters') {
            return route.fulfill({ json: { species: [dunnock, parus], cameras, camera_counts: Object.fromEntries(cameras.map((camera, index) => [camera, 10 - index])), totals: { total: 21, favorites: 0, audio_matched: 0, hidden: 0 } } });
        }
        if (url.pathname.startsWith('/api/taxonomy/') && url.pathname.endsWith('/lineage')) {
            const id = Number(url.pathname.split('/')[3]);
            const taxon = [tits, carnivores].find(item => item.taxon_id === id);
            return taxon
                ? route.fulfill({ json: { lineage: [{ taxon_id: taxon.taxon_id, rank: taxon.rank, scientific_name: taxon.scientific_name, name: taxon.name }] } })
                : route.fulfill({ status: 404, json: { detail: 'Not found' } });
        }
        if (url.pathname === '/api/visits') return route.fulfill({ json: { total: 0, gap_seconds: 60, visits: [] } });
        if (url.pathname === '/api/garden/visits') return route.fulfill({ json: { visits: [], total: 0, capture_total: 0, limit: 25, offset: 0 } });
        if (url.pathname === '/api/events/count') return route.fulfill({ json: { count: 0 } });
        if (url.pathname === '/api/events' && url.searchParams.get('event_id') === FRIGATE_ID) {
            return route.fulfill({ json: [{ frigate_event: FRIGATE_ID, display_name: 'Parus major', scientific_name: 'Parus major', common_name: 'Great Tit', camera_name: 'birdcam', detection_time: new Date().toISOString(), score: 0.93, has_clip: false, has_snapshot: false }] });
        }
        if (url.pathname === '/api/events' || url.pathname.endsWith('/labels')) return route.fulfill({ json: [] });
        return route.fulfill({ json: {} });
    });
    return mock;
}

async function openExplorer(page: Page, query = '', options: Parameters<typeof mockApi>[1] = {}): Promise<Mock> {
    const mock = await mockApi(page, options);
    await page.goto(`/browser-tests/owner-history.html?surface=explorer${query}`);
    await expect(page.locator('[data-explorer-search]')).toBeVisible();
    return mock;
}

const searchBox = (page: Page) => page.getByRole('combobox', { name: 'Search the Explorer' });
const option = (page: Page, name: string | RegExp) => page.getByRole('option', { name });
const lastRead = (mock: Mock, path: string) => mock.requests.filter(url => url.pathname === path).at(-1);
const status = (page: Page) => page.locator('#explorer-search-status');

test('typing finds species and groups in groups, and Enter on the active result applies it', async ({ page }) => {
    const mock = await openExplorer(page);
    const box = searchBox(page);
    await box.fill('tit');
    await expect(box).toHaveAttribute('aria-expanded', 'true');
    await expect(page.getByRole('listbox', { name: 'Search the Explorer' })).toBeVisible();
    await expect(option(page, /^Tits/)).toBeVisible();
    await expect(option(page, /^Tits/)).toContainText('Paridae');
    await expect(option(page, /^Tits/)).toContainText('Family');
    await expect(page.getByRole('group', { name: 'Species and groups' })).toBeVisible();
    await expect(status(page)).toHaveText('3 results');
    if (shots) await page.screenshot({ path: `${shots}/explorer-search-results-${test.info().project.name}.png` });

    // Focus stays in the box; the arrows move the active result for a screen reader.
    await expect(box).toHaveAttribute('aria-activedescendant', /explorer-search-option-0/);
    await expect(option(page, /^Tits/)).toHaveAttribute('aria-selected', 'true');
    await box.press('ArrowDown');
    await expect(option(page, /^Great Tit/)).toHaveAttribute('aria-selected', 'true');
    await box.press('ArrowDown');
    await box.press('ArrowUp');
    await box.press('ArrowUp');
    await expect(option(page, /^Tits/)).toHaveAttribute('aria-selected', 'true');
    await box.press('Enter');

    // A group narrows through the existing filters, shows as a token and lives in the address.
    await expect(box).toHaveValue('');
    await expect(box).toBeFocused();
    await expect.poll(() => lastRead(mock, '/api/visits')?.searchParams.get('taxon')).toBe('50');
    expect(lastRead(mock, '/api/visits')?.searchParams.has('species')).toBe(false);
    await expect.poll(() => new URL(page.url()).searchParams.get('taxon')).toBe('50');
    await expect(page.locator('[data-explorer-token]').filter({ hasText: 'Family: Tits' })).toBeVisible();
    if (shots) await page.screenshot({ path: `${shots}/explorer-search-token-${test.info().project.name}.png` });
});

test('a species the rail lists is applied as its own species filter, replacing a chosen group', async ({ page }) => {
    const mock = await openExplorer(page, '&taxon=50');
    await expect(page.locator('[data-explorer-token]').filter({ hasText: 'Family: Tits' })).toBeVisible();
    const box = searchBox(page);
    await box.fill('parus');
    await option(page, /^Great Tit/).click();
    await expect.poll(() => lastRead(mock, '/api/visits')?.searchParams.get('species')).toBe('Parus major');
    expect(lastRead(mock, '/api/visits')?.searchParams.has('taxon')).toBe(false);
    await expect.poll(() => new URL(page.url()).searchParams.has('taxon')).toBe(false);
    await expect(page.locator('[data-explorer-token]').filter({ hasText: 'Family: Tits' })).toHaveCount(0);
});

test('a camera is matched on the page, with no wait, and the species facet answers while the server is down', async ({ page }) => {
    const mock = await openExplorer(page);
    mock.answer = (_query, route) => route.fulfill({ status: 500, json: { detail: 'boom' } });
    const box = searchBox(page);
    await box.fill('feed');
    await expect(option(page, /^feeder/)).toBeVisible();
    await expect(status(page)).toContainText('could not be searched just now');
    await option(page, /^feeder/).click();
    await expect.poll(() => lastRead(mock, '/api/visits')?.searchParams.get('camera')).toBe('feeder');
    await expect.poll(() => new URL(page.url()).searchParams.get('camera')).toBe('feeder');

    // Species the page already lists are still found when the catalogue cannot be asked.
    await box.fill('dunn');
    await expect(option(page, /^Dunnock/)).toBeVisible();
});

test('a server failure with nothing else to offer says so and how to recover', async ({ page }) => {
    const mock = await openExplorer(page);
    mock.answer = (_query, route) => route.fulfill({ status: 500, json: { detail: 'boom' } });
    await searchBox(page).fill('zzz');
    await expect(page.locator('[data-explorer-search-status]')).toHaveText('Species and records could not be searched just now. Try again in a moment.');
    await expect(page.getByRole('option')).toHaveCount(0);
    mock.answer = (_query, route) => route.fulfill({ json: { taxa: [], truncated: false, record: null } });
    await searchBox(page).fill('zzzz');
    await expect(page.locator('[data-explorer-search-status]')).toHaveText('No match for “zzzz”. Try a scientific name or a camera.');
    if (shots) await page.screenshot({ path: `${shots}/explorer-search-empty-${test.info().project.name}.png` });
});

test('a late answer for older text never replaces the answer for what is typed now', async ({ page }) => {
    const mock = await openExplorer(page);
    const releaseOld: Array<() => void> = [];
    mock.answer = async (query, route) => {
        if (query === 'tit') {
            await new Promise<void>(resolve => releaseOld.push(resolve));
            return route.fulfill({ json: { taxa: [tits], truncated: false, record: null } }).catch(() => undefined);
        }
        return route.fulfill({ json: { taxa: [carnivores], truncated: false, record: null } });
    };
    const box = searchBox(page);
    await box.fill('tit');
    await expect(status(page)).toHaveText('Searching…');
    await expect.poll(() => mock.searchQueries.includes('tit')).toBe(true);
    await box.fill('fox');
    await expect(option(page, /^Carnivorans/)).toBeVisible();
    releaseOld.forEach(release => release());
    await page.waitForTimeout(150);
    await expect(option(page, /^Tits/)).toHaveCount(0);
    await expect(option(page, /^Carnivorans/)).toBeVisible();
    await expect(status(page)).toHaveText('1 result');
});

test('typing quickly asks once for the final text, and one letter asks nothing', async ({ page }) => {
    const mock = await openExplorer(page);
    const box = searchBox(page);
    await box.pressSequentially('par', { delay: 20 });
    await expect(option(page, /^Great Tit/)).toBeVisible();
    await expect.poll(() => mock.searchQueries).toEqual(['par']);
    await box.fill('p');
    await page.waitForTimeout(400);
    expect(mock.searchQueries).toEqual(['par']);
});

test('Escape clears the box and closes the results, and "/" focuses the box from the page', async ({ page }) => {
    await openExplorer(page);
    const box = searchBox(page);
    await page.locator('body').click({ position: { x: 5, y: 5 } });
    await page.keyboard.press('/');
    await expect(box).toBeFocused();
    await box.fill('tit');
    await expect(option(page, /^Tits/)).toBeVisible();
    await box.press('Escape');
    await expect(box).toHaveValue('');
    await expect(box).toHaveAttribute('aria-expanded', 'false');
    // Typing a slash into the box types it.
    await box.fill('a/b');
    await expect(box).toHaveValue('a/b');
});

test('a Frigate id opens its record, asking for hidden ones only when the search says it is hidden', async ({ page }) => {
    const record = { kind: 'detection', id: FRIGATE_ID, observed_at: '2026-11-02T08:00:00Z', display_name: 'Great Tit', scientific_name: 'Parus major', common_name: 'Great Tit', camera: 'birdcam', hidden: false };
    const mock = await openExplorer(page, '', { record });
    const box = searchBox(page);
    await box.fill(FRIGATE_ID);
    await expect(option(page, /Great Tit/)).toContainText('Open record');
    await expect(option(page, /Great Tit/)).toContainText('birdcam');
    await box.press('Enter');
    await expect(page.getByRole('dialog')).toBeVisible();
    const opened = lastRead(mock, '/api/events');
    expect(opened?.searchParams.get('event_id')).toBe(FRIGATE_ID);
    expect(opened?.searchParams.has('include_hidden')).toBe(false);
});

test('an id nobody the reader may see has is answered in words, not an error', async ({ page }) => {
    await openExplorer(page, '', { record: null });
    await searchBox(page).fill(FRIGATE_ID);
    await expect(page.locator('[data-explorer-search-status]')).toHaveText('No record you can open has this ID.');
    await expect(page.getByRole('option')).toHaveCount(0);
});

test('a day typed in words filters to that day', async ({ page }) => {
    const mock = await openExplorer(page);
    await searchBox(page).fill('yesterday');
    await option(page, /^Show /).click();
    await expect.poll(() => lastRead(mock, '/api/visits')?.searchParams.get('start_date')).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    const read = lastRead(mock, '/api/visits')?.searchParams;
    expect(read?.get('start_date')).toBe(read?.get('end_date'));
    await expect.poll(() => new URL(page.url()).searchParams.get('date')).toBe('custom');
});

test('a Garden-only group brings Garden into view, and leaving it for Birds drops the group instead of showing an empty page', async ({ page }) => {
    const mock = await openExplorer(page, '&garden=1&visitors=birds');
    await searchBox(page).fill('fox');
    await option(page, /^Carnivorans/).click();
    await expect.poll(() => lastRead(mock, '/api/garden/visits')?.searchParams.get('taxon')).toBe('400');
    await expect.poll(() => new URL(page.url()).searchParams.get('visitors')).toBe('garden');
    await expect(page.locator('[data-explorer-token]').filter({ hasText: 'Order: Carnivorans' })).toBeVisible();

    const birds = page.locator('[data-explorer-subjects-option="birds"]');
    if (!(await birds.isVisible())) await page.locator('[data-explorer-filter-toggle]').click();
    await birds.click();
    await expect(page.locator('[data-explorer-token]').filter({ hasText: 'Order: Carnivorans' })).toHaveCount(0);
    await expect(page.getByText('The group filter was removed because it has no visitors in this view.')).toBeVisible();
    await expect.poll(() => new URL(page.url()).searchParams.has('taxon')).toBe(false);
});

test('a link naming only a group is named from the catalogue, and a group the catalogue lacks stays removable', async ({ page }) => {
    const mock = await openExplorer(page, '&taxon=50');
    await expect(page.locator('[data-explorer-token]').filter({ hasText: 'Family: Tits' })).toBeVisible();
    expect(lastRead(mock, '/api/visits')?.searchParams.get('taxon')).toBe('50');
    await page.goto('/browser-tests/owner-history.html?surface=explorer&taxon=999');
    const unnamed = page.locator('[data-explorer-token]').filter({ hasText: 'Chosen group of species' });
    await expect(unnamed).toBeVisible();
    await unnamed.click();
    await expect(unnamed).toHaveCount(0);
    await expect.poll(() => new URL(page.url()).searchParams.has('taxon')).toBe(false);
});

test('a visitor is offered no camera the owner does not share, and search never loads media', async ({ page }) => {
    const mock = await openExplorer(page, '&guest=1', { cameras: [] });
    const box = searchBox(page);
    await box.fill('birdcam');
    await expect(page.locator('[data-explorer-search-status]')).toContainText('No match for “birdcam”');
    await expect(page.getByRole('option', { name: /birdcam/ })).toHaveCount(0);
    await box.fill('tit');
    await expect(option(page, /^Tits/)).toBeVisible();
    await option(page, /^Tits/).click();
    await expect.poll(() => lastRead(mock, '/api/visits')?.searchParams.get('taxon')).toBe('50');
    // Results are text; nothing the search touches requests a snapshot, clip, thumbnail or spectrogram.
    const media = mock.requests.filter(url => /\/(snapshot|thumbnail|clip|crop|spectrogram|latest)\b|\.(jpg|mp4|webp)$/.test(url.pathname));
    expect(media).toEqual([]);
});

test('results fit a phone and stay inside the page', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openExplorer(page);
    await searchBox(page).fill('tit');
    await expect(option(page, /^Tits/)).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    const panel = page.locator('[data-explorer-search-panel]');
    const box = await panel.boundingBox();
    expect(box?.x).toBeGreaterThanOrEqual(0);
    expect((box?.x ?? 0) + (box?.width ?? 0)).toBeLessThanOrEqual(390);
});

test('the results stay readable in the dark theme', async ({ page }) => {
    await openExplorer(page, '&theme=dark');
    await searchBox(page).fill('tit');
    await expect(option(page, /^Tits/)).toBeVisible();
    if (shots) await page.screenshot({ path: `${shots}/explorer-search-dark-${test.info().project.name}.png` });
    await option(page, /^Tits/).click();
    await expect(page.locator('[data-explorer-token]').filter({ hasText: 'Family: Tits' })).toBeVisible();
    if (shots) await page.screenshot({ path: `${shots}/explorer-search-dark-token-${test.info().project.name}.png` });
});
