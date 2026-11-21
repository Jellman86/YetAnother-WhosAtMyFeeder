import { test, expect, type Page, type Route } from '@playwright/test';

const image = '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"><rect width="640" height="360" fill="#147d64"/><circle cx="330" cy="155" r="50" fill="#f5ce66"/></svg>';

function portrait(event = 'dunnock', name = 'Dunnock') {
    return {
        scope: 'shared', shared_days: 30, started_at: '2026-09-01T08:00:00Z',
        visits: 1234, detections: 5678, species: 12,
        busiest_day: { date: '2026-09-23', visits: 149 },
        newest_arrival: { species: 'Prunella modularis', display_name: 'Dunnock', first_seen: '2026-09-21T08:00:00Z' },
        latest_visit: {
            frigate_event: event, display_name: name, scientific_name: 'Prunella modularis',
            detection_time: '2026-10-03T08:00:00Z',
            image_url: `/api/about/showcase/${event}.jpg`, film_url: `/api/about/showcase/${event}.webm`
        }
    };
}

// A default install's report: image work runs in worker processes that have started.
const RUNNING = { runtime_source: 'worker', image_execution_mode: 'subprocess', active_model_installed: true, effective_model_id: 'Bird classifier', active_provider: 'CPU' };

async function open(page: Page, onPortrait: (route: Route) => Promise<void>, classifier: Record<string, unknown> = RUNNING, activity: Record<string, string> = {}, version = '2.9.15') {
    page.on('pageerror', error => { throw error; });
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route('**/ready', route => route.fulfill({ json: { status: 'ready', startup_started_at: '2026-09-01T08:00:00Z' } }));
    await page.route(url => url.pathname.startsWith('/api/'), async route => {
        const path = new URL(route.request().url()).pathname;
        if (path === '/api/about/portrait') return onPortrait(route);
        if (path.endsWith('.jpg')) return route.fulfill({ contentType: 'image/svg+xml', body: image });
        if (path.endsWith('.webm')) return route.fulfill({ contentType: 'video/webm', body: 'fixture' });
        if (path === '/api/version') return route.fulfill({ json: { version, base_version: '2.9.15', git_hash: 'fixture', branch: 'dev' } });
        if (path === '/api/about/community') return route.fulfill({ json: { enabled: true, active_installs: 812 } });
        if (path === '/api/classifier/status') return route.fulfill({ json: classifier });
        if (path === '/api/models/activity') return route.fulfill({ json: { activity } });
        if (path === '/api/stats/uptime') return route.fulfill({ json: { buckets: [], longest_gap_minutes: 0, availability_percent: 100 } });
        if (path === '/api/update-status') return route.fulfill({ json: { enabled: false, update_available: false } });
        throw new Error(`Unexpected About fixture API request: ${path}`);
    });
    await page.goto('/browser-tests/about-portrait.html');
    // The fixture mounts after its asynchronous locale bundle is ready.
    await expect(page.locator('main')).toBeVisible({ timeout: 15000 });
}

test('a public history change removes the old film and facts before the next portrait resolves', async ({ page }, testInfo) => {
    let reads = 0;
    let pending: Route | undefined;
    await open(page, async route => {
        reads += 1;
        if (reads === 1) await route.fulfill({ json: portrait() });
        else pending = route;
    });
    await expect(page.locator('[data-feeder-portrait] video')).toHaveCount(1);
    await page.screenshot({ path: testInfo.outputPath('about-portrait.png'), fullPage: true });
    await page.evaluate(() => window.aboutPortrait!.invalidate());
    await expect.poll(() => reads).toBe(2);
    await expect(page.locator('[data-feeder-portrait]')).toHaveCount(0);
    await expect(page.locator('video')).toHaveCount(0);
    await pending!.fulfill({ json: portrait('robin', 'European Robin') });
    await expect(page.locator('[data-feeder-portrait-visit]')).toHaveAccessibleName(/European Robin/);
});

test('an older portrait response cannot replace a newer public projection', async ({ page }) => {
    // Let an old response reach the component even if the caller aborts: this exercises its
    // response guard independently of the browser's request cancellation.
    await page.addInitScript(() => {
        const original = window.fetch;
        window.fetch = (input, options) => original(input, String(input).includes('/about/portrait') ? { ...options, signal: undefined } : options);
    });
    let reads = 0;
    let old: Route | undefined;
    await open(page, async route => {
        reads += 1;
        if (reads === 1) old = route;
        else await route.fulfill({ json: portrait('robin', 'European Robin') });
    });
    await expect.poll(() => reads).toBe(1);
    await page.evaluate(() => window.aboutPortrait!.invalidate());
    await expect(page.locator('[data-feeder-portrait-visit]')).toHaveAccessibleName(/European Robin/);
    await old!.fulfill({ json: portrait() });
    await page.waitForTimeout(100);
    await expect(page.locator('[data-feeder-portrait-visit]')).toHaveAccessibleName(/European Robin/);
});

