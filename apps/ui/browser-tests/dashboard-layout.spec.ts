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
            hourly_visits: hourly, latest_detection: reps[0], total_count: 57, visit_count: 21, unresolved_count: 1,
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
    summaryOverrides?: Record<string, unknown>;
    summaryFail?: boolean;
    queueTotal?: number;
    /** Garden animals switched on, with a quiet garden, so the log holds birds and Garden. */
    garden?: boolean;
    /** What Today reads, when it differs from the last 24 hours. */
    today?: { summary?: Record<string, unknown>; visits?: unknown[]; visitTotal?: number; delayMs?: number; fail?: boolean };
    /** How long the last 24 hours' day summary takes, apart from Today's. */
    rollingSummaryDelayMs?: number;
    /** Every request the page sends to the API, for checking which window each one read. */
    requests?: URL[];
}

/** A read of Today runs from local midnight, so it is shorter than the last 24 hours' exact day. */
function readsToday(url: URL): boolean {
    if (url.searchParams.get('window') === 'today' || url.searchParams.get('span') === 'today') return true;
    const start = Date.parse(url.searchParams.get('start_time') ?? url.searchParams.get('start_date') ?? url.searchParams.get('start') ?? '');
    const end = Date.parse(url.searchParams.get('end_time') ?? url.searchParams.get('end_date') ?? url.searchParams.get('end') ?? '');
    return Number.isFinite(start) && Number.isFinite(end) && end - start !== 24 * 60 * 60 * 1000;
}

