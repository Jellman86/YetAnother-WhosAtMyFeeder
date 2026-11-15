import { expect, test, type Page } from '@playwright/test';

// The real App shell on a cold load, as an owner with BirdNET-Go and the Garden beta on: the
// widest header the Explorer has. The count and the visits arrive after the page has drawn its
// loading state, and nothing already on screen may move when they do.
const owner = { auth_required: false, is_authenticated: true, needs_initial_setup: false, birdnet_enabled: true, garden_animals_enabled: true };
const settings = { birdnet_enabled: true, classification_threshold: 0.6, beta_garden_animals: true, garden_cameras: ['garden'] };
const species = [
    ['Cyanistes caeruleus', 'Eurasian Blue Tit'], ['Parus major', 'Great Tit'], ['Erithacus rubecula', 'European Robin'],
    ['Passer domesticus', 'House Sparrow'], ['Turdus merula', 'Eurasian Blackbird'], ['Carduelis carduelis', 'European Goldfinch']
] as const;

function record(index: number, minutesApart: number) {
    const [scientific, common] = species[index % species.length];
    return {
        frigate_event: `visit-${index}`, display_name: common, scientific_name: scientific, common_name: common,
        camera_name: index % 2 ? 'feeder' : 'birdtable', detection_time: new Date(Date.now() - (index + 1) * minutesApart * 60 * 1000).toISOString(),
        score: 0.86, has_clip: false, has_snapshot: true, temperature: 12.4, weather_condition: 'rain'
    };
}

function visit(index: number, minutesApart: number) {
    const capture = record(index, minutesApart);
    return {
        visit_id: capture.frigate_event, start_time: capture.detection_time, end_time: capture.detection_time, capture_count: 1,
        best_score: capture.score, needs_review: false, audio_confirmed: false, representative: capture, latest: capture, peak_capture: null
    };
}

interface Shift { at: number; value: number; moved: string[] }

/** Every layout shift since navigation, with the nodes that moved, so a failure names its cause. */
interface Feeder {
    /** Garden captures still waiting for their automatic check: a sentence added to the count. */
    awaitingCheck?: number;
    /** 40 minutes between visits spreads a page of 24 over two days; one minute keeps it to one. */
    minutesApart?: number;
}

async function coldLoadShifts(page: Page, viewport: { width: number; height: number }, { awaitingCheck = 0, minutesApart = 40 }: Feeder = {}): Promise<Shift[]> {
    await page.setViewportSize(viewport);
    await page.addInitScript(() => {
        const shifts: Shift[] = [];
        (window as unknown as { explorerShifts: Shift[] }).explorerShifts = shifts;
        const name = (node: Node | null): string => {
            if (!(node instanceof Element)) return node?.nodeName ?? '';
            const marks = [...node.attributes].filter(attribute => attribute.name.startsWith('data-')).map(attribute => `[${attribute.name}]`).join('');
            return `${node.tagName.toLowerCase()}${marks || `.${[...node.classList].slice(0, 3).join('.')}`}`;
        };
        new PerformanceObserver(list => {
            for (const entry of list.getEntries() as unknown as { hadRecentInput: boolean; startTime: number; value: number; sources: { node: Node | null }[] }[]) {
                if (entry.hadRecentInput) continue;
                shifts.push({ at: Math.round(entry.startTime), value: entry.value, moved: entry.sources.map(source => name(source.node)) });
            }
        }).observe({ type: 'layout-shift', buffered: true });
    });
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route('**/health', route => route.fulfill({ json: { status: 'healthy' } }));
    await page.route(url => url.pathname.startsWith('/api/'), async route => {
        const pathname = new URL(route.request().url()).pathname;
        const responses: Record<string, unknown> = {
            '/api/auth/status': owner,
            '/api/settings': settings,
            '/api/settings/public': {},
            '/api/events': Array.from({ length: 24 }, (_, index) => record(index, minutesApart)),
            '/api/events/count': { count: 937 },
            '/api/events/hidden-count': { count: 0 },
            '/api/events/filters': {
                species: species.map(([scientific, common], index) => ({ value: scientific, display_name: common, scientific_name: scientific, common_name: common, count: 160 - index * 20 })),
                cameras: ['birdtable', 'feeder'], camera_counts: { birdtable: 400, feeder: 363 },
                totals: { total: 763, favorites: 9, audio_matched: 12 }
            },
            '/api/visits': { total: 763, gap_seconds: 60, visits: Array.from({ length: 24 }, (_, index) => visit(index, minutesApart)) },
            '/api/garden/visits': { visits: [], total: 0, capture_total: 0, awaiting_check: awaitingCheck, limit: 24, offset: 0 },
            '/api/update-status': { update_available: false }
        };
        if (pathname === '/api/sse') return route.abort();
        if (pathname.endsWith('.jpg')) return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="120"><rect width="160" height="120" fill="#4d7c0f"/></svg>' });
        // The page has drawn its loading state before the visits and their count arrive.
        if (pathname === '/api/visits' || pathname === '/api/events' || pathname === '/api/events/count') await new Promise(resolve => setTimeout(resolve, 600));
        if (pathname in responses) return route.fulfill({ json: responses[pathname] });
        return route.fulfill({ status: 503, json: { detail: 'Not part of this fixture' } });
    });
    await page.goto('/events');
    await expect(page.locator('[data-explorer-count]')).toContainText('763 visits');
    await expect(page.locator('[data-explorer-visit="visit-0"] [data-detection-card]')).toBeVisible();
    // Late media and late facets have had their chance to move things.
    await page.waitForTimeout(2_000);
    return page.evaluate(() => (window as unknown as { explorerShifts: Shift[] }).explorerShifts);
}

