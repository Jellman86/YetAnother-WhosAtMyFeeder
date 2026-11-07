import { expect, test, type Page, type Route } from '@playwright/test';

// The range check flags Red Junglefowl (the bird model's name for chickens) over the desk's 24 hours.
// "Needs your call" must say so, link to the Species page's checks, and never claim nothing is waiting.

const NOTHING_WAITING = 'Nothing waiting on you';

function windowSpecies(name: string, scientificName: string, overrides: Record<string, unknown> = {}) {
    return {
        species: name, common_name: name, scientific_name: scientificName, taxa_id: null,
        window_count: 8, window_prev_count: 0, window_delta: 8, window_percent: 0,
        window_visit_count: 3, window_prev_visit_count: 0, window_confirmed_count: 0,
        reported_nearby: false, ...overrides
    };
}

const flagged = {
    span: 'day', window_start: '2026-11-01T12:00:00Z', window_end: '2026-11-02T12:00:00Z',
    nearby_check: 'checked', nearby_radius_km: 50, nearby_days_back: 14,
    species: [windowSpecies('Red Junglefowl', 'Gallus gallus'), windowSpecies('Dunnock', 'Prunella modularis', { reported_nearby: true })]
};
const cleared = { ...flagged, species: [windowSpecies('Dunnock', 'Prunella modularis', { reported_nearby: true })] };
// eBird is set up but its lookup failed: a 200 whose rows cannot say whether anyone reported them.
const unmeasured = {
    ...flagged, nearby_check: 'unavailable', nearby_radius_km: null, nearby_days_back: null,
    species: flagged.species.map((row) => ({ ...row, reported_nearby: null }))
};
const switchedOff = { ...unmeasured, nearby_check: 'off' };
const UNAVAILABLE = 'The range check could not be read, so it is not known whether a species may be misnamed.';
const STALE = 'The range check could not be read again, so this list may be out of date.';
const unavailableResponse = (route: Route) => route.fulfill({ status: 503, json: { detail: 'Unavailable' } });

interface Served {
    leaderboard: (route: Route) => Promise<void> | void;
    requests: string[];
}

async function serve(page: Page, served: Served): Promise<void> {
    await page.route('https://fonts.googleapis.com/**', (route) => route.fulfill({ contentType: 'text/css', body: '' }));
    await page.route('https://fonts.gstatic.com/**', (route) => route.abort());
    await page.route((url) => url.pathname.startsWith('/api/'), async (route) => {
        const url = new URL(route.request().url());
        served.requests.push(`${route.request().method()} ${url.pathname}${url.search}`);
        if (url.pathname === '/api/leaderboard/species') return served.leaderboard(route);
        if (url.pathname === '/api/garden/domestic-birds') {
            return route.fulfill({ json: [{ key: 'chicken', declared: false, species_ids: [], scientific_names: ['Gallus gallus'] }] });
        }
        if (url.pathname === '/api/garden/domestic-birds/chicken/keep') {
            return route.fulfill({ json: { bird: 'chicken', declared: true, moved: 8, skipped: 0, remaining: 0 } });
        }
        if (url.pathname === '/api/events/review-queue') return route.fulfill({ json: { items: [], total: 0 } });
        if (url.pathname === '/api/events') return route.fulfill({ json: [] });
        // Supporting dashboard readings are unavailable; the panel depends only on the readings above.
        return route.fulfill({ status: 503, json: { detail: 'Supporting fixture reading unavailable.' } });
    });
}

test('a flagged species is named in Needs your call with a link to the Species page checks', async ({ page }) => {
    const served: Served = { requests: [], leaderboard: (route) => route.fulfill({ json: flagged }) };
    await serve(page, served);
    await page.goto('/browser-tests/dashboard-species-checks.html');
    const card = page.locator('[data-dashboard-review-queue]');
    await expect(card.locator('[data-review-queue-checks="waiting"]')).toContainText('1 species may be misnamed: Red Junglefowl.');
    await expect(card).toContainText('Only the camera backs it and no birder has reported it within 50 km.');
    await expect(card.locator('[data-review-queue-count]')).toHaveText('1');
    await expect(card).toContainText('Every visit in the last 24 hours has a species.');
    await expect(card).not.toContainText(NOTHING_WAITING);
    expect(served.requests).toContain('GET /api/leaderboard/species?span=day');

    await card.getByRole('button', { name: 'Open the checks on the Species page' }).click();
    await expect(page.locator('[data-navigated]')).toHaveText('/species?span=day#checks');
});

for (const [units, expected] of [['imperial', '31 mi'], ['british', '31 mi']] as const) {
    test(`the range check radius follows the owner's ${units} distance units (#911)`, async ({ page }) => {
        const served: Served = { requests: [], leaderboard: (route) => route.fulfill({ json: flagged }) };
        await serve(page, served);
        await page.goto(`/browser-tests/dashboard-species-checks.html?units=${units}`);
        const card = page.locator('[data-dashboard-review-queue]');
        await expect(card).toContainText(`Only the camera backs it and no birder has reported it within ${expected}.`);
        await expect(card).not.toContainText(' km');
    });
}

test('the owner keeps chickens from the Dashboard, and the panel then reads clear', async ({ page }) => {
    let reads = 0;
    const served: Served = { requests: [], leaderboard: (route) => route.fulfill({ json: reads++ === 0 ? flagged : cleared }) };
    await serve(page, served);
    await page.goto('/browser-tests/dashboard-species-checks.html');
    const card = page.locator('[data-dashboard-review-queue]');
    const offer = card.locator('[data-spotlight-kept-bird="chicken"]');
    await expect(offer).toContainText('Red Junglefowl may be a domestic bird: Chickens.');
    await offer.getByRole('button', { name: 'I keep Chickens: move to Garden' }).click();
    await expect(page.getByText('Moved 8 bird records to Garden. Chickens are now in Domestic birds you keep.')).toBeVisible();
    expect(served.requests).toContain('POST /api/garden/domestic-birds/chicken/keep');
    await expect(card).toContainText(`Every visit in the last 24 hours has a species. ${NOTHING_WAITING}.`);
    await expect(card.locator('[data-review-queue-count]')).toHaveCount(0);
});

