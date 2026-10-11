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

async function open(page: Page, onPortrait: (route: Route) => Promise<void>) {
    page.on('pageerror', error => { throw error; });
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route('**/ready', route => route.fulfill({ json: { status: 'ready', startup_started_at: '2026-09-01T08:00:00Z' } }));
    await page.route(url => url.pathname.startsWith('/api/'), async route => {
        const path = new URL(route.request().url()).pathname;
        if (path === '/api/about/portrait') return onPortrait(route);
        if (path.endsWith('.jpg')) return route.fulfill({ contentType: 'image/svg+xml', body: image });
        if (path.endsWith('.webm')) return route.fulfill({ contentType: 'video/webm', body: 'fixture' });
        if (path === '/api/version') return route.fulfill({ json: { version: '2.9.15', base_version: '2.9.15', git_hash: 'fixture', branch: 'dev' } });
        if (path === '/api/about/community') return route.fulfill({ json: { enabled: true, active_installs: 812 } });
        if (path === '/api/classifier/status') return route.fulfill({ json: { loaded: true, effective_model_id: 'Bird classifier', active_provider: 'CPU' } });
        if (path === '/api/stats/uptime') return route.fulfill({ json: { buckets: [], longest_gap_minutes: 0, availability_percent: 100 } });
        if (path === '/api/update-status') return route.fulfill({ json: { enabled: false, update_available: false } });
        throw new Error(`Unexpected About fixture API request: ${path}`);
    });
    await page.goto('/browser-tests/about-portrait.html');
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
