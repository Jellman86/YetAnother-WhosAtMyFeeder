import { expect, test, type Page } from '@playwright/test';
import { replayFeeder } from '../accessibility-mock';

/**
 * The production bundle, served from `dist`, on the replayed feeder. The main suite runs on the
 * dev server, which does not split code, so only this shows whether the built chunks start: every
 * route draws its own content, every chunk the build emitted loads, the German locale and the
 * lazily loaded features (charts, the map, a record's markdown, the video library) work, and the
 * console stays free of errors throughout.
 */

// Answers for what the recording does not hold, so a gap in the fixture is not mistaken for a fault.
const FIXTURE_GAPS: Record<string, unknown> = {
    '/api/diagnostics/workspace': {
        workspace_schema_version: 'fixture',
        backend_diagnostics: {
            captured_at: new Date().toISOString(), capacity: 500, total_events: 0, total_occurrences: 0,
            filtered_events: 0, returned_events: 0, severity_counts: {}, component_counts: {}, events: []
        },
        focused_diagnostics: {}, health: { status: 'healthy' }, connections: null, classifier: {},
        taxonomy_repair: {}, maintenance_coordinator: {}, startup_warnings: []
    },
    '/api/frigate/cameras/status': { cameras: [] },
    '/api/frigate/config': { cameras: {} },
    '/api/models/available': [],
    '/api/models/installed': [],
    '/api/models/activity': { activity: {} },
    '/api/range-filter/status': {
        enabled: false, filtering: false, reason: 'needs_ebird_key', problem: null, source: 'ebird',
        location_precision: 'exact', region_level_setting: 'county', ebird_configured: false, birdnet_enabled: true,
        region: null, species_in_range: null, region_species_total: null, heard_species: 0, heard_only_species: 0,
        refreshed_at: null, next_refresh_at: null, stale_after: null, refreshing: false, last_error: null,
        last_attempt_at: null, model: null, recent: { window_days: 30, fallback: 0, skipped: 0 }
    },
    '/api/range-filter/skips': { items: [] },
    '/api/stats/ai/usage': { span: '30d', from_date: '2026-10-17T00:00:00', to_date: '2026-11-16T00:00:00', input_tokens: 0, output_tokens: 0, total_tokens: 0, daily: [] },
    '/api/maintenance/last-runs': { runs: [] },
    '/api/garden/identification': { country: 'GBR', catalogue_ready: true, busy: false, error: null, models: [], automatic_message: '' },
    '/api/garden/motion': { cameras: [], installed: false, state: 'disabled', message: 'Off' },
    '/api/classifier/quarantine/revalidation': { attempt: { state: 'idle' }, profile: null },
    '/api/location/reverse-geocode': { country: 'United Kingdom', place_guess: 'Rutland', state: 'England' }
};

// The recording holds no written analysis and has the AI integration off, so the analysis is
// turned on and each recorded detection is given one in markdown, which a record draws with its
// lazily loaded markdown code.
const ANALYSIS = '**Feeding.** A short visit to the *seed feeder*, then off to the hedge.';

function withAnalysisValues(json: unknown): unknown {
    if (Array.isArray(json)) return json.map(withAnalysisValues);
    if (json === null || typeof json !== 'object') return json;
    const entries = Object.entries(json).map(([key, value]) => [key, key === 'ai_analysis' && value === null ? ANALYSIS : withAnalysisValues(value)]);
    return Object.fromEntries(entries);
}

function withAnalysis(json: unknown, url: URL): unknown {
    if (url.pathname === '/api/settings' && json !== null && typeof json === 'object') return { ...json, llm_enabled: true, llm_ready: true };
    return withAnalysisValues(json);
}

interface Watch {
    problems: string[];
    scripts: string[];
}

/**
 * The browser's own line for an API read the recording does not hold (a record's per-detection
 * reads, for one). That is a gap in the fixture, not in the bundle: the app's own errors, page
 * errors and every script still count.
 */
function isFixtureGap(text: string, url: string): boolean {
    return text.startsWith('Failed to load resource:') && new URL(url).pathname.startsWith('/api/');
}

/** Records every console error, page error and script that did not load, and every script that did. */
function watch(page: Page): Watch {
    const seen: Watch = { problems: [], scripts: [] };
    page.on('console', (message) => {
        if (message.type() !== 'error' || isFixtureGap(message.text(), message.location().url)) return;
        seen.problems.push(`console: ${message.text()} (${message.location().url})`);
    });
    page.on('pageerror', (error) => seen.problems.push(`page error: ${error.message}`));
    page.on('requestfailed', (request) => {
        if (request.resourceType() === 'script') seen.problems.push(`script failed: ${request.url()} ${request.failure()?.errorText ?? ''}`);
    });
    page.on('response', (response) => {
        if (response.request().resourceType() !== 'script') return;
        if (response.status() >= 400) seen.problems.push(`script ${response.status()}: ${response.url()}`);
        else seen.scripts.push(new URL(response.url()).pathname);
    });
    return seen;
}