test('nothing is claimed while the range check loads, nor when it cannot be read', async ({ page }) => {
    let release: () => void = () => undefined;
    const held = new Promise<void>((resolve) => { release = resolve; });
    const served: Served = {
        requests: [],
        leaderboard: async (route) => {
            await held;
            await route.fulfill({ status: 503, json: { detail: 'Unavailable' } });
        }
    };
    await serve(page, served);
    await page.goto('/browser-tests/dashboard-species-checks.html');
    const card = page.locator('[data-dashboard-review-queue]');
    await expect(card.locator('[data-review-queue-checks="loading"]')).toHaveCount(1);
    await expect(card).not.toContainText(NOTHING_WAITING);
    release();
    await expect(card).toContainText('The range check could not be read, so it is not known whether a species may be misnamed.');
    await expect(card).not.toContainText(NOTHING_WAITING);
    await expect(card.getByRole('button', { name: 'Try again' })).toBeVisible();
});

test('a visitor sees no Needs your call panel and no keep action', async ({ page }) => {
    const served: Served = { requests: [], leaderboard: (route) => route.fulfill({ json: flagged }) };
    await serve(page, served);
    await page.goto('/browser-tests/dashboard-species-checks.html?viewer=guest');
    await expect(page.locator('[data-dashboard-field-desk]')).toBeVisible();
    await expect(page.locator('[data-dashboard-review-queue]')).toHaveCount(0);
    await expect(page.locator('[data-spotlight-kept-bird]')).toHaveCount(0);
    expect(served.requests.filter((request) => request.includes('/api/leaderboard/species') || request.includes('/api/garden/domestic-birds'))).toEqual([]);
});

test('a 200 whose nearby evidence was unavailable is not read as zero checks', async ({ page }) => {
    const served: Served = { requests: [], leaderboard: (route) => route.fulfill({ json: unmeasured }) };
    await serve(page, served);
    await page.goto('/browser-tests/dashboard-species-checks.html');
    const card = page.locator('[data-dashboard-review-queue]');
    await expect(card).toContainText(UNAVAILABLE);
    await expect(card.getByRole('button', { name: 'Try again' })).toBeVisible();
    await expect(card).not.toContainText(NOTHING_WAITING);
    await expect(card.locator('[data-review-queue-count]')).toHaveCount(0);
});

test('a range check that is switched off is neither an error nor a claim that names were checked', async ({ page }) => {
    const served: Served = { requests: [], leaderboard: (route) => route.fulfill({ json: switchedOff }) };
    await serve(page, served);
    await page.goto('/browser-tests/dashboard-species-checks.html');
    const card = page.locator('[data-dashboard-review-queue]');
    await expect(card.locator('[data-review-queue-visits-clear]')).toHaveText('Every visit in the last 24 hours has a species.');
    await expect(card).not.toContainText(NOTHING_WAITING);
    await expect(card).not.toContainText(UNAVAILABLE);
    await expect(card.getByRole('button', { name: 'Try again' })).toHaveCount(0);
    await expect(card.locator('[data-review-queue-checks]')).toHaveCount(0);
});

test('a failed refresh keeps the last checks but says they may be out of date, and Try again reads them', async ({ page }) => {
    const answers = [(route: Route) => route.fulfill({ json: flagged }), unavailableResponse, (route: Route) => route.fulfill({ json: cleared })];
    const served: Served = { requests: [], leaderboard: (route) => (answers.shift() ?? unavailableResponse)(route) };
    await serve(page, served);
    await page.goto('/browser-tests/dashboard-species-checks.html');
    const card = page.locator('[data-dashboard-review-queue]');
    await expect(card).toContainText('1 species may be misnamed: Red Junglefowl.');
    await page.evaluate(() => window.dispatchEvent(new Event('test-page-refresh')));
    await expect(card.locator('[data-review-queue-checks-stale]')).toHaveText(STALE);
    await expect(card).toContainText('1 species may be misnamed: Red Junglefowl.');
    await card.locator('[data-review-queue-checks="stale"]').getByRole('button', { name: 'Try again' }).click();
    await expect(card).toContainText(`Every visit in the last 24 hours has a species. ${NOTHING_WAITING}.`);
    await expect(card.locator('[data-review-queue-checks-stale]')).toHaveCount(0);
});

test('a kept bird whose reload fails is not offered again, and the list is marked out of date', async ({ page }) => {
    let reads = 0;
    const served: Served = {
        requests: [],
        leaderboard: (route) => (reads++ === 0 ? route.fulfill({ json: flagged }) : unavailableResponse(route))
    };
    await serve(page, served);
    await page.goto('/browser-tests/dashboard-species-checks.html');
    const card = page.locator('[data-dashboard-review-queue]');
    await card.getByRole('button', { name: 'I keep Chickens: move to Garden' }).click();
    await expect(page.getByText('Moved 8 bird records to Garden. Chickens are now in Domestic birds you keep.')).toBeVisible();
    await expect(card.locator('[data-review-queue-checks-stale]')).toHaveText(STALE);
    await expect(card.locator('[data-spotlight-kept-bird]')).toHaveCount(0);
    expect(served.requests.filter((request) => request.startsWith('POST'))).toEqual(['POST /api/garden/domestic-birds/chicken/keep']);
});