async function openDashboard(page: Page, { status, readingDelayMs = 0, summaryOverrides, summaryFail = false, queueTotal = 0, garden = false, today, rollingSummaryDelayMs = 0, requests }: Opening): Promise<void> {
    const data = readings();
    if (summaryOverrides) Object.assign(data.summary, summaryOverrides);
    const todaySummary = { ...data.summary, ...today?.summary, window: 'today' };
    const todayVisits = { ...data.visits, visits: today?.visits ?? data.visits.visits, total: today?.visitTotal ?? data.visits.total };
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route('**/health', route => route.fulfill({ json: { status: 'healthy' } }));
    await page.route(url => url.pathname.startsWith('/api/'), async route => {
        const url = new URL(route.request().url());
        const path = url.pathname;
        requests?.push(url);
        if (path === '/api/sse') return route.abort();
        if (today && readsToday(url) && (path === '/api/stats/daily-summary' || path === '/api/visits')) {
            if (today.delayMs) await new Promise(resolve => setTimeout(resolve, today.delayMs));
            if (today.fail) return route.fulfill({ status: 503, json: { detail: 'Summary unavailable' } });
            return route.fulfill({ json: path === '/api/visits' ? todayVisits : todaySummary });
        }
        if (path === '/api/stats/daily-summary' && rollingSummaryDelayMs > 0) {
            await new Promise(resolve => setTimeout(resolve, rollingSummaryDelayMs));
        }
        if (path.endsWith('.jpg') || path.endsWith('/snapshot') || path.endsWith('/thumbnail')) {
            return route.fulfill({ contentType: 'image/svg+xml', body: image });
        }
        if (path === '/api/stats/daily-summary' && summaryFail) {
            return route.fulfill({ status: 503, json: { detail: 'Summary unavailable' } });
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
            '/api/settings': { birdnet_enabled: true, classification_threshold: 0.6, cameras: ['birdcam'], media_cache_high_quality_event_snapshots: true, clips_enabled: true, beta_garden_animals: garden },
            '/api/garden/visits': { visits: [], total: 0, capture_total: 0, limit: 24, offset: 0 },
            '/api/settings/public': { classification_threshold: 0.6, ebird_default_days_back: 7, clips_enabled: true, recording_clip_enabled: false, bird_counting_enabled: true },
            '/api/events': data.events,
            '/api/events/count': { count: data.events.length },
            '/api/events/review-queue': { items: [], total: queueTotal },
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

for (const { scope, garden, visitors } of [
    { scope: 'birds only', garden: false, visitors: 'birds' },
    { scope: 'birds and Garden', garden: true, visitors: 'all' }
]) {
    test(`the field log's earlier visits open the Explorer on the last 24 hours with ${scope}, whatever the device last chose`, async ({ page }) => {
        await page.setViewportSize({ width: 1280, height: 800 });
        // This device last left the Explorer on Garden alone; the link must not inherit that.
        await page.addInitScript(() => localStorage.setItem('yawamf:explorer-subjects', 'garden'));
        await openDashboard(page, { status: owner, garden });
        await settled(page);
        await expect(page.getByRole('heading', { level: 1 })).toHaveText('Last 24 hours');
        const more = page.locator('[data-field-log-more]');
        await expect(more).toHaveText('9 earlier visits in the last 24 hours, open in Explorer');
        // The Explorer's page of 24 visits, not the Dashboard's own read of 12.
        const visitsRead = page.waitForRequest(request => {
            const url = new URL(request.url());
            return url.pathname === '/api/visits' && url.searchParams.get('limit') === '24';
        });
        await more.click();
        await expect.poll(() => new URL(page.url()).pathname).toBe('/events');
        await expect.poll(() => new URL(page.url()).searchParams.get('date')).toBe('24h');
        await expect.poll(() => new URL(page.url()).searchParams.get('visitors')).toBe(visitors);
        // The Explorer reads exactly the last 24 hours, not whole days.
        const read = new URL((await visitsRead).url()).searchParams;
        const span = Date.parse(read.get('end_time') ?? '') - Date.parse(read.get('start_time') ?? '');
        expect(span).toBe(24 * 60 * 60 * 1000);
        expect(read.has('start_date')).toBe(false);
    });
}

test('the field log header still opens the whole history', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await openDashboard(page, { status: owner });
    await settled(page);
    await page.locator('[data-dashboard-field-log]').getByRole('button', { name: 'See full history' }).click();
    await expect.poll(() => new URL(page.url()).pathname).toBe('/events');
    expect(new URL(page.url()).searchParams.get('date')).toBeNull();
});

test('on a phone Needs your call comes before the field log; on a desktop it heads the rail beside the log', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openDashboard(page, { status: owner });
    await settled(page);
    const card = page.locator('[data-dashboard-needs-call]');
    const log = page.locator('[data-dashboard-field-log-column]');
    await expect(card).toBeVisible();
    let cardBox = await card.boundingBox();
    let logBox = await log.boundingBox();
    expect(cardBox && logBox && cardBox.y + cardBox.height <= logBox.y + 1).toBe(true);
    // The rest of the rail still follows the log on a phone.
    const rail = await page.locator('[data-dashboard-rail-now]').boundingBox();
    expect(rail && logBox && rail.y >= logBox.y + logBox.height - 1).toBe(true);

    await page.setViewportSize({ width: 1440, height: 900 });
    // The shell trades its phone bar for the sidebar as the window widens; measure once it has.
    await expect(page.locator('#app-sidebar')).toBeInViewport();
    await expect.poll(async () => {
        const [cardNow, logNow] = await Promise.all([card.boundingBox(), log.boundingBox()]);
        return Boolean(cardNow && logNow && cardNow.x >= logNow.x + logNow.width - 1);
    }).toBe(true);
    cardBox = await card.boundingBox();
    logBox = await log.boundingBox();
    const aside = await page.locator('[data-dashboard-field-desk] aside').boundingBox();
    expect(cardBox && logBox && Math.abs(cardBox.y - logBox.y)).toBeLessThan(2);
    // The rail continues straight under the card, with only the grid's gap between them.
    expect(cardBox && aside && aside.y - (cardBox.y + cardBox.height)).toBeLessThan(30);

    await page.setViewportSize({ width: 1920, height: 1080 });
    await expect.poll(async () => {
        const [cardNow, asideNow] = await Promise.all([card.boundingBox(), page.locator('[data-dashboard-field-desk] aside').boundingBox()]);
        return Boolean(cardNow && asideNow && Math.abs(cardNow.width - asideNow.width) < 2);
    }).toBe(true);
    const wideCard = await card.boundingBox();
    const wideAside = await page.locator('[data-dashboard-field-desk] aside').boundingBox();
    // From 1920px the rail has two columns and the card spans both.
    expect(wideCard && wideAside && Math.abs(wideCard.width - wideAside.width)).toBeLessThan(2);
});

test('under the log on a tablet the rail\'s two groups stand side by side, and beside it on a desktop they stack', async ({ page }) => {
    await page.setViewportSize({ width: 1024, height: 768 });
    await openDashboard(page, { status: owner });
    await settled(page);
    const now = page.locator('[data-dashboard-rail-now]');
    const reference = page.locator('[data-dashboard-rail-reference]');
    let nowBox = await now.boundingBox();
    let referenceBox = await reference.boundingBox();
    expect(nowBox && referenceBox && referenceBox.x >= nowBox.x + nowBox.width - 1).toBe(true);
    expect(nowBox && referenceBox && Math.abs(referenceBox.y - nowBox.y)).toBeLessThan(2);
    // Each group keeps a card's width rather than the whole page's.
    expect(nowBox?.width ?? Infinity).toBeLessThan(600);

    await page.setViewportSize({ width: 1440, height: 900 });
    await expect.poll(async () => {
        const [a, b] = await Promise.all([now.boundingBox(), reference.boundingBox()]);
        return Boolean(a && b && b.y >= a.y + a.height - 1);
    }).toBe(true);
    nowBox = await now.boundingBox();
    referenceBox = await reference.boundingBox();
    expect(nowBox && referenceBox && Math.abs(referenceBox.x - nowBox.x)).toBeLessThan(2);
});

for (const [visitor, status] of [['owner', owner], ['guest', guest]] as const) {
    test(`DayBar shows the server unresolved_count for ${visitor} rather than counting the recent-events buffer (#1086)`, async ({ page }) => {
        await page.setViewportSize({ width: 1280, height: 800 });
        await openDashboard(page, { status, summaryOverrides: { unresolved_count: 128 }, queueTotal: 128 });
        await settled(page);
        const figure = page.locator('[data-day-bar-figure="unresolved"]');
        await expect(figure.locator('.figure')).toHaveText('128');
    });
}

test('DayBar shows not available when daily-summary fails and measured 0 when clear (#1086)', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await openDashboard(page, { status: guest, summaryFail: true });
    const figure = page.locator('[data-day-bar-figure="unresolved"]');
    await expect(figure.locator('.figure')).toContainText('–');

    await openDashboard(page, { status: guest, summaryOverrides: { unresolved_count: 0 } });
    await settled(page);
    await expect(figure.locator('.figure')).toHaveText('0');
    await expect(figure).toContainText('nothing needs your call');
});

function localMidnight(): string {
    const midnight = new Date();
    midnight.setHours(0, 0, 0, 0);
    return midnight.toISOString();
}

test('Today reads one window everywhere, names it only once it is read and is remembered on this device', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    const requests: URL[] = [];
    await openDashboard(page, {
        status: owner,
        requests,
        today: { summary: { visit_count: 14, unresolved_count: 0 }, visitTotal: 14, delayMs: 700 }
    });
    await settled(page);
    const heading = page.getByRole('heading', { level: 1 });
    const visits = page.locator('[data-day-bar-figure="visits"] .figure');
    await expect(heading).toHaveText('Last 24 hours');
    await expect(visits).toHaveText('21');
    await expect(page.locator('[data-day-bar-window="rolling"]')).toHaveAttribute('aria-pressed', 'true');

    requests.length = 0;
    await page.locator('[data-day-bar-window="today"]').click();
    await expect(page.locator('[data-day-bar-window="today"]')).toHaveAttribute('aria-pressed', 'true');
    // While Today is read, nothing read for the last 24 hours stands under its name.
    await expect(heading).toHaveText('Today');
    await expect(visits).not.toHaveText('21');
    await expect(visits).toHaveText('14');

    const midnight = localMidnight();
    const read = (path: string) => requests.filter(url => url.pathname === path);
    expect(read('/api/stats/daily-summary').every(url => url.searchParams.get('window') === 'today')).toBe(true);
    const visitReads = read('/api/visits');
    expect(visitReads.length).toBeGreaterThan(0);
    for (const url of visitReads) expect(url.searchParams.get('start_time')).toBe(midnight);
    for (const url of read('/api/audio/summary')) expect(url.searchParams.get('start_date')).toBe(midnight);
    for (const url of read('/api/events/review-queue')) expect(url.searchParams.get('window')).toBe('today');
    for (const url of read('/api/leaderboard/species')) expect(url.searchParams.get('span')).toBe('today');
    expect(read('/api/events/review-queue').length).toBeGreaterThan(0);

    const more = page.locator('[data-field-log-more]');
    await expect(more).toHaveText('2 earlier visits today, open in Explorer');

    await page.reload();
    await expect(page.locator('[data-day-bar-window="today"]')).toHaveAttribute('aria-pressed', 'true');
    await expect(heading).toHaveText('Today');
    await expect(visits).toHaveText('14');

    await more.click();
    await expect.poll(() => new URL(page.url()).pathname).toBe('/events');
    await expect.poll(() => new URL(page.url()).searchParams.get('date')).toBe('today');
    await expect.poll(() => new URL(page.url()).searchParams.get('visitors')).toBe('birds');
});

