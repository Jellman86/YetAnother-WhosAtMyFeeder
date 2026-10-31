import { expect, test, type Page } from '@playwright/test';

// The real App shell opening the Dashboard on a busy day: twelve visits shown of twenty-one,
// counted birds, and a microphone. The day's readings arrive late, as they do on a slow phone,
// so the page must already stand in the shape they fill.
const owner = { auth_required: false, is_authenticated: true, needs_initial_setup: false, birdnet_enabled: true };
const guest = {
    auth_required: true, is_authenticated: false, public_access_enabled: true, needs_initial_setup: false,
    birdnet_enabled: true, public_access_show_audio: true, public_access_rate_limit_per_minute: 30
};
const SPECIES = [
    ['Eurasian Blackbird', 'Turdus merula'], ['Dunnock', 'Prunella modularis'], ['House Sparrow', 'Passer domesticus'],
    ['European Robin', 'Erithacus rubecula'], ['Eurasian Tree Sparrow', 'Passer montanus']
] as const;
const image = '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="320"><rect width="320" height="320" fill="#3f6212"/></svg>';

function detection(index: number, at: number) {
    const [common, scientific] = SPECIES[index % SPECIES.length];
    return {
        frigate_event: `visit-${index}`, display_name: common, category_name: common, common_name: common,
        scientific_name: scientific, camera_name: 'birdcam', detection_time: new Date(at).toISOString(),
        score: index === 3 ? 0.42 : 0.86 + (index % 4) / 30, has_clip: true, manual_tagged: false, is_hidden: false
    };
}

function readings() {
    const now = Date.now();
    const reps = Array.from({ length: 12 }, (_, index) => detection(index, now - (index + 1) * 47 * 60_000));
    const visits = reps.map((rep, index) => ({
        visit_id: rep.frigate_event, start_time: new Date(Date.parse(rep.detection_time) - 90_000).toISOString(),
        end_time: rep.detection_time, capture_count: index % 3 === 0 ? 4 : 1, best_score: rep.score,
        needs_review: index === 3, audio_confirmed: index === 1, representative: rep, latest: rep, peak_capture: null
    }));
    const hourly = Array.from({ length: 24 }, (_, hour) => (hour % 5) + 1);
    return {
        events: reps,
        visits: { total: 21, gap_seconds: 60, visits },
        summary: {
            audio_confirmations: 13, counted_birds: 74, counted_captures: 46, hourly_distribution: hourly,
            hourly_visits: hourly, latest_detection: reps[0], total_count: 57, visit_count: 21,
            camera_visits: [{ camera: 'birdcam', visits: 21, last_seen: reps[0].detection_time }],
            top_species: SPECIES.map(([common, scientific], index) => ({
                species: common, common_name: common, scientific_name: scientific, count: 9 - index,
                visit_count: 9 - index, latest_event: `visit-${index}`
            }))
        },
        audio: {
            total: 956, species_count: 14, source_count: 1, daily_counts: [],
            hourly_counts: hourly.map((count, hour) => ({ hour, count: count * 9 })),
            sources: [{ source_name: 'garden-mic', count: 956, last_heard: reps[0].detection_time }],
            top_species: SPECIES.map(([common], index) => ({
                species: common, count: 120 - index * 10, avg_confidence: 0.8, max_confidence: 0.95,
                first_heard: reps[11].detection_time, last_heard: reps[0].detection_time
            }))
        }
    };
}

interface Opening {
    status: Record<string, unknown>;
    /** How long the day's readings take, so the page is seen before and after they land. */
    readingDelayMs?: number;
}

async function openDashboard(page: Page, { status, readingDelayMs = 0 }: Opening): Promise<void> {
    const data = readings();
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route('**/health', route => route.fulfill({ json: { status: 'healthy' } }));
    await page.route(url => url.pathname.startsWith('/api/'), async route => {
        const path = new URL(route.request().url()).pathname;
        if (path === '/api/sse') return route.abort();
        if (path.endsWith('.jpg') || path.endsWith('/snapshot') || path.endsWith('/thumbnail')) {
            return route.fulfill({ contentType: 'image/svg+xml', body: image });
        }
        const late: Record<string, unknown> = {
            '/api/stats/daily-summary': data.summary,
            '/api/visits': data.visits,
            '/api/audio/summary': data.audio
        };
        if (path in late) {
            if (readingDelayMs > 0) await new Promise(resolve => setTimeout(resolve, readingDelayMs));
            return route.fulfill({ json: late[path] });
        }
        const responses: Record<string, unknown> = {
            '/api/auth/status': status,
            '/api/settings': { birdnet_enabled: true, classification_threshold: 0.6, cameras: ['birdcam'], media_cache_high_quality_event_snapshots: true, clips_enabled: true },
            '/api/settings/public': { classification_threshold: 0.6, ebird_default_days_back: 7, clips_enabled: true, recording_clip_enabled: false, bird_counting_enabled: true },
            '/api/events': data.events,
            '/api/events/count': { count: data.events.length },
            '/api/events/new-species': { items: [] },
            '/api/audio/recent': [],
            '/api/update-status': { update_available: false }
        };
        if (path in responses) return route.fulfill({ json: responses[path] });
        return route.fulfill({ status: 503, json: { detail: 'Not part of this fixture' } });
    });
    await page.goto('/');
}

