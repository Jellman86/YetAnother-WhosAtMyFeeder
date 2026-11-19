import { expect, test, type Page, type Request } from '@playwright/test';
import { NOT_RECORDED_HEADER, replayFeeder } from '../accessibility-mock';

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
    /** Page errors, the app's console errors, failed or erroring scripts, and failed API answers. */
    failures: string[];
    /** URLs the browser reported failing to load, judged once the answers behind them are known. */
    unloaded: string[];
    /** API reads the replay marked as not recorded: gaps in the fixture, not faults in the bundle. */
    notRecorded: Set<string>;
    scripts: string[];
}

const RESOURCE_FAILURE = 'Failed to load resource:';

/** Records every error the page shows, and every script that loaded. */
function watch(page: Page): Watch {
    const seen: Watch = { failures: [], unloaded: [], notRecorded: new Set(), scripts: [] };
    page.on('console', (message) => {
        if (message.type() !== 'error') return;
        // The browser's own line for a failed load is judged by the answer behind it (`problems`).
        if (message.text().startsWith(RESOURCE_FAILURE)) seen.unloaded.push(message.location().url);
        else seen.failures.push(`console: ${message.text()} (${message.location().url})`);
    });
    page.on('pageerror', (error) => seen.failures.push(`page error: ${error.message}`));
    // A script still loading when the test moves on is cancelled by that navigation, not broken: the
    // browser reports it as aborted. Count it only if the page had not navigated since it was asked for.
    // A script the server cannot give is still caught, by its status below.
    let navigations = 0;
    const askedDuring = new WeakMap<Request, number>();
    page.on('framenavigated', (frame) => {
        if (frame === page.mainFrame()) navigations += 1;
    });
    page.on('request', (request) => askedDuring.set(request, navigations));
    page.on('requestfailed', (request) => {
        if (request.resourceType() !== 'script') return;
        const error = request.failure()?.errorText ?? '';
        if (error === 'net::ERR_ABORTED' && askedDuring.get(request) !== navigations) return;
        seen.failures.push(`script failed: ${request.url()} ${error}`);
    });
    page.on('response', (response) => {
        const url = new URL(response.url());
        if (response.request().resourceType() === 'script') {
            if (response.status() >= 400) seen.failures.push(`script ${response.status()}: ${response.url()}`);
            else seen.scripts.push(url.pathname);
            return;
        }
        if (!url.pathname.startsWith('/api/') || response.status() < 400) return;
        // Only the replay's own "not recorded" 404 is a gap; a recorded read that fails, or any 5xx, is a fault.
        if (response.status() === 404 && response.headers()[NOT_RECORDED_HEADER] === '1') seen.notRecorded.add(response.url());
        else seen.failures.push(`api ${response.status()}: ${response.request().method()} ${response.url()}`);
    });
    return seen;
}

/** Everything wrong so far: each failure, and each failed load that was not a gap in the fixture. */
function problems(seen: Watch): string[] {
    return [...seen.failures, ...seen.unloaded.filter((url) => !seen.notRecorded.has(url)).map((url) => `failed to load: ${url}`)];
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

// Settings is organised by task: six sections, each at its own address.
const SETTINGS_SECTIONS: ReadonlyArray<[section: string, name: string]> = [
    ['cameras', 'Cameras & connection'], ['identification', 'Identifying birds'], ['alerts', 'Alerts'],
    ['sharing', 'Sharing & integrations'], ['storage', 'Storage & upkeep'], ['display', 'Display']
];

// Every former tab's address, the section that now holds it, and the part it lands on.
const FORMER_SETTINGS_TABS: ReadonlyArray<[tab: string, section: string]> = [
    ['connection', 'cameras'], ['detection', 'identification'], ['models', 'identification'], ['beta', 'identification'],
    ['notifications', 'alerts'], ['integrations', 'sharing'], ['ai', 'sharing'], ['security', 'sharing'],
    ['data', 'storage'], ['maintenance', 'storage'], ['appearance', 'display'], ['accessibility', 'display']
];

test('every page draws its own content, with every script loaded and no console error', async ({ page }) => {
    const seen = await openFeeder(page);
    for (const [path, heading] of PAGES) {
        await page.goto(path);
        await expect(page.getByRole('heading', { level: 1, name: heading, exact: true }), path).toBeVisible({ timeout: 15_000 });
    }
    for (const [section, name] of SETTINGS_SECTIONS) {
        await page.goto(`/settings/${section}`);
        await expect(page.locator('[data-settings-navigation] [aria-current="page"]'), section).toHaveText(name, { timeout: 15_000 });
        await expect(page.locator('main').getByRole('heading', { level: 2 }).first(), section).toBeVisible();
    }
    expect(problems(seen)).toEqual([]);
});

test('every former Settings tab address lands on its section, at its part', async ({ page }) => {
    const seen = await openFeeder(page);
    for (const [tab, section] of FORMER_SETTINGS_TABS) {
        const name = SETTINGS_SECTIONS.find(([id]) => id === section)?.[1] ?? section;
        await page.goto(`/settings/${tab}`);
        await expect.poll(() => new URL(page.url()).pathname, { timeout: 15_000 }).toBe(`/settings/${section}`);
        expect(new URL(page.url()).hash, tab).toBe(`#${tab}`);
        await expect(page.locator('[data-settings-navigation] [aria-current="page"]'), tab).toHaveText(name);
        await expect(page.locator(`[data-settings-part="${tab}"]`), tab).toBeInViewport({ timeout: 15_000 });
    }
    expect(problems(seen)).toEqual([]);
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
    expect(problems(seen)).toEqual([]);
    for (const library of ['hls', 'leaflet-src', 'chartjs-runtime', 'markdown']) expect(loaded(seen, library), library).toBe(true);
});

test('the German locale loads and the app speaks it', async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem('preferred-language', 'de'));
    const seen = await openFeeder(page);
    await page.goto('/about');
    await expect(page.getByRole('heading', { level: 1, name: 'Über uns', exact: true })).toBeVisible({ timeout: 15_000 });
    await expect.poll(() => loaded(seen, 'de')).toBe(true);
    expect(problems(seen)).toEqual([]);
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
    expect(problems(seen)).toEqual([]);
});

test('a recorded read that fails fails the check, whatever the app does with it', async ({ page }) => {
    const seen = await openFeeder(page);
    // A server error on a read the recording holds, as a broken release would give.
    await page.route((url) => url.pathname === '/api/about/community', (route) => route.fulfill({ status: 500, json: { detail: 'Internal Server Error' } }));
    await page.goto('/about');
    await expect(page.getByRole('heading', { level: 1, name: 'About', exact: true })).toBeVisible({ timeout: 15_000 });
    await expect.poll(() => problems(seen).some((problem) => problem.includes('/api/about/community'))).toBe(true);
});
