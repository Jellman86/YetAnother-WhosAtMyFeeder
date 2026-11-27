import { test, expect, type Page, type Route } from '@playwright/test';

// The counts beside the Explorer's filters follow the period and Visits or Captures (#1097).
const COUNTS = {
    all: { visits: { dunnock: 12, robin: 8, wren: 3, birdcam: 15 }, captures: { dunnock: 30, robin: 19, wren: 5, birdcam: 40 } },
    today: { visits: { dunnock: 3, robin: 0, wren: 12345, birdcam: 3 }, captures: { dunnock: 7, robin: 0, wren: 23456, birdcam: 7 } }
} as const;

function filtersFor(url: URL) {
    const period = url.searchParams.has('start_date') ? 'today' : 'all';
    const unit = url.searchParams.get('unit') === 'visits' ? 'visits' : 'captures';
    const counts: Record<'dunnock' | 'robin' | 'wren' | 'birdcam', number> = COUNTS[period][unit];
    return {
        species: [
            { value: 'Prunella modularis', display_name: 'Dunnock', common_name: 'Dunnock', scientific_name: 'Prunella modularis', count: counts.dunnock },
            { value: 'Erithacus rubecula', display_name: 'European Robin', common_name: 'European Robin', scientific_name: 'Erithacus rubecula', count: counts.robin },
            { value: 'Troglodytes troglodytes', display_name: 'Eurasian Wren of the Northern Woods', common_name: 'Eurasian Wren of the Northern Woods', scientific_name: 'Troglodytes troglodytes', count: counts.wren }
        ],
        cameras: ['birdcam'],
        camera_counts: { birdcam: counts.birdcam },
        totals: { total: counts.birdcam, favorites: 0, audio_matched: 0, video_analysed: 0, hidden: 1 },
        unit,
        gap_seconds: unit === 'visits' ? 60 : null
    };
}

function visit(id: string, at: string) {
    const representative = {
        frigate_event: id, display_name: 'Prunella modularis', scientific_name: 'Prunella modularis', common_name: 'Dunnock',
        camera_name: 'birdcam', detection_time: at, score: 0.91, has_clip: false
    };
    return { visit_id: id, start_time: at, end_time: at, capture_count: 1, best_score: 0.91, needs_review: false, audio_confirmed: false, representative, latest: representative, peak_capture: null };
}

interface Boundary {
    /** Answer a filter read; the default answers at once with the counts for its period and unit. */
    filters?: (route: Route, url: URL) => Promise<void> | void;
    /** Visits in all, for a page that has more than one page. */
    visitTotal?: number;
    /** Answer the hidden count; the default answers at once with 3. */
    hidden?: (route: Route) => Promise<void> | void;
    /** Answer a visits read with its default body; the default answers at once. */
    visits?: (route: Route, body: unknown) => Promise<void> | void;
    /** A public visitor rather than the owner. */
    guest?: boolean;
}

async function openExplorer(page: Page, boundary: Boundary = {}, width = 1280) {
    const reads: { visits: URL[]; filters: URL[] } = { visits: [], filters: [] };
    await page.setViewportSize({ width, height: 900 });
    await page.route('https://fonts.googleapis.com/**', (route) => route.fulfill({ contentType: 'text/css', body: '' }));
    await page.route('https://fonts.gstatic.com/**', (route) => route.abort());
    await page.route((url) => url.pathname.startsWith('/api/'), (route) => {
        const url = new URL(route.request().url());
        if (url.pathname === '/api/events/filters') {
            reads.filters.push(url);
            if (boundary.filters) return boundary.filters(route, url);
            return route.fulfill({ json: filtersFor(url) });
        }
        if (url.pathname === '/api/visits') {
            reads.visits.push(url);
            const total = boundary.visitTotal ?? 0;
            const limit = Number(url.searchParams.get('limit') ?? 24);
            const offset = Number(url.searchParams.get('offset') ?? 0);
            const visits = Array.from({ length: Math.max(0, Math.min(limit, total - offset)) }, (_, index) => visit(`v${offset + index}`, '2033-10-03T08:00:00Z'));
            const body = { total, gap_seconds: 60, visits };
            if (boundary.visits) return boundary.visits(route, body);
            return route.fulfill({ json: body });
        }
        if (url.pathname === '/api/garden/visits') return route.fulfill({ json: { visits: [], total: 0, capture_total: 0, limit: 200, offset: 0 } });
        if (url.pathname === '/api/events/hidden-count') return boundary.hidden ? boundary.hidden(route) : route.fulfill({ json: { hidden_count: 3 } });
        if (url.pathname === '/api/events/count') return route.fulfill({ json: { count: 0, filtered: true } });
        if (url.pathname === '/api/events' || url.pathname.endsWith('/labels')) return route.fulfill({ json: [] });
        return route.fulfill({ json: {} });
    });
    await page.goto(`/browser-tests/owner-history.html?surface=explorer${boundary.guest ? '&guest=1' : ''}`);
    await expect(page.locator('[data-events-filter-bar]')).toBeVisible();
    if (width < 1024) await page.locator('[data-explorer-filter-toggle]').click();
    return reads;
}

