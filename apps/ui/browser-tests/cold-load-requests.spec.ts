import { expect, test, type Page } from '@playwright/test';

// The real App shell, as a visitor opens it: history, live updates and the route's own reads all
// start together. Each reading is asked for once; a first history read is not an edit to refresh after.
const owner = { auth_required: false, is_authenticated: true, needs_initial_setup: false, birdnet_enabled: true };
const guest = {
    auth_required: true, is_authenticated: false, public_access_enabled: true, needs_initial_setup: false,
    birdnet_enabled: true, public_access_show_audio: true, public_access_rate_limit_per_minute: 30
};
const dailySummary = {
    audio_confirmations: 0, hourly_distribution: Array(24).fill(0), hourly_visits: Array(24).fill(0),
    latest_detection: null, top_species: [], total_count: 0, visit_count: 0, camera_visits: []
};
const audioSummary = { daily_counts: [], hourly_counts: [], source_count: 0, sources: [], species_count: 0, top_species: [], total: 0 };

async function countColdLoadReads(page: Page, path: string, status: Record<string, unknown>): Promise<Map<string, number>> {
    const reads = new Map<string, number>();
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route('**/health', route => route.fulfill({ json: { status: 'healthy' } }));
    await page.route(url => url.pathname.startsWith('/api/'), async route => {
        const pathname = new URL(route.request().url()).pathname;
        reads.set(pathname, (reads.get(pathname) ?? 0) + 1);
        const responses: Record<string, unknown> = {
            '/api/auth/status': status,
            '/api/settings': { birdnet_enabled: true, classification_threshold: 0.6 },
            '/api/settings/public': {},
            '/api/events': [],
            '/api/events/count': { count: 0 },
            '/api/events/filters': { species: [], cameras: [] },
            '/api/events/new-species': { items: [] },
            '/api/visits': { total: 0, gap_seconds: 60, visits: [] },
            '/api/stats/daily-summary': dailySummary,
            '/api/audio/summary': audioSummary,
            '/api/audio/recent': [],
            '/api/classifier/labels': { labels: ['Dunnock'] },
            '/api/update-status': { update_available: false }
        };
        if (pathname === '/api/sse') return route.abort();
        // The recent history is the slowest first read, so it settles after the route has mounted.
        if (pathname === '/api/events' || pathname === '/api/events/count') await new Promise(resolve => setTimeout(resolve, 600));
        if (pathname in responses) return route.fulfill({ json: responses[pathname] });
        return route.fulfill({ status: 503, json: { detail: 'Not part of this fixture' } });
    });
    await page.goto(path);
    await page.waitForTimeout(5_000);
    return reads;
}

for (const [visitor, status] of [['owner', owner], ['guest', guest]] as const) {
    test(`a cold Dashboard load as the ${visitor} reads each summary once and no classifier labels`, async ({ page }) => {
        const reads = await countColdLoadReads(page, '/', status);
        expect(reads.get('/api/events')).toBe(1);
        expect(reads.get('/api/events/count')).toBe(1);
        expect(reads.get('/api/stats/daily-summary')).toBe(1);
        expect(reads.get('/api/visits')).toBe(1);
        expect(reads.get('/api/audio/summary')).toBe(1);
        expect(reads.get('/api/classifier/labels') ?? 0).toBe(0);
    });

    test(`a cold Explorer load as the ${visitor} reads its visits once and no classifier labels`, async ({ page }) => {
        const reads = await countColdLoadReads(page, '/events', status);
        expect(reads.get('/api/events')).toBe(1);
        expect(reads.get('/api/visits')).toBe(1);
        expect(reads.get('/api/classifier/labels') ?? 0).toBe(0);
    });
}