async function openFeeder(page: Page): Promise<Watch> {
    const seen = watch(page);
    await replayFeeder(page, 'light', FIXTURE_GAPS, withAnalysis);
    // nginx serves the start-up file in production; the preview server has none to give.
    await page.route((url) => url.pathname === '/startup-status.json', (route) => route.fulfill({ status: 204, body: '' }));
    // The live stream opens and ends at once; the app reconnects as it does after any drop.
    await page.route((url) => url.pathname === '/api/sse', (route) => route.fulfill({ status: 200, contentType: 'text/event-stream', body: '' }));
    await page.setViewportSize({ width: 1440, height: 900 });
    return seen;
}

const loaded = (seen: Watch, chunk: string): boolean => seen.scripts.some((path) => path.split('/').pop()?.startsWith(`${chunk}-`));

const PAGES: ReadonlyArray<[path: string, heading: string]> = [
    ['/', 'Last 24 hours'],
    ['/events', 'Explorer'],
    ['/events?visitors=garden&review=pending', 'Explorer'],
    ['/observations/new', 'Add observation'],
    ['/species', 'Leaderboard'],
    ['/audio', 'Audio history'],
    ['/notifications', 'Notifications'],
    ['/diagnostics/model-eval', 'Model evaluation'],
    ['/about', 'About'],
    ['/system-health', 'Health'],
    ['/no-such-page', 'This page does not exist']
];

const SETTINGS_TABS: ReadonlyArray<[path: string, tab: string]> = [
    ['connection', 'Connection'], ['detection', 'Detection'], ['models', 'Models'], ['integrations', 'Integrations'],
    ['ai', 'AI'], ['notifications', 'Notifications'], ['security', 'Security'], ['data', 'Data'],
    ['maintenance', 'Maintenance'], ['beta', 'Beta features'], ['appearance', 'Appearance'], ['accessibility', 'Accessibility']
];

test('every page draws its own content, with every script loaded and no console error', async ({ page }) => {
    const seen = await openFeeder(page);
    for (const [path, heading] of PAGES) {
        await page.goto(path);
        await expect(page.getByRole('heading', { level: 1, name: heading, exact: true }), path).toBeVisible({ timeout: 15_000 });
    }
    for (const [tab, name] of SETTINGS_TABS) {
        await page.goto(`/settings/${tab}`);
        await expect(page.locator('[data-settings-navigation] [aria-current="page"]'), tab).toHaveText(name, { timeout: 15_000 });
        await expect(page.locator('main').getByRole('heading', { level: 2 }).first(), tab).toBeVisible();
    }
    expect(seen.problems).toEqual([]);
});

test('every chunk the build emitted loads and runs', async ({ page }) => {
    // @ts-expect-error The UI has no Node type package; the test runner runs in Node.
    const { readdirSync } = await import('node:fs');
    const chunks = (readdirSync('dist/assets') as string[]).filter((file) => file.endsWith('.js'));
    expect(chunks.length).toBeGreaterThan(10);
    const seen = await openFeeder(page);
    await page.goto('/about');
    await expect(page.getByRole('heading', { level: 1, name: 'About', exact: true })).toBeVisible({ timeout: 15_000 });
    const failures = await page.evaluate(async (files) => {
        const failed: string[] = [];
        for (const file of files) {
            try {
                await import(/* @vite-ignore */ `/assets/${file}`);
            } catch (error) {
                failed.push(`${file}: ${error instanceof Error ? error.message : String(error)}`);
            }
        }
        return failed;
    }, chunks);
    expect(failures).toEqual([]);
    expect(seen.problems).toEqual([]);
    for (const library of ['hls', 'leaflet-src', 'chartjs-runtime', 'markdown']) expect(loaded(seen, library), library).toBe(true);
});

test('the German locale loads and the app speaks it', async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem('preferred-language', 'de'));
    const seen = await openFeeder(page);
    await page.goto('/about');
    await expect(page.getByRole('heading', { level: 1, name: 'Über uns', exact: true })).toBeVisible({ timeout: 15_000 });
    await expect.poll(() => loaded(seen, 'de')).toBe(true);
    expect(seen.problems).toEqual([]);
});

test('charts, the map and a record with its written analysis draw from their lazily loaded code', async ({ page }) => {
    const seen = await openFeeder(page);
    await page.goto('/audio');
    await expect(page.getByRole('heading', { level: 1, name: 'Audio history', exact: true })).toBeVisible({ timeout: 15_000 });
    await expect(page.locator('main canvas').first()).toBeVisible();
    await expect.poll(() => loaded(seen, 'chartjs-runtime')).toBe(true);

    await page.goto('/settings/integrations');
    await expect(page.locator('.leaflet-container').first()).toBeVisible({ timeout: 15_000 });
    await expect.poll(() => loaded(seen, 'leaflet-src')).toBe(true);

    await page.goto('/events');
    await page.locator('[data-detection-card]').first().click();
    // Bold text drawn from the analysis's markdown shows the markdown code loaded and ran.
    await expect(page.locator('[data-record-ai-analysis] strong', { hasText: 'Feeding.' })).toBeVisible({ timeout: 15_000 });
    await expect.poll(() => loaded(seen, 'markdown')).toBe(true);
    expect(seen.problems).toEqual([]);
});