const species = (page: Page, name: string) => page.locator('[data-explorer-species-list]').getByRole('button', { name: new RegExp(`^${name}`) });
const countOf = (page: Page, name: string) => species(page, name).locator('[data-explorer-facet-count]');
const when = (page: Page, label: string) => page.locator('[data-explorer-date-facet]').getByRole('button', { name: label, exact: true });
const speciesList = (page: Page) => page.locator('[data-explorer-species-list]');

test('switching to Today and to Captures changes the species counts', async ({ page }) => {
    const reads = await openExplorer(page);
    const unit = page.locator('[data-explorer-facet-unit]');
    await expect(countOf(page, 'Dunnock')).toHaveText('12');
    await expect(unit).toHaveText('Visits');
    // Each count is read with its unit, as the heading beside the list shows it.
    await expect(species(page, 'Dunnock')).toHaveAccessibleName(/12 visits$/);
    expect(reads.filters.at(-1)?.searchParams.get('unit')).toBe('visits');

    await when(page, 'Today').click();
    await expect(countOf(page, 'Dunnock')).toHaveText('3');
    await expect(countOf(page, 'European Robin')).toHaveText('0');
    expect(reads.filters.at(-1)?.searchParams.get('start_date')).toBeTruthy();

    await page.locator('[data-explorer-show="captures"]').click();
    await expect(countOf(page, 'Dunnock')).toHaveText('7');
    await expect(unit).toHaveText('Captures');
    await expect(species(page, 'Dunnock')).toHaveAccessibleName(/7 captures$/);
    expect(reads.filters.at(-1)?.searchParams.get('unit')).toBe('captures');

    // The camera list follows the same choices.
    await page.locator('[data-explorer-camera-facet] summary').click();
    await expect(page.getByRole('button', { name: 'birdcam 7 captures', exact: true })).toBeVisible();
});

test('the counts and the results of one read are asked for over the same bounds', async ({ page }) => {
    const reads = await openExplorer(page);
    await expect(countOf(page, 'Dunnock')).toHaveText('12');

    await when(page, 'Last 24 hours').click();
    await expect.poll(() => reads.visits.filter((url) => url.searchParams.has('start_time')).length).toBe(1);
    await expect.poll(() => reads.filters.filter((url) => url.searchParams.has('start_time')).length).toBe(1);
    const visits = reads.visits.find((url) => url.searchParams.has('start_time'));
    const filters = reads.filters.find((url) => url.searchParams.has('start_time'));
    expect(filters?.searchParams.get('start_time')).toBe(visits?.searchParams.get('start_time'));
    expect(filters?.searchParams.get('end_time')).toBe(visits?.searchParams.get('end_time'));
});

test('read again across midnight, Today counts and shows the new day in both reads', async ({ page }) => {
    await page.clock.setFixedTime(new Date('2033-10-03T23:59:50+01:00'));
    const reads = await openExplorer(page, { visitTotal: 60 });
    await when(page, 'Today').click();
    await expect.poll(() => reads.filters.at(-1)?.searchParams.get('start_date')).toBe('2033-10-03');
    expect(reads.visits.at(-1)?.searchParams.get('start_date')).toBe('2033-10-03');
    await expect(countOf(page, 'Dunnock')).toHaveText('3');

    // The next page is read after midnight: its results and its counts both read the new day.
    await page.clock.setFixedTime(new Date('2033-10-04T00:00:10+01:00'));
    const before = reads.filters.length;
    await page.getByRole('button', { name: 'Next page' }).click();
    await expect.poll(() => reads.visits.at(-1)?.searchParams.get('offset')).toBe('24');
    expect(reads.visits.at(-1)?.searchParams.get('start_date')).toBe('2033-10-04');
    await expect.poll(() => reads.filters.length).toBe(before + 1);
    expect(reads.filters.at(-1)?.searchParams.get('start_date')).toBe('2033-10-04');
    expect(reads.filters.at(-1)?.searchParams.get('end_date')).toBe('2033-10-04');
});

