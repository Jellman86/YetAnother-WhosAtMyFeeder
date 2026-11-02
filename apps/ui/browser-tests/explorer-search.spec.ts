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
const GARDEN_ID_NEWER = 'e'.repeat(32);

const gardenSearchRecord = (id: string, name: string) => ({ kind: 'garden', id, observed_at: '2026-11-02T08:00:00Z', display_name: name, scientific_name: null, common_name: name, camera: 'patio', hidden: false });

function gardenCapture(id: string, name: string) {
    return {
        id, camera: 'patio', frigate_label: 'cat', observed_at: '2026-11-02T08:00:00Z', status: 'confirmed', reviewed_at: null,
        snapshot_url: null, crop_url: null, source_kind: 'frigate_event', motion_source: null, automatic_check: null, automatic_check_overridden: false,
        review_token: 'a'.repeat(64), owner_identification: null,
        identification: { outcome: 'suggestion', reason: 'confident', review: 'accepted', automatic: false, name, rank: 'species', score: 0.93, country: 'GBR', variant: '4.0.3b', provider: 'cpu', devices: ['cpu'], output_index: 1, input_kind: 'whole_image', box_xywh: null, frame_size: [160, 120], identified_at: '2026-11-02T08:00:00Z' }
    };
}

const DETECTION = { frigate_event: FRIGATE_ID, display_name: 'Parus major', scientific_name: 'Parus major', common_name: 'Great Tit', camera_name: 'birdcam', detection_time: new Date().toISOString(), score: 0.93, has_clip: false, has_snapshot: false };