test('failed refreshes stay clear and unmount aborts the active portrait read', async ({ page }) => {
    await page.addInitScript(() => {
        const original = window.fetch;
        (window as Window & { portraitAborts?: number }).portraitAborts = 0;
        window.fetch = (input, options) => {
            if (String(input).includes('/about/portrait')) {
                options?.signal?.addEventListener('abort', () => {
                    const tracked = window as Window & { portraitAborts?: number };
                    tracked.portraitAborts = (tracked.portraitAborts ?? 0) + 1;
                }, { once: true });
            }
            return original(input, options);
        };
    });
    let reads = 0;
    let pending: Route | undefined;
    await open(page, async route => {
        reads += 1;
        if (reads === 1) await route.fulfill({ json: portrait() });
        else if (reads === 2) await route.fulfill({ status: 503, json: { detail: 'Refresh failed' } });
        else pending = route;
    });
    await expect(page.locator('[data-feeder-portrait]')).toBeVisible();
    await page.evaluate(() => window.aboutPortrait!.invalidate());
    await expect.poll(() => reads).toBe(2);
    await expect(page.locator('[data-feeder-portrait]')).toHaveCount(0);
    await page.evaluate(() => window.aboutPortrait!.invalidate());
    await expect.poll(() => reads).toBe(3);
    await page.evaluate(() => window.aboutPortrait!.setMounted(false));
    await expect.poll(() => page.evaluate(() => (window as Window & { portraitAborts?: number }).portraitAborts)).toBe(1);
    await pending!.fulfill({ json: portrait() });
    await expect(page.locator('[data-feeder-portrait]')).toHaveCount(0);
});

test('the newest arrival has a usable touch target', async ({ page }) => {
    await open(page, route => route.fulfill({ json: portrait() }));
    const arrival = page.locator('[data-feeder-portrait-arrival]');
    await expect(arrival).toBeVisible();
    const box = await arrival.boundingBox();
    expect(box?.width ?? 0).toBeGreaterThanOrEqual(44);
    expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
});

for (const viewport of [{ width: 1280, height: 800 }, { width: 390, height: 844 }]) {
    test(`a slow portrait lands in its own shape without moving the page at ${viewport.width}px`, async ({ page }) => {
        await page.setViewportSize(viewport);
        await page.addInitScript(() => {
            const tracked = window as Window & { layoutShifts?: { value: number; sources: string[] }[] };
            tracked.layoutShifts = [];
            new PerformanceObserver(list => {
                for (const entry of list.getEntries() as (PerformanceEntry & { value: number; hadRecentInput: boolean; sources?: { node?: Node | null }[] })[]) {
                    if (entry.hadRecentInput) continue;
                    const sources = (entry.sources ?? []).map(source => source.node instanceof Element
                        ? `${source.node.tagName.toLowerCase()}.${String(source.node.className).slice(0, 60)}`
                        : source.node?.nodeName ?? 'unknown');
                    tracked.layoutShifts?.push({ value: entry.value, sources });
                }
            }).observe({ type: 'layout-shift', buffered: true });
        });
        let release: () => void = () => undefined;
        const released = new Promise<void>(resolve => { release = resolve; });
        await open(page, async route => {
            await released;
            await route.fulfill({ json: portrait() });
        });
        const prose = page.locator('#about-project .max-w-prose');
        const placeholder = page.locator('[data-feeder-portrait-loading]');
        await expect(placeholder).toBeVisible();
        await expect(placeholder).toHaveAttribute('aria-busy', 'true');
        await expect(page.getByRole('status').filter({ hasText: "Loading this feeder's facts" })).toHaveCount(1);
        await page.waitForTimeout(300);
        const before = (await prose.boundingBox())?.y ?? -1;

        release();
        await expect(page.locator('[data-feeder-portrait-visit]')).toBeVisible();
        await expect(placeholder).toHaveCount(0);
        await page.waitForTimeout(500);
        const after = (await prose.boundingBox())?.y ?? -2;
        expect(Math.abs(after - before)).toBeLessThanOrEqual(1);
        const shifts = await page.evaluate(() => (window as Window & { layoutShifts?: { value: number; sources: string[] }[] }).layoutShifts ?? []);
        const total = shifts.reduce((sum, shift) => sum + shift.value, 0);
        expect(total, JSON.stringify(shifts, null, 1)).toBeLessThan(0.05);
    });
}

test('a failed portrait read leaves one quiet line, not an empty gap or a stuck placeholder', async ({ page }) => {
    await open(page, route => route.fulfill({ status: 503, json: { detail: 'Portrait unavailable' } }));
    await expect(page.locator('[data-feeder-portrait-unavailable]')).toHaveText("This feeder's facts could not be loaded.");
    await expect(page.locator('[data-feeder-portrait-loading]')).toHaveCount(0);
    await expect(page.locator('[data-feeder-portrait]')).toHaveCount(0);
});