test('a retry, and a refresh of counts already shown, wait for their own answer', async ({ page }) => {
    const held: Route[] = [];
    let failToday = true;
    let hold = false;
    await openExplorer(page, {
        filters: (route, url) => {
            if (hold) {
                held.push(route);
                return;
            }
            if (failToday && url.searchParams.has('start_date')) return route.fulfill({ status: 503, json: { detail: 'busy' } });
            return route.fulfill({ json: filtersFor(url) });
        }
    });
    await expect(countOf(page, 'Dunnock')).toHaveText('12');

    await when(page, 'Today').click();
    const notice = page.locator('[data-explorer-facet-counts-unavailable]');
    await expect(notice).toHaveRole('status');
    await expect(notice).toHaveText('The counts for these filters could not be read. Refresh options tries again.');
    await expect(countOf(page, 'Dunnock')).toHaveCount(0);

    // Retrying waits for the retry: no failure notice and no old number while it is read.
    failToday = false;
    hold = true;
    await page.getByRole('button', { name: 'Refresh options' }).click();
    await expect.poll(() => held.length).toBe(1);
    await expect(notice).toHaveText('');
    await expect(speciesList(page)).toHaveAttribute('aria-busy', 'true');
    await expect(page.locator('[data-explorer-facet-unit]')).toHaveText('Counting…');
    await held[0].fulfill({ json: filtersFor(new URL(held[0].request().url())) });
    await expect(countOf(page, 'Dunnock')).toHaveText('3');
    await expect(speciesList(page)).toHaveAttribute('aria-busy', 'false');

    // Refreshing counts already on screen waits too, rather than calling the old ones current.
    await page.getByRole('button', { name: 'Refresh options' }).click();
    await expect.poll(() => held.length).toBe(2);
    await expect(countOf(page, 'Dunnock')).toHaveCount(0);
    await expect(speciesList(page)).toHaveAttribute('aria-busy', 'true');
    await held[1].fulfill({ status: 503, json: { detail: 'busy' } });
    await expect(notice).toHaveText('The counts for these filters could not be read. Refresh options tries again.');
    await expect(countOf(page, 'Dunnock')).toHaveCount(0);
});

test('counts wait honestly while they are read, a late answer never overwrites a newer one, and Hidden stays offered', async ({ page }) => {
    const held: Route[] = [];
    let holdNext = true;
    await openExplorer(page, {
        filters: (route, url) => {
            if (holdNext) {
                holdNext = false;
                held.push(route);
                return;
            }
            return route.fulfill({ json: filtersFor(url) });
        }
    });
    // The first read is held; Today is chosen before it answers.
    await expect.poll(() => held.length).toBe(1);
    // Nothing is offered or counted before the first answer; the list says it is counting.
    await expect(page.locator('[data-explorer-facet-unit]')).toHaveText('Counting…');
    await expect(speciesList(page)).toHaveAttribute('aria-busy', 'true');
    await when(page, 'Today').click();
    await expect(countOf(page, 'Dunnock')).toHaveText('3');

    // The all-time answer arrives last: Today's counts stay on screen.
    await held[0].fulfill({ json: filtersFor(new URL(held[0].request().url())) });
    await page.waitForTimeout(200);
    await expect(countOf(page, 'Dunnock')).toHaveText('3');
    await expect(speciesList(page)).toHaveAttribute('aria-busy', 'false');

    // Whether Hidden is offered was read apart from the replaced read.
    await page.locator('[data-explorer-only-facet] summary').click();
    await expect(page.locator('[data-explorer-hidden-facet]')).toBeVisible();
});

