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

// Every time in the fixture counts back from one fixed instant, and the page's clock is pinned to
// it, so which calendar day a visit falls on never depends on when the suite runs. Noon in London:
// a page 40 minutes apart reaches back 16 hours, to 20:00 the day before (18 visits on the 15th,
// 6 on the 14th); a page one minute apart stays inside the 15th.
const NOW = Date.parse('2026-06-15T11:00:00Z');

function record(index: number, minutesApart: number) {
    const [scientific, common] = species[index % species.length];
    return {
        frigate_event: `visit-${index}`, display_name: common, scientific_name: scientific, common_name: common,
        camera_name: index % 2 ? 'feeder' : 'birdtable', detection_time: new Date(NOW - (index + 1) * minutesApart * 60 * 1000).toISOString(),
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
    /** How long the visits and their count take to answer. */
    answerAfterMs?: number;
}

const dailySummary = {
    audio_confirmations: 0, hourly_distribution: Array(24).fill(0), hourly_visits: Array(24).fill(0),
    latest_detection: null, top_species: [], total_count: 0, visit_count: 0, camera_visits: []
};
const audioSummary = { daily_counts: [], hourly_counts: [], source_count: 0, sources: [], species_count: 0, top_species: [], total: 0 };
const shiftsOf = (page: Page): Promise<Shift[]> => page.evaluate(() => (window as unknown as { explorerShifts: Shift[] }).explorerShifts);

/** The owner's feeder behind the real App shell, with layout shifts recorded from the first frame. */
async function feeder(page: Page, viewport: { width: number; height: number }, { awaitingCheck = 0, minutesApart = 40, answerAfterMs = 600 }: Feeder = {}): Promise<{ visitsAnsweredAt: number }> {
    // The suite's own clock, not the page's pinned one: when the latest visits read was answered.
    const answers = { visitsAnsweredAt: 0 };
    await page.setViewportSize(viewport);
    await page.clock.setFixedTime(NOW);
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
            '/api/update-status': { update_available: false },
            '/api/events/review-queue': { items: [], total: 0 },
            '/api/stats/daily-summary': dailySummary,
            '/api/audio/summary': audioSummary,
            '/api/audio/recent': []
        };
        if (pathname === '/api/sse') return route.abort();
        if (pathname.endsWith('.jpg')) return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="120"><rect width="160" height="120" fill="#4d7c0f"/></svg>' });
        // The page has drawn its loading state before the visits and their count arrive.
        if (pathname === '/api/visits' || pathname === '/api/events' || pathname === '/api/events/count') {
            await new Promise(resolve => setTimeout(resolve, answerAfterMs));
            if (pathname === '/api/visits') answers.visitsAnsweredAt = Date.now();
        }
        if (pathname in responses) return route.fulfill({ json: responses[pathname] });
        return route.fulfill({ status: 503, json: { detail: 'Not part of this fixture' } });
    });
    return answers;
}

async function explorerSettled(page: Page): Promise<void> {
    await expect(page.locator('[data-explorer-count]')).toContainText('763 visits');
    await expect(page.locator('[data-explorer-visit="visit-0"] [data-detection-card]')).toBeVisible();
    // Late media and late facets have had their chance to move things.
    await page.waitForTimeout(2_000);
}

/** The day strip's counts are only meaningful against the fixture's instant, so the pin itself is checked. */
async function expectClockPinnedToFixture(page: Page): Promise<void> {
    expect(await page.evaluate(() => Date.now())).toBe(NOW);
}

/** Every layout shift of a cold Explorer load. */
async function coldLoadShifts(page: Page, viewport: { width: number; height: number }, options: Feeder = {}): Promise<Shift[]> {
    await feeder(page, viewport, options);
    await page.goto('/events');
    await explorerSettled(page);
    return shiftsOf(page);
}

/**
 * Every layout shift of an in-app move from a settled Dashboard to the Explorer, made the way a
 * person makes it. Chrome leaves out shifts within 500 ms of an input, so the visits answer well
 * after that: what they move when they land is counted.
 */