const total = (shifts: Shift[]): number => shifts.reduce((sum, shift) => sum + shift.value, 0);
const named = (shifts: Shift[]): string => `layout shifts: ${JSON.stringify(shifts.filter(shift => shift.value >= 0.001))}`;

// Chrome calls a cumulative shift above 0.1 "needs improvement"; these sit well inside "good".
test('a cold Explorer load on a 1440 px desktop moves nothing when its longest count arrives', async ({ page }) => {
    // Captures waiting for their automatic check add a sentence to the count, the longest it gets.
    const shifts = await coldLoadShifts(page, { width: 1440, height: 900 }, { awaitingCheck: 3 });
    await expect(page.locator('[data-garden-awaiting-check]')).toBeVisible();
    expect(total(shifts), named(shifts)).toBeLessThan(0.02);
});

test('a cold Explorer load on a 390 px phone moves nothing when a count that fits its line arrives', async ({ page }) => {
    const shifts = await coldLoadShifts(page, { width: 390, height: 844 });
    expect(total(shifts), named(shifts)).toBeLessThan(0.02);
});

test('on a desktop the count has a line of its own, so its length cannot wrap the controls beside the search', async ({ page }) => {
    await coldLoadShifts(page, { width: 1440, height: 900 }, { awaitingCheck: 3 });
    const search = await page.locator('[data-explorer-header-search]').boundingBox();
    const toggle = await page.locator('[data-explorer-rail-toggle]').boundingBox();
    const count = await page.locator('[data-explorer-count]').boundingBox();
    if (!search || !toggle || !count) throw new Error('The Explorer header is missing a part');
    // The controls share the search's row; the count sits beneath both, above the results.
    expect(toggle.y).toBeLessThan(search.y + search.height);
    expect(toggle.x).toBeGreaterThanOrEqual(search.x + search.width);
    expect(count.y).toBeGreaterThanOrEqual(search.y + search.height);
});

test('a page from one day has no day strip, and a count with nothing to add says only the visits', async ({ page }) => {
    await coldLoadShifts(page, { width: 1440, height: 900 }, { minutesApart: 1 });
    await expect(page.locator('[data-events-timeline]')).toHaveCount(0);
    // "0 Garden visits on this page" read as a fault; a figure is given only when there is one.
    await expect(page.locator('[data-explorer-count]')).toHaveText('763 visits');
});

