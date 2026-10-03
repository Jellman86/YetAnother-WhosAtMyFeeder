import { test, expect } from '@playwright/test';

test('recent sightings link to the exact capture even when it has no clip', async ({ page }) => {
    const sightings = [
        { frigate_event: 'clip-available', has_clip: true },
        { frigate_event: 'snapshot only & visit', has_clip: false }
    ].map((capture, index) => ({
        ...capture,
        display_name: 'Eurasian Blue Tit', scientific_name: 'Cyanistes caeruleus',
        camera_name: 'birdcam', detection_time: `2026-10-03T09:0${index}:00Z`, score: 0.8
    }));
    const errors: string[] = [];
    page.on('pageerror', error => { if (!error.message.includes('ResizeObserver loop')) errors.push(error.message); });
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route(url => url.pathname.startsWith('/api/'), async route => {
        const path = new URL(route.request().url()).pathname;
        if (path.endsWith('/stats')) return route.fulfill({ json: {
            species_name: 'Cyanistes caeruleus', scientific_name: 'Cyanistes caeruleus', common_name: 'Eurasian Blue Tit',
            total_sightings: 2, first_seen: sightings[0].detection_time, last_seen: sightings[1].detection_time,
            cameras: [{ camera_name: 'birdcam', count: 2, percentage: 100 }], hourly_distribution: Array(24).fill(0),
            daily_distribution: Array(7).fill(0), monthly_distribution: Array(12).fill(0),
            avg_confidence: 0.8, min_confidence: 0.8, max_confidence: 0.8, recent_sightings: sightings
        } });
        if (path.endsWith('.jpg')) return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="120"><rect width="160" height="120" fill="#0f766e"/></svg>' });
        if (path.endsWith('/range')) return route.fulfill({ json: { available: false } });
        return route.fulfill({ json: {} });
    });
    await page.goto('/browser-tests/owner-history.html?surface=species');
    const links = page.locator('[data-species-recent-sightings]').getByRole('link', { name: 'Open Eurasian Blue Tit capture' });
    await expect(links).toHaveCount(2);
    for (const [index, capture] of sightings.entries()) {
        await expect(links.nth(index)).toHaveAttribute('href', `/events?event=${encodeURIComponent(capture.frigate_event)}`);
        expect(await links.nth(index).getAttribute('aria-disabled')).not.toBe('true');
    }
    await links.nth(1).focus();
    await expect(links.nth(1)).toBeFocused();
    // Stop at the navigation boundary; the application router is outside this fixture.
    await page.route('**/events?event=*', route => route.fulfill({ contentType: 'text/html', body: '<main>Exact capture destination</main>' }));
    await page.keyboard.press('Enter');
    await expect.poll(() => new URL(page.url()).pathname).toBe('/events');
    expect([...new URL(page.url()).searchParams.entries()]).toEqual([['event', sightings[1].frigate_event]]);
    expect(errors).toEqual([]);
});

test('Explorer sends the multiple-species filter for visits, captures and counts and clears it', async ({ page }) => {
    const requests: URL[] = [];
    const errors: string[] = [];
    page.on('pageerror', error => { if (!error.message.includes('ResizeObserver loop')) errors.push(error.message); });
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route(url => url.pathname.startsWith('/api/'), async route => {
        const url = new URL(route.request().url());
        requests.push(url);
        if (url.pathname === '/api/events/filters') return route.fulfill({ json: { species: [], cameras: ['birdcam'] } });
        if (url.pathname === '/api/events') return route.fulfill({ json: [] });
        if (url.pathname === '/api/visits') return route.fulfill({ json: { visits: [], total: 0, gap_seconds: 120 } });
        if (url.pathname === '/api/events/count') return route.fulfill({ json: { count: 0 } });
        if (url.pathname === '/api/events/hidden-count') return route.fulfill({ json: { hidden_count: 0 } });
        if (url.pathname === '/api/classifier/labels') return route.fulfill({ json: { labels: [] } });
        return route.fulfill({ json: {} });
    });
    await page.goto('/browser-tests/owner-history.html?surface=explorer');
    const filter = page.getByRole('button', { name: 'Multiple bird species', exact: true });
    if (!await filter.isVisible()) await page.locator('[data-explorer-filter-toggle]').click();
    await expect(filter).toHaveAttribute('aria-pressed', 'false');
    await filter.click();
    await expect(filter).toHaveAttribute('aria-pressed', 'true');
    await expect.poll(() => requests.some(url => url.pathname === '/api/visits' && url.searchParams.get('multiple_species_only') === 'true')).toBe(true);
    const grouping = page.getByRole('group', { name: 'Group captures' });
    await grouping.getByRole('button', { name: 'Captures', exact: true }).click();
    for (const path of ['/api/events', '/api/events/count']) {
        await expect.poll(() => requests.some(url => url.pathname === path && url.searchParams.get('multiple_species_only') === 'true')).toBe(true);
    }
    const beforeClear = requests.length;
    await page.getByRole('button', { name: 'Clear all', exact: true }).click();
    await expect(filter).toHaveAttribute('aria-pressed', 'false');
    for (const path of ['/api/events', '/api/events/count']) {
        await expect.poll(() => requests.slice(beforeClear).some(url => url.pathname === path && !url.searchParams.has('multiple_species_only'))).toBe(true);
    }
    await grouping.getByRole('button', { name: 'Visits', exact: true }).click();
    await expect.poll(() => requests.slice(beforeClear).some(url => url.pathname === '/api/visits' && !url.searchParams.has('multiple_species_only'))).toBe(true);
    expect(errors).toEqual([]);
});

test('incoming capture refresh waits for the current visit read and updates membership', async ({ page }) => {
    let reads = 0;
    let release: () => void = () => undefined;
    const held = new Promise<void>(resolve => { release = resolve; });
    const record = { frigate_event: 'first', display_name: 'Turdus merula', scientific_name: 'Turdus merula', common_name: 'Eurasian Blackbird', camera_name: 'birdcam', detection_time: '2026-10-03T09:00:00Z', score: 0.95, has_clip: false };
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route(url => url.pathname.startsWith('/api/'), async route => {
        const path = new URL(route.request().url()).pathname;
        if (path === '/api/visits') {
            const current = ++reads;
            if (current === 1) await held;
            return route.fulfill({ json: { total: 1, gap_seconds: 60, visits: [{ visit_id: 'first', start_time: record.detection_time, end_time: record.detection_time, capture_count: current === 1 ? 13 : 14, best_score: 0.95, needs_review: false, audio_confirmed: false, representative: record, latest: record, peak_capture: null }] } });
        }
        if (path.endsWith('/filters')) return route.fulfill({ json: { species: [], cameras: [], camera_counts: {}, totals: { total: 14, favorites: 0, audio_matched: 0 } } });
        if (path.endsWith('.jpg')) return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="120"/>' });
        if (path.endsWith('/labels') || path.endsWith('/species')) return route.fulfill({ json: [] });
        return route.fulfill({ json: { count: 0 } });
    });
    await page.goto('/browser-tests/owner-history.html?surface=explorer');
    await expect.poll(() => reads).toBe(1);
    await page.getByRole('button', { name: 'Notify new capture' }).click();
    // Allow the scheduled refresh to run while the first response is still held.
    await expect(page.locator('[data-visit-captures]')).toHaveCount(0);
    await page.waitForTimeout(900);
    expect(reads).toBe(1);
    release();
    await expect(page.locator('[data-visit-captures="first"] [data-visit-captures-toggle]')).toContainText('14 captures');
    expect(reads).toBe(2);
});