interface Mock {
    requests: URL[];
    searchQueries: string[];
    /** Answers one search; a test replaces it to delay or fail. */
    answer: (query: string, route: Route) => Promise<void> | void;
    /** Ids of the Garden captures read to open a record, and answers each; a test replaces it to hold one back. */
    captureReads: string[];
    answerCapture: (id: string, route: Route) => Promise<void> | void;
    /** Answers the read that opens a searched detection. */
    answerEvent: (route: Route) => Promise<void> | void;
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
        captureReads: [],
        answerCapture: (id, route) => route.fulfill({ json: gardenCapture(id, 'Red fox') }),
        answerEvent: route => route.fulfill({ json: [DETECTION] }),
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
        if (url.pathname.startsWith('/api/garden/captures/')) {
            const id = url.pathname.split('/')[4];
            mock.captureReads.push(id);
            return mock.answerCapture(id, route);
        }
        if (url.pathname === '/api/events' && url.searchParams.get('event_id') === FRIGATE_ID) return mock.answerEvent(route);
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

// Opening a record is a read that can outlive the choice that began it, so only the newest choice may open anything.
const staleToast = (page: Page) => page.getByText('no longer available, or is not shared here');

/** Holds each named Garden capture's read until the test releases it, so the order of the answers is the test's. */
function holdCaptures(mock: Mock, ids: string[]): Record<string, () => void> {
    const release: Record<string, () => void> = {};
    const gates = new Map(ids.map(id => [id, new Promise<void>(resolve => { release[id] = resolve; })]));
    mock.answerCapture = async (id, route) => {
        await gates.get(id);
        const name = id === GARDEN_ID ? 'Red fox' : 'Hedgehog';
        await route.fulfill({ json: gardenCapture(id, name) }).catch(() => undefined);
    };
    return release;
}

async function chooseRecord(page: Page, id: string): Promise<void> {
    const box = searchBox(page);
    await box.fill(id);
    await expect(option(page, /Open record/)).toBeVisible();
    await box.press('Enter');
}

function searchesRecords(mock: Mock, records: Record<string, unknown>): void {
    mock.answer = (query, route) => route.fulfill({ json: { taxa: query.toLowerCase().includes('tit') ? [tits] : [], truncated: false, record: records[query] ?? null } });
}

test('a slow Garden record never replaces the newer one chosen after it, whichever answers last', async ({ page }) => {
    const mock = await openExplorer(page, '&garden=1');
    searchesRecords(mock, { [GARDEN_ID]: gardenSearchRecord(GARDEN_ID, 'Red fox'), [GARDEN_ID_NEWER]: gardenSearchRecord(GARDEN_ID_NEWER, 'Hedgehog') });
    const release = holdCaptures(mock, [GARDEN_ID, GARDEN_ID_NEWER]);
    const cancelled: string[] = [];
    page.on('requestfailed', request => cancelled.push(request.url()));

    await chooseRecord(page, GARDEN_ID);
    await expect.poll(() => mock.captureReads).toEqual([GARDEN_ID]);
    await chooseRecord(page, GARDEN_ID_NEWER);
    await expect.poll(() => mock.captureReads).toEqual([GARDEN_ID, GARDEN_ID_NEWER]);
    release[GARDEN_ID_NEWER]();
    await expect(page.locator('[data-garden-capture-modal]')).toContainText('Hedgehog');
    release[GARDEN_ID]();
    await page.waitForTimeout(250);
    await expect(page.locator('[data-garden-capture-modal]')).toHaveCount(1);
    await expect(page.locator('[data-garden-capture-modal]')).toContainText('Hedgehog');
    await expect(page.locator('[data-garden-capture-modal]')).not.toContainText('Red fox');
    await expect(staleToast(page)).toHaveCount(0);
    expect(cancelled.some(url => url.includes(`/garden/captures/${GARDEN_ID}`))).toBe(true);
});

test('an older Garden record that fails after a newer choice says nothing', async ({ page }) => {
    const mock = await openExplorer(page, '&garden=1');
    searchesRecords(mock, { [GARDEN_ID]: gardenSearchRecord(GARDEN_ID, 'Red fox'), [GARDEN_ID_NEWER]: gardenSearchRecord(GARDEN_ID_NEWER, 'Hedgehog') });
    let failOld: () => void = () => undefined;
    const oldFails = new Promise<void>(resolve => { failOld = resolve; });
    mock.answerCapture = async (id, route) => {
        if (id === GARDEN_ID) {
            await oldFails;
            await route.fulfill({ status: 404, json: { detail: 'Garden capture not found' } }).catch(() => undefined);
            return;
        }
        await route.fulfill({ json: gardenCapture(id, 'Hedgehog') });
    };
    await chooseRecord(page, GARDEN_ID);
    await expect.poll(() => mock.captureReads).toEqual([GARDEN_ID]);
    await chooseRecord(page, GARDEN_ID_NEWER);
    await expect(page.locator('[data-garden-capture-modal]')).toContainText('Hedgehog');
    failOld();
    await page.waitForTimeout(250);
    await expect(staleToast(page)).toHaveCount(0);
    await expect(page.locator('[data-garden-capture-modal]')).toContainText('Hedgehog');
});

test('a detection chosen after a slow Garden record is the only record that opens', async ({ page }) => {
    const mock = await openExplorer(page, '&garden=1', { record: null });
    searchesRecords(mock, { [GARDEN_ID]: gardenSearchRecord(GARDEN_ID, 'Red fox'), [FRIGATE_ID]: { kind: 'detection', id: FRIGATE_ID, observed_at: '2026-11-02T08:00:00Z', display_name: 'Great Tit', scientific_name: 'Parus major', common_name: 'Great Tit', camera: 'birdcam', hidden: false } });
    const release = holdCaptures(mock, [GARDEN_ID]);
    await chooseRecord(page, GARDEN_ID);
    await expect.poll(() => mock.captureReads).toEqual([GARDEN_ID]);
    await chooseRecord(page, FRIGATE_ID);
    await expect(page.getByRole('dialog')).toBeVisible();
    release[GARDEN_ID]();
    await page.waitForTimeout(250);
    await expect(page.locator('[data-garden-capture-modal]')).toHaveCount(0);
    await expect(page.getByRole('dialog')).toHaveCount(1);
    await expect(staleToast(page)).toHaveCount(0);
});

test('a Garden record chosen after a slow detection is the only record that opens', async ({ page }) => {
    const mock = await openExplorer(page, '&garden=1');
    searchesRecords(mock, { [GARDEN_ID]: gardenSearchRecord(GARDEN_ID, 'Red fox'), [FRIGATE_ID]: { kind: 'detection', id: FRIGATE_ID, observed_at: '2026-11-02T08:00:00Z', display_name: 'Great Tit', scientific_name: 'Parus major', common_name: 'Great Tit', camera: 'birdcam', hidden: false } });
    let releaseEvent: () => void = () => undefined;
    const held = new Promise<void>(resolve => { releaseEvent = resolve; });
    let eventReads = 0;
    mock.answerEvent = async route => {
        eventReads += 1;
        await held;
        await route.fulfill({ json: [DETECTION] }).catch(() => undefined);
    };
    await chooseRecord(page, FRIGATE_ID);
    await expect.poll(() => eventReads).toBe(1);
    await chooseRecord(page, GARDEN_ID);
    await expect(page.locator('[data-garden-capture-modal]')).toContainText('Red fox');
    releaseEvent();
    await page.waitForTimeout(250);
    await expect(page.locator('[data-garden-capture-modal]')).toHaveCount(1);
    await expect(page.getByRole('dialog', { name: /Great Tit/ })).toHaveCount(0);
});

test('narrowing the Explorer while a record is still being read leaves that record closed', async ({ page }) => {
    const mock = await openExplorer(page, '&garden=1');
    searchesRecords(mock, { [GARDEN_ID]: gardenSearchRecord(GARDEN_ID, 'Red fox') });
    const release = holdCaptures(mock, [GARDEN_ID]);
    await chooseRecord(page, GARDEN_ID);
    await expect.poll(() => mock.captureReads).toEqual([GARDEN_ID]);
    const box = searchBox(page);
    await box.fill('tit');
    await option(page, /^Tits/).click();
    await expect(page.locator('[data-explorer-token]').filter({ hasText: 'Family: Tits' })).toBeVisible();
    release[GARDEN_ID]();
    await page.waitForTimeout(250);
    await expect(page.locator('[data-garden-capture-modal]')).toHaveCount(0);
    await expect(staleToast(page)).toHaveCount(0);
});

// A ring drawn outside the box is cut off by any clipping edge it touches, so the box carries it inside.
async function focusRing(page: Page) {
    return page.evaluate(() => {
        const input = document.getElementById('explorer-search-input');
        if (!input) throw new Error('The search box is missing');
        const box = input.getBoundingClientRect();
        // Computed shadows read `colour x y blur spread [inset]`; the offset layer has no spread.
        const shadows = getComputedStyle(input).boxShadow.split(/,\s*(?=rgb)/).map(layer => /^(rgba?\([^)]*\))\s+\S+\s+\S+\s+\S+\s+([\d.]+)px(\s+inset)?$/.exec(layer.trim()));
        const ring = shadows.find(layer => layer && Number(layer[2]) > 0);
        const spread = Number(ring?.[2] ?? 0);
        const colour = ring?.[1] ?? '';
        const reach = ring?.[3] ? 0 : spread;
        // Every ancestor that clips, and the viewport, must hold the whole ring.
        const clips: DOMRect[] = [new DOMRect(0, 0, document.documentElement.clientWidth, window.innerHeight)];
        for (let node = input.parentElement; node; node = node.parentElement) {
            const style = getComputedStyle(node);
            if (style.overflowX !== 'visible' || style.overflowY !== 'visible') clips.push(node.getBoundingClientRect());
        }
        const clipped = clips.some(clip => box.left - reach < clip.left || box.right + reach > clip.right || box.top - reach < clip.top || box.bottom + reach > clip.bottom);
        const holder = input.closest('[data-explorer-search]')?.getBoundingClientRect();
        return { spread, colour, clipped, width: box.width, holderWidth: holder?.width ?? 0 };
    });
}

const surfaces = [{ name: 'phone', size: { width: 390, height: 844 } }, { name: 'desktop', size: { width: 1280, height: 800 } }];
for (const { name, size } of surfaces) for (const theme of ['light', 'dark']) {
    test(`on a ${name} the keyboard focus ring of the search box is whole and solid in the ${theme} theme`, async ({ page }) => {
        await page.setViewportSize(size);
        await openExplorer(page, theme === 'dark' ? '&theme=dark' : '');
        await page.keyboard.press('Tab');
        await searchBox(page).focus();
        await page.keyboard.press('ArrowDown');
        await expect(searchBox(page)).toBeFocused();
        const ring = await focusRing(page);
        expect(ring.spread).toBeGreaterThanOrEqual(2);
        expect(ring.clipped).toBe(false);
        // Opaque, so it keeps its contrast against the page it sits on.
        expect(ring.colour).toMatch(/^rgb\(/);
        // The box still fills its place in the rail.
        expect(ring.width).toBe(ring.holderWidth);
        if (shots) await page.screenshot({ path: `${shots}/explorer-search-focus-${name}-${theme}-${test.info().project.name}.png` });
    });
}