test('on a phone a count arriving keeps its slot and the list keeps its order until it is current', async ({ page }) => {
    const held: Route[] = [];
    let hold = false;
    await openExplorer(
        page,
        {
            filters: (route, url) => {
                if (hold) {
                    held.push(route);
                    return;
                }
                return route.fulfill({ json: filtersFor(url) });
            }
        },
        390
    );
    const wren = species(page, 'Eurasian Wren');
    await expect(countOf(page, 'Eurasian Wren')).toHaveText('3');
    const slot = () => wren.locator('[data-explorer-facet-slot]').evaluate((node) => node.getBoundingClientRect().width);
    const order = () => speciesList(page).getByRole('button').evaluateAll((buttons) => buttons.map((button) => (button.querySelector('span span')?.textContent ?? '').trim()));
    const widthBefore = await slot();
    const heightBefore = await wren.evaluate((node) => node.getBoundingClientRect().height);
    const orderBefore = await order();

    hold = true;
    await when(page, 'Today').click();
    await expect.poll(() => held.length).toBe(1);
    // While Today is read, the rows keep their places and the slot its width.
    await expect(wren.locator('[data-explorer-facet-count-pending]')).toBeVisible();
    expect(await order()).toEqual(orderBefore);
    expect(await slot()).toBe(widthBefore);

    // Today's five-digit count fits the same slot, and only then does the Wren move to the top.
    await held[0].fulfill({ json: filtersFor(new URL(held[0].request().url())) });
    await expect(countOf(page, 'Eurasian Wren')).toHaveText('12345');
    expect(await slot()).toBe(widthBefore);
    expect(await wren.evaluate((node) => node.getBoundingClientRect().height)).toBe(heightBefore);
    expect((await order())[0]).toContain('Eurasian Wren');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test('a page read again under the same filters shows its counts as updating, never as current, until they are read', async ({ page }) => {
    const held: Route[] = [];
    let reads = 0;
    const urls = await openExplorer(page, {
        visitTotal: 60,
        filters: (route, url) => {
            reads += 1;
            if (reads > 1) {
                held.push(route);
                return;
            }
            return route.fulfill({ json: filtersFor(url) });
        }
    });
    await expect(countOf(page, 'Dunnock')).toHaveText('12');
    await expect(speciesList(page)).toHaveAttribute('aria-busy', 'false');

    await page.getByRole('button', { name: 'Next page' }).click();
    await expect.poll(() => urls.visits.at(-1)?.searchParams.get('offset')).toBe('24');
    // The newer page is on screen; the counts read with it are not yet.
    await expect(page.locator('[data-explorer-visit="v24"]')).toBeVisible();
    await expect.poll(() => held.length).toBe(1);
    // The earlier numbers stay readable, but as updating: the list is busy and says so.
    await expect(countOf(page, 'Dunnock')).toHaveText('12');
    // At full contrast: the label and the busy list say they are being counted, not a fade.
    expect(await species(page, 'Dunnock').locator('[data-explorer-facet-slot]').evaluate((node) => getComputedStyle(node).opacity)).toBe('1');
    await expect(speciesList(page)).toHaveAttribute('aria-busy', 'true');
    await expect(page.locator('[data-explorer-facet-unit]')).toHaveText('Counting…');
    await expect(page.locator('[data-explorer-facet-count-pending]')).toHaveCount(0);

    // A capture arrived between the two reads.
    const body = filtersFor(new URL(held[0].request().url()));
    body.species[0].count += 1;
    await held[0].fulfill({ json: body });
    await expect(countOf(page, 'Dunnock')).toHaveText('13');
    await expect(speciesList(page)).toHaveAttribute('aria-busy', 'false');
    await expect(page.locator('[data-explorer-facet-unit]')).toHaveText('Visits');
});

test('the results are read first, and the counts after them', async ({ page }) => {
    const heldVisits: { route: Route; body: unknown }[] = [];
    const urls = await openExplorer(page, { visitTotal: 2, visits: (route, body) => void heldVisits.push({ route, body }) });
    await expect.poll(() => heldVisits.length).toBe(1);
    await page.waitForTimeout(300);
    // While the results are being read, the counts wait their turn rather than compete with them.
    expect(urls.filters).toHaveLength(0);
    await expect(speciesList(page)).toHaveAttribute('aria-busy', 'true');

    await heldVisits[0].route.fulfill({ json: heldVisits[0].body });
    await expect.poll(() => urls.filters.length).toBe(1);
    await expect(countOf(page, 'Dunnock')).toHaveText('12');
});

test('before the species are known, the list never says no species were recorded', async ({ page }) => {
    const held: Route[] = [];
    await openExplorer(page, { visitTotal: 1, filters: (route) => void held.push(route) });
    await expect.poll(() => held.length).toBe(1);
    await expect(page.locator('[data-explorer-visit="v0"]')).toBeVisible();
    await expect(page.locator('[data-explorer-facet-unit]')).toHaveText('Counting…');
    await expect(page.getByText('No species recorded yet.')).toHaveCount(0);

    await held[0].fulfill({ status: 503, json: { detail: 'busy' } });
    await expect(page.locator('[data-explorer-facet-counts-unavailable]')).toHaveText('The counts for these filters could not be read. Refresh options tries again.');
    await expect(page.getByText('No species recorded yet.')).toHaveCount(0);
});

test('a history with no species says so once it has been read', async ({ page }) => {
    await openExplorer(page, { filters: (route, url) => route.fulfill({ json: { ...filtersFor(url), species: [] } }) });
    await expect(page.getByText('No species recorded yet.')).toBeVisible();
});

test('Refresh options reads the counts at once, whatever the hidden count is doing', async ({ page }) => {
    const heldHidden: Route[] = [];
    let holdHidden = false;
    await openExplorer(page, {
        hidden: (route) => (holdHidden ? void heldHidden.push(route) : route.fulfill({ json: { hidden_count: 3 } })),
        filters: (route, url) => (holdHidden ? undefined : route.fulfill({ json: filtersFor(url) }))
    });
    await expect(countOf(page, 'Dunnock')).toHaveText('12');

    holdHidden = true;
    await page.getByRole('button', { name: 'Refresh options' }).click();
    await expect.poll(() => heldHidden.length).toBe(1);
    // The counts are already being read: they wait, rather than standing as current behind the hidden count.
    await expect(speciesList(page)).toHaveAttribute('aria-busy', 'true');
    await expect(countOf(page, 'Dunnock')).toHaveCount(0);
});

for (const order of ['older answer last', 'older answer first'] as const) {
    test(`a hidden count answered out of order never removes Hidden (${order})`, async ({ page }) => {
        const heldHidden: Route[] = [];
        await openExplorer(page, { hidden: (route) => void heldHidden.push(route) });
        await expect(countOf(page, 'Dunnock')).toHaveText('12');
        await expect.poll(() => heldHidden.length).toBe(1);

        // Refresh options asks again; its answer is the newer one.
        await page.getByRole('button', { name: 'Refresh options' }).click();
        await expect.poll(() => heldHidden.length).toBe(2);
        const [mount, refresh] = heldHidden;
        if (order === 'older answer last') {
            await refresh.fulfill({ json: { hidden_count: 3 } });
            await mount.fulfill({ json: { hidden_count: 0 } });
        } else {
            await mount.fulfill({ json: { hidden_count: 0 } });
            await refresh.fulfill({ json: { hidden_count: 3 } });
        }
        await page.waitForTimeout(200);
        await page.locator('[data-explorer-only-facet] summary').click();
        await expect(page.locator('[data-explorer-hidden-facet]')).toBeVisible();
    });
}

test('a link naming a species by its name is read once the options name its value', async ({ page }) => {
    const reads = await openExplorer(page);
    await expect(countOf(page, 'Dunnock')).toHaveText('12');
    // Back to a link that names the Dunnock by its common name, with the options already read.
    await page.evaluate(() => {
        window.history.pushState(window.history.state, '', `${window.location.pathname}?surface=explorer&species=Dunnock`);
        window.dispatchEvent(new PopStateEvent('popstate'));
    });
    await expect.poll(() => reads.visits.at(-1)?.searchParams.get('species')).toBe('Prunella modularis');
    expect(reads.visits.filter((url) => url.searchParams.get('species') === 'Dunnock')).toHaveLength(0);
    expect(reads.filters.filter((url) => url.searchParams.get('species') === 'Dunnock')).toHaveLength(0);
});

test('a page whose counts cannot be read again says so, rather than keeping the old ones as current', async ({ page }) => {
    let reads = 0;
    const urls = await openExplorer(page, {
        visitTotal: 60,
        filters: (route, url) => {
            reads += 1;
            if (reads > 1) return route.fulfill({ status: 503, json: { detail: 'busy' } });
            return route.fulfill({ json: filtersFor(url) });
        }
    });
    await expect(countOf(page, 'Dunnock')).toHaveText('12');

    await page.getByRole('button', { name: 'Next page' }).click();
    await expect.poll(() => urls.visits.at(-1)?.searchParams.get('offset')).toBe('24');
    await expect.poll(() => reads).toBe(2);
    await expect(page.locator('[data-explorer-facet-counts-unavailable]')).toHaveText('The counts for these filters could not be read. Refresh options tries again.');
    await expect(countOf(page, 'Dunnock')).toHaveCount(0);
});

test('paging again while the counts are read keeps the last counts in view and ignores the replaced answer', async ({ page }) => {
    const held: Route[] = [];
    let reads = 0;
    const urls = await openExplorer(page, {
        visitTotal: 90,
        filters: (route, url) => {
            reads += 1;
            if (reads > 1) {
                held.push(route);
                return;
            }
            return route.fulfill({ json: filtersFor(url) });
        }
    });
    await expect(countOf(page, 'Dunnock')).toHaveText('12');

    await page.getByRole('button', { name: 'Next page' }).click();
    await expect.poll(() => held.length).toBe(1);
    await page.getByRole('button', { name: 'Next page' }).click();
    await expect.poll(() => urls.visits.at(-1)?.searchParams.get('offset')).toBe('48');
    await expect.poll(() => held.length).toBe(2);
    // Two pages on, the last counts read are still the ones in view, still marked as updating.
    await expect(countOf(page, 'Dunnock')).toHaveText('12');
    await expect(page.locator('[data-explorer-facet-count-pending]')).toHaveCount(0);
    await expect(speciesList(page)).toHaveAttribute('aria-busy', 'true');

    // The answer for the page left behind arrives first: it is not shown.
    const replaced = filtersFor(new URL(held[0].request().url()));
    replaced.species[0].count = 99;
    await held[0].fulfill({ json: replaced });
    await page.waitForTimeout(200);
    await expect(countOf(page, 'Dunnock')).toHaveText('12');
    await expect(speciesList(page)).toHaveAttribute('aria-busy', 'true');

    const newest = filtersFor(new URL(held[1].request().url()));
    newest.species[0].count = 14;
    await held[1].fulfill({ json: newest });
    await expect(countOf(page, 'Dunnock')).toHaveText('14');
    await expect(speciesList(page)).toHaveAttribute('aria-busy', 'false');
});

test('a visitor never sees names an answer read before their access narrowed', async ({ page }) => {
    const heldFilters: Route[] = [];
    const heldVisits: Route[] = [];
    let visitReads = 0;
    let filterReads = 0;
    await openExplorer(page, {
        guest: true,
        visitTotal: 1,
        visits: (route, body) => {
            visitReads += 1;
            if (visitReads > 1) {
                heldVisits.push(route);
                return;
            }
            return route.fulfill({ json: body });
        },
        filters: (route, url) => {
            filterReads += 1;
            if (filterReads === 1) {
                heldFilters.push(route);
                return;
            }
            return route.fulfill({ json: filtersFor(url) });
        }
    });
    await expect.poll(() => heldFilters.length).toBe(1);

    // The owner narrows what visitors see: the Explorer reads its history again.
    await page.evaluate(async () => {
        // The store the page uses, as the dev server serves it to the page.
        const path = '/src/lib/stores/detections.svelte.ts';
        const store: { detectionsStore: { publicHistoryVersion: number } } = await import(/* @vite-ignore */ path);
        store.detectionsStore.publicHistoryVersion += 1;
    });
    await expect.poll(() => heldVisits.length).toBe(1);

    // The answer read before the change arrives while the new results are still being read.
    const revoked = filtersFor(new URL(heldFilters[0].request().url()));
    revoked.species.push({ value: 'Revoked owl', display_name: 'Revoked Owl', common_name: 'Revoked Owl', scientific_name: 'Revoked owl', count: 4 });
    revoked.cameras.push('revoked-camera');
    await heldFilters[0].fulfill({ json: { ...revoked, camera_counts: { ...revoked.camera_counts, 'revoked-camera': 4 } } });
    await page.waitForTimeout(300);
    expect((await page.content()).toLowerCase()).not.toContain('revoked');

    await heldVisits[0].fulfill({ json: { total: 1, gap_seconds: 60, visits: [visit('v0', '2033-10-03T08:00:00Z')] } });
    await expect(countOf(page, 'Dunnock')).toHaveText('12');
    expect((await page.content()).toLowerCase()).not.toContain('revoked');
});