test('a slower answer for the last 24 hours never lands under Today', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await openDashboard(page, { status: owner, rollingSummaryDelayMs: 1500, today: { summary: { visit_count: 14 }, visitTotal: 14 } });
    const visits = page.locator('[data-day-bar-figure="visits"] .figure');
    // Chosen before the last 24 hours have answered.
    await page.locator('[data-day-bar-window="today"]').click();
    await expect(visits).toHaveText('14');
    await page.waitForTimeout(2000);
    await expect(visits).toHaveText('14');
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Today');
});

test('an empty Today says no visits yet today, and a Today that failed does not', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.addInitScript(() => localStorage.setItem('yawamf.dashboard.window', 'today'));
    await openDashboard(page, { status: owner, today: { summary: { visit_count: 0, top_species: [], unresolved_count: 0 }, visits: [], visitTotal: 0 } });
    const log = page.locator('[data-dashboard-field-log]');
    await expect(log).toContainText('No visits yet today. New visits appear here as they arrive.');

    await openDashboard(page, { status: owner, today: { fail: true } });
    await expect(log).toContainText('Visits could not be loaded.');
    await expect(log).not.toContainText('yet today');
});

test('a guest whose shared history starts after their midnight is told from when Today is shown', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    const sharedFrom = new Date(Date.now() - 60_000);
    test.skip(sharedFrom.getTime() <= Date.parse(localMidnight()), 'Shared history cannot start after a midnight a minute away');
    await page.addInitScript(() => localStorage.setItem('yawamf.dashboard.window', 'today'));
    await openDashboard(page, { status: guest, today: { summary: { window_start: sharedFrom.toISOString() } } });
    await expect(page.locator('[data-day-bar-shared-from]')).toContainText('Shared history starts at');
    await expect(page.locator('[data-day-bar-shared-from]')).toContainText('so visits earlier today are not shown.');
});