test('a page from two days names each day with a plain count, and one day narrows the page to itself', async ({ page }) => {
    const shifts = await coldLoadShifts(page, { width: 1440, height: 900 });
    const days = page.locator('[data-events-timeline] button');
    await expect(days).toHaveCount(3);
    await expect(days.first()).toHaveText(/^All\s*24$/);
    await expect(page.locator('[data-events-timeline] svg')).toHaveCount(0);
    // The strip arrives with the results, above them, and still moves nothing already drawn.
    expect(total(shifts), named(shifts)).toBeLessThan(0.02);
    await days.nth(1).click();
    await expect(days.nth(1)).toHaveAttribute('aria-pressed', 'true');
    const shown = Number(((await days.nth(1).textContent()) ?? '').trim().split(/\s+/).at(-1));
    await expect(page.locator('[data-explorer-visit]')).toHaveCount(shown);
});

test('on a phone two rows stand between the count and the first photo: the search, then Filters with the view switch', async ({ page }) => {
    await coldLoadShifts(page, { width: 390, height: 844 }, { minutesApart: 1 });
    const count = await page.locator('[data-explorer-count]').boundingBox();
    const search = await page.locator('[data-explorer-search]').boundingBox();
    const filters = page.locator('[data-explorer-filter-toggle]');
    const filtersBox = await filters.boundingBox();
    const view = await page.locator('[data-explorer-view-toggle="list"]').boundingBox();
    const card = await page.locator('[data-detection-card]').first().boundingBox();
    if (!count || !search || !filtersBox || !view || !card) throw new Error('The Explorer is missing a part');
    expect(search.y).toBeGreaterThanOrEqual(count.y + count.height);
    expect(filtersBox.y).toBeGreaterThanOrEqual(search.y + search.height);
    // The view switch shares the Filters row, at its far end.
    expect(Math.abs((view.y + view.height / 2) - (filtersBox.y + filtersBox.height / 2))).toBeLessThanOrEqual(4);
    expect(view.x).toBeGreaterThan(filtersBox.x + filtersBox.width);
    expect(card.y - (filtersBox.y + filtersBox.height)).toBeLessThanOrEqual(48);

    // The two controls used less often open with the filters, and selecting has its way out on the page.
    await expect(page.locator('[data-explorer-heard-toggle]')).toBeHidden();
    await expect(page.getByRole('button', { name: 'Multi-select' })).toBeHidden();
    await filters.click();
    await expect(page.locator('[data-explorer-heard-toggle]')).toBeVisible();
    await page.getByRole('button', { name: 'Multi-select' }).click();
    await filters.click();
    await expect(page.locator('[data-explorer-selection-count]')).toHaveText('No captures selected');
    await page.locator('[data-explorer-selection-done]').click();
    await expect(page.locator('[data-explorer-selection-count]')).toHaveCount(0);
});

test('the listening history is opened from the sidebar, and the toolbar keeps one audio control', async ({ page }) => {
    await coldLoadShifts(page, { width: 1440, height: 900 });
    await expect(page.locator('[data-explorer-controls]').getByText('Audio history')).toHaveCount(0);
    await expect(page.locator('[data-explorer-controls] [data-explorer-heard-toggle]')).toBeVisible();
    await page.getByRole('navigation').getByRole('button', { name: 'Audio history' }).click();
    await expect(page).toHaveURL(/\/audio$/);
});

test('the Visitors switch is three equal segments, one to a line', async ({ page }) => {
    await coldLoadShifts(page, { width: 1440, height: 900 });
    const boxes = await page.locator('[data-explorer-subjects-option]').evaluateAll(nodes => nodes.map(node => node.getBoundingClientRect()).map(box => ({ x: box.x, y: box.y, width: box.width, height: box.height })));
    expect(boxes).toHaveLength(3);
    for (const box of boxes) {
        expect(box.x).toBe(boxes[0].x);
        expect(box.width).toBe(boxes[0].width);
        expect(box.height).toBe(boxes[0].height);
    }
    expect(boxes[1].y).toBeGreaterThan(boxes[0].y);
    expect(boxes[2].y).toBeGreaterThan(boxes[1].y);
});
