import { expect, test, type Route } from '@playwright/test';

// The real App shell: an Explorer left while its results are being read starts no count read for
// a page that is gone (#1097).
const guest = {
    auth_required: true, is_authenticated: false, public_access_enabled: true, needs_initial_setup: false,
    birdnet_enabled: true, public_access_show_audio: true, public_access_rate_limit_per_minute: 30
};
const representative = {
    frigate_event: 'v0', display_name: 'Prunella modularis', scientific_name: 'Prunella modularis', common_name: 'Dunnock',
    camera_name: 'birdcam', detection_time: '2033-10-03T08:00:00Z', score: 0.91, has_clip: false
};
const visits = {
    total: 1, gap_seconds: 60,
    visits: [{ visit_id: 'v0', start_time: representative.detection_time, end_time: representative.detection_time, capture_count: 1, best_score: 0.91, needs_review: false, audio_confirmed: false, representative, latest: representative, peak_capture: null }]
};

test('an Explorer left while its results are read asks for no counts afterwards', async ({ page }) => {
    const heldVisits: Route[] = [];
    let filterReads = 0;
    await page.route('https://fonts.googleapis.com/**', (route) => route.fulfill({ contentType: 'text/css', body: '' }));
    await page.route('https://fonts.gstatic.com/**', (route) => route.abort());
    await page.route('**/health', (route) => route.fulfill({ json: { status: 'healthy' } }));
    await page.route((url) => url.pathname.startsWith('/api/'), (route) => {
        const pathname = new URL(route.request().url()).pathname;
        if (pathname === '/api/sse') return route.abort();
        if (pathname === '/api/visits' && heldVisits.length === 0) {
            heldVisits.push(route);
            return;
        }
        if (pathname === '/api/events/filters') filterReads += 1;
        const responses: Record<string, unknown> = {
            '/api/auth/status': guest,
            '/api/settings/public': {},
            '/api/visits': visits,
            '/api/events': [],
            '/api/events/count': { count: 0 },
            '/api/events/filters': { species: [], cameras: [] },
            '/api/garden/visits': { visits: [], total: 0, capture_total: 0, limit: 200, offset: 0 },
            '/api/classifier/labels': { labels: [] },
            '/api/version': { version: 'unknown', base_version: 'unknown' }
        };
        if (pathname in responses) return route.fulfill({ json: responses[pathname] });
        return route.fulfill({ status: 503, json: { detail: 'Not part of this fixture' } });
    });
    await page.goto('/events');
    await expect.poll(() => heldVisits.length).toBe(1);

    // A phone keeps the navigation in a drawer behind Menu; a desktop shows it.
    const menu = page.getByRole('button', { name: 'Menu', exact: true });
    if (await menu.isVisible()) await menu.click();
    await page.getByRole('navigation').getByRole('button', { name: 'Leaderboard', exact: true }).first().click();
    await expect(page.locator('[data-events-filter-bar]')).toHaveCount(0);
    await heldVisits[0].fulfill({ json: visits });
    await page.waitForTimeout(500);
    expect(filterReads).toBe(0);
});