// About states the model by the rule Settings, the wizard and Garden use, and reports inference
// health beside it. Each report below is one the shared readiness fixture names.
for (const [name, report, state, health] of [
    ['running in workers', RUNNING, 'Running', null],
    ['an in-app model still loading', { ...RUNNING, runtime_source: 'in_process', image_execution_mode: 'in_process' }, 'Loading', null],
    ['an in-app model that could not load', { ...RUNNING, runtime_source: 'in_process', loaded: false, error: 'runtime could not open the model' }, 'Could not load', null],
    ['a failed in-app fallback', { ...RUNNING, runtime_source: 'in_process_fallback', loaded: false, error: 'runtime could not open the model' }, 'Could not load', null],
    ['files that are not on this install', { ...RUNNING, active_model_installed: false, runtime_source: 'planned' }, 'Needs a download', null],
    ['a report with no evidence', { active_model_installed: true, effective_model_id: 'Bird classifier', image_execution_mode: 'subprocess' }, 'Not reported', null],
    ['running with failing inferences', { ...RUNNING, inference_health: { status: 'unhealthy' } }, 'Running', 'Recent photos could not be named']
] as const) {
    test(`the pipeline's classifier step reads ${name} as ${state}`, async ({ page }) => {
        await open(page, route => route.fulfill({ json: portrait() }), report);
        const step = page.locator('[data-pipeline-step="classifier"]');
        await expect(step).toContainText(state);
        for (const other of ['Check', 'Unknown', 'Loaded', 'Not loaded yet']) await expect(step).not.toContainText(other);
        if (health) await expect(step.locator('[data-pipeline-health]')).toHaveText(health);
        else await expect(step.locator('[data-pipeline-health]')).toHaveCount(0);
    });
}

test('a guest is told the model\'s own state and never asks for work in progress, which is the owner\'s to read', async ({ page }) => {
    const asked: string[] = [];
    page.on('request', request => { if (new URL(request.url()).pathname === '/api/models/activity') asked.push(request.url()); });
    // The server is downloading the model, and this viewer is not signed in.
    await open(page, route => route.fulfill({ json: portrait() }), { ...RUNNING, active_model_installed: false, runtime_source: 'planned' }, { 'Bird classifier': 'downloading' });
    await expect(page.locator('[data-pipeline-step="classifier"]')).toContainText('Needs a download');
    expect(asked).toEqual([]);
});

// A development build checked out by name carries its branch in the version; a long one must not
// widen the chip, rewrap the title or move the portrait and the prose beneath it.
const LONG_VERSION = '2.9.15-m4/settings-by-task-accessibility-per-device-with-a-default-for-everyone+0123abc';

for (const viewport of [{ width: 1280, height: 800 }, { width: 390, height: 844 }]) {
    test(`a long branch name in the version moves nothing at ${viewport.width}px`, async ({ page }) => {
        await page.setViewportSize(viewport);
        const measure = async (version: string) => {
            await open(page, route => route.fulfill({ json: portrait() }), RUNNING, {}, version);
            const chip = page.locator('[data-about-version]');
            await expect(chip).toHaveText(`v${version}`);
            await expect(page.locator('[data-feeder-portrait-visit]')).toBeVisible();
            const [title, prose, portraitBox, slot, chipBox] = await Promise.all([
                page.locator('#about-project-heading').boundingBox(),
                page.locator('#about-project .max-w-prose').boundingBox(),
                page.locator('[data-feeder-portrait-visit]').boundingBox(),
                page.locator('[data-about-version-slot]').boundingBox(),
                chip.boundingBox()
            ]);
            return { title, prose, portrait: portraitBox, slot, chip: chipBox, tooltip: await chip.getAttribute('title') };
        };
        const short = await measure('2.9.15');
        const long = await measure(LONG_VERSION);
        // The title, the portrait and the prose stand exactly where they stood with a short version.
        for (const key of ['title', 'portrait', 'prose'] as const) {
            expect(long[key]?.y, key).toBeCloseTo(short[key]?.y ?? -1, 0);
            expect(long[key]?.width, key).toBeCloseTo(short[key]?.width ?? -1, 0);
        }
        // The chip keeps to its slot, cut short, and its title says the whole version.
        expect(long.chip && long.slot && long.chip.x + long.chip.width <= long.slot.x + long.slot.width + 1).toBe(true);
        expect(long.slot?.width).toBeCloseTo(short.slot?.width ?? -1, 0);
        expect(long.tooltip).toContain(`v${LONG_VERSION}`);
        expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(0);
    });
}