async function settled(page: Page): Promise<void> {
    await expect(page.locator('[data-field-log-row]')).toHaveCount(12, { timeout: 15_000 });
    const dayBar = page.locator('[data-dashboard-day-bar]');
    await expect(dayBar).toContainText('956');
    await expect(dayBar).toContainText('74');
}

test.describe('the Dashboard at 320px with enlarged text', () => {
    test.use({ viewport: { width: 320, height: 900 } });

    for (const { name, enlarge } of [
        { name: 'a 200% root font size', enlarge: async (page: Page) => page.addStyleTag({ content: 'html{font-size:200%!important}' }) },
        { name: 'the largest Appearance text size', enlarge: async (page: Page) => page.evaluate(() => localStorage.setItem('text_size', 'largest')).then(() => page.reload()) }
    ]) {
        test(`never scrolls sideways at ${name}`, async ({ page }, testInfo) => {
            await openDashboard(page, { status: owner });
            await settled(page);
            await enlarge(page);
            await settled(page);

            await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(0);

            // Every figure shows its label, value and note whole, inside its own cell and the screen.
            const figures = page.locator('[data-day-bar-figure]');
            expect(await figures.count()).toBe(6);
            const clipped = await figures.evaluateAll(nodes => nodes.flatMap(node => {
                const cell = node.getBoundingClientRect();
                const parts = [node, ...node.querySelectorAll('dt, dd, dd > span')];
                return parts.flatMap(part => {
                    const box = part.getBoundingClientRect();
                    const inside = box.left >= cell.left - 0.5 && box.right <= cell.right + 0.5 && box.right <= innerWidth;
                    const whole = part.scrollWidth <= part.clientWidth + 1 || part.clientWidth === 0;
                    return inside && whole ? [] : [`${node.getAttribute('data-day-bar-figure')}: ${part.textContent?.trim()}`];
                });
            }));
            expect(clipped).toEqual([]);

            // Each row's Open (or Identify) stays on screen, with its full touch target.
            const actions = page.locator('[data-field-log-row] [data-field-log-action]');
            expect(await actions.count()).toBe(12);
            for (const action of await actions.all()) {
                const box = await action.boundingBox();
                expect(box).not.toBeNull();
                expect(box?.x ?? -1).toBeGreaterThanOrEqual(0);
                expect((box?.x ?? 0) + (box?.width ?? 0)).toBeLessThanOrEqual(320);
                expect(box?.width ?? 0).toBeGreaterThanOrEqual(44);
                expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
            }
            // The day's heading wraps between words, never inside one.
            const heading = page.getByRole('heading', { level: 1 });
            expect(await heading.evaluate(node => node.scrollWidth <= node.clientWidth)).toBe(true);
            await page.screenshot({ path: testInfo.outputPath('dashboard-320-enlarged.png'), fullPage: true });
        });
    }
});

declare global {
    interface Window {
        layoutShifts?: { value: number; sources: string[] }[];
    }
}

async function observeLayoutShift(page: Page): Promise<void> {
    await page.addInitScript(() => {
        window.layoutShifts = [];
        new PerformanceObserver(list => {
            for (const entry of list.getEntries() as (PerformanceEntry & {
                value: number; hadRecentInput: boolean; sources?: { node?: Node | null }[];
            })[]) {
                if (entry.hadRecentInput) continue;
                const sources = (entry.sources ?? []).map(source => {
                    const node = source.node;
                    if (!(node instanceof Element)) return node?.nodeName ?? 'unknown';
                    const hook = [...node.attributes].find(attribute => attribute.name.startsWith('data-'))?.name;
                    return `${node.tagName.toLowerCase()}${hook ? `[${hook}]` : ''}.${String(node.className).slice(0, 60)}`;
                });
                window.layoutShifts?.push({ value: entry.value, sources });
            }
        }).observe({ type: 'layout-shift', buffered: true });
    });
}

for (const { device, viewport, budget } of [
    { device: 'desktop', viewport: { width: 1280, height: 800 }, budget: 0.05 },
    { device: 'phone', viewport: { width: 390, height: 844 }, budget: 0.1 }
]) {
    for (const [visitor, status] of [['owner', owner], ['guest', guest]] as const) {
        test(`a cold Dashboard load holds still on a ${device} for the ${visitor} while the day is read`, async ({ page }) => {
            await page.setViewportSize(viewport);
            await observeLayoutShift(page);
            await openDashboard(page, { status, readingDelayMs: 1_500 });
            await settled(page);
            // Late images and fonts are part of the load the reader sees.
            await page.waitForTimeout(1_000);
            const shifts = await page.evaluate(() => window.layoutShifts ?? []);
            // Every shift, not only the worst session window: stricter than the CLS metric.
            const total = shifts.reduce((sum, shift) => sum + shift.value, 0);
            expect(total, JSON.stringify(shifts, null, 1)).toBeLessThanOrEqual(budget);
        });
    }
}

test('the field log names the desk window and says that its earlier visits open in the Explorer', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await openDashboard(page, { status: owner });
    await settled(page);
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Last 24 hours');
    const more = page.locator('[data-field-log-more]');
    await expect(more).toHaveText('9 earlier visits in the last 24 hours, open in Explorer');
    await more.click();
    await expect.poll(() => new URL(page.url()).pathname).toBe('/events');
});