async function routeChangeShifts(page: Page, viewport: { width: number; height: number }): Promise<Shift[]> {
    const answers = await feeder(page, viewport, { awaitingCheck: 3, answerAfterMs: 1_200 });
    await page.goto('/');
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    await page.waitForTimeout(2_500);
    if (viewport.width < 768) await page.getByRole('button', { name: 'Menu', exact: true }).click();
    const link = page.getByRole('navigation').getByRole('button', { name: 'Explorer', exact: true });
    await expect(link).toBeVisible();
    await page.evaluate(() => { (window as unknown as { explorerShifts: Shift[] }).explorerShifts.length = 0; });
    const pressedAt = Date.now();
    await link.click();
    await expect(page).toHaveURL(/\/events$/);
    // The loading state is on screen, and the input window has passed, before any answer arrives.
    await expect(page.locator('[data-explorer-count]')).toHaveAttribute('data-explorer-count', 'pending');
    await explorerSettled(page);
    const shifts = await shiftsOf(page);
    expect(answers.visitsAnsweredAt - pressedAt, 'the visits answered after the recent-input window').toBeGreaterThan(700);
    return shifts;
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

for (const [name, viewport] of [['a 1440 px desktop', { width: 1440, height: 900 }], ['a 390 px phone', { width: 390, height: 844 }]] as const) {
    test(`moving from the Dashboard to the Explorer on ${name} moves nothing when the visits arrive`, async ({ page }) => {
        const shifts = await routeChangeShifts(page, viewport);
        expect(total(shifts), named(shifts)).toBeLessThan(0.02);
    });
}

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
    await expectClockPinnedToFixture(page);
    await expect(page.locator('[data-events-timeline]')).toHaveCount(0);
    // "0 Garden visits on this page" read as a fault; a figure is given only when there is one.
    await expect(page.locator('[data-explorer-count]')).toHaveText('763 visits');
});

test('a page from two days names each day with a plain count, and one day narrows the page to itself', async ({ page }) => {
    const shifts = await coldLoadShifts(page, { width: 1440, height: 900 });
    await expectClockPinnedToFixture(page);
    const days = page.locator('[data-events-timeline] button');
    await expect(days).toHaveCount(3);
    await expect(days.first()).toHaveText(/^All\s*24$/);
    await expect(days.nth(1)).toHaveText(/^15 Jun\s*18$/);
    await expect(days.nth(2)).toHaveText(/^14 Jun\s*6$/);
    await expect(page.locator('[data-events-timeline] svg')).toHaveCount(0);
    // The strip arrives with the results, above them, and still moves nothing already drawn.
    expect(total(shifts), named(shifts)).toBeLessThan(0.02);
    await days.nth(1).click();
    await expect(days.nth(1)).toHaveAttribute('aria-pressed', 'true');
    await expect(page.locator('[data-explorer-visit]')).toHaveCount(18);
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
    await page.locator('[data-explorer-sheet-close]').click();
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

test('on a phone Filters opens a named modal sheet that holds focus, and Escape or Close hands it back to the button', async ({ page }) => {
    await coldLoadShifts(page, { width: 390, height: 844 }, { minutesApart: 1 });
    const filters = page.locator('[data-explorer-filter-toggle]');
    const sheet = page.getByRole('dialog', { name: 'Filters' });
    await expect(sheet).toHaveCount(0);

    await filters.focus();
    await page.keyboard.press('Enter');
    await expect(sheet).toBeVisible();
    await expect(sheet).toHaveAttribute('aria-modal', 'true');
    const inside = () => sheet.evaluate(node => node.contains(document.activeElement));
    await expect.poll(inside).toBe(true);

    // Tab and Shift+Tab go round the sheet, past both ends, without reaching the page beneath.
    const stops = await sheet.locator('a[href], button:not([disabled]), input, select').count();
    expect(stops).toBeGreaterThan(5);
    for (let press = 0; press < stops + 3; press += 1) {
        await page.keyboard.press('Tab');
        expect(await inside()).toBe(true);
    }
    for (let press = 0; press < stops + 3; press += 1) {
        await page.keyboard.press('Shift+Tab');
        expect(await inside()).toBe(true);
    }
    // The page's own shortcuts stay behind it: "/" does not pull focus out to the search.
    await page.keyboard.press('/');
    expect(await inside()).toBe(true);

    await page.keyboard.press('Escape');
    await expect(sheet).toHaveCount(0);
    await expect(filters).toBeFocused();

    await page.keyboard.press('Enter');
    await expect(sheet).toBeVisible();
    await sheet.getByRole('button', { name: 'Close' }).click();
    await expect(sheet).toHaveCount(0);
    await expect(filters).toBeFocused();

    // A press on the dimmed page beside the sheet closes it too.
    await filters.click();
    await expect(sheet).toBeVisible();
    await page.mouse.click(195, 20);
    await expect(sheet).toHaveCount(0);
});

test('a filter chosen in the sheet acts at once and is still applied when the sheet is closed', async ({ page }) => {
    await coldLoadShifts(page, { width: 390, height: 844 }, { minutesApart: 1 });
    await page.locator('[data-explorer-filter-toggle]').click();
    const sheet = page.getByRole('dialog', { name: 'Filters' });
    await sheet.getByRole('button', { name: 'Today', exact: true }).click();
    await expect(sheet.getByRole('button', { name: 'Today', exact: true })).toHaveAttribute('aria-pressed', 'true');
    await page.keyboard.press('Escape');
    await expect(page.locator('[data-explorer-token]')).toHaveText(/Today/);
});
