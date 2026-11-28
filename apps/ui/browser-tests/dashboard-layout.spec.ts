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
            hourly_visits: hourly, latest_detection: reps[0], total_count: 57, visit_count: 21, unknown_visit_count: 1, unresolved_count: 1,
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
    /** Answers a request before the fixture does, for a test's own scenario. */
    answer?: (url: URL) => { json?: unknown; status?: number } | undefined | Promise<{ json?: unknown; status?: number } | undefined>;
}

/** The fixture's browser runs in London (playwright.config.ts), whose midnight Today counts from. */
function londonMidnight(at: Date = new Date()): string {
    const day = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/London', year: 'numeric', month: '2-digit', day: '2-digit' }).format(at);
    for (const offset of ['+00:00', '+01:00']) {
        const midnight = new Date(`${day}T00:00:00${offset}`);
        const local = new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/London', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(midnight);
        if (local === '00:00') return midnight.toISOString();
    }
    throw new Error(`No London midnight on ${day}`);
}

/** A read of Today runs from local midnight, so it is shorter than the last 24 hours' exact day. */
function readsToday(url: URL): boolean {
    if (url.searchParams.get('window') === 'today' || url.searchParams.get('span') === 'today') return true;
    const start = Date.parse(url.searchParams.get('start_time') ?? url.searchParams.get('start_date') ?? url.searchParams.get('start') ?? '');
    const end = Date.parse(url.searchParams.get('end_time') ?? url.searchParams.get('end_date') ?? url.searchParams.get('end') ?? '');
    return Number.isFinite(start) && Number.isFinite(end) && end - start !== 24 * 60 * 60 * 1000;
}

async function openDashboard(page: Page, { status, readingDelayMs = 0, summaryOverrides, summaryFail = false, queueTotal = 0, garden = false, today, rollingSummaryDelayMs = 0, requests, answer }: Opening): Promise<void> {
    const data = readings();
    if (summaryOverrides) Object.assign(data.summary, summaryOverrides);
    // Today's answers say they counted from this midnight, as the server does.
    const todaySummary = { window_start: londonMidnight(), ...data.summary, ...today?.summary, window: 'today' };
    const todayVisits = { ...data.visits, visits: today?.visits ?? data.visits.visits, total: today?.visitTotal ?? data.visits.total };
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route('**/health', route => route.fulfill({ json: { status: 'healthy' } }));
    await page.route(url => url.pathname.startsWith('/api/'), async route => {
        const url = new URL(route.request().url());
        const path = url.pathname;
        requests?.push(url);
        if (path === '/api/sse') return route.abort();
        const answered = await answer?.(url);
        if (answered) {
            return answered.status && answered.status >= 400
                ? route.fulfill({ status: answered.status, json: { detail: 'Unavailable in this scenario' } })
                : route.fulfill({ json: answered.json });
        }
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
            // The summary reports where it counted from: the start it was asked for.
            '/api/audio/summary': { ...data.audio, window_start: url.searchParams.get('start_date'), window_end: url.searchParams.get('end_date') }
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
            '/api/events/review-queue': { items: [], total: queueTotal, window_start: url.searchParams.get('window') === 'today' ? londonMidnight() : '', window_end: '' },
            '/api/leaderboard/species': { span: url.searchParams.get('span'), window_start: url.searchParams.get('span') === 'today' ? londonMidnight() : '', window_end: '', species: [], nearby_check: 'off' },
            '/api/audio/species': { span: url.searchParams.get('span'), window_start: url.searchParams.get('span') === 'today' ? londonMidnight() : '', window_end: '', species: [] },
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

const UNKNOWN_REASON = /^3 of these visits are Unknown birds\. An Unknown bird is usually its own visit\. .* so Visits can fall\. No capture is removed\.$/;

test('the Visits figure counts its Unknown birds and gives the reason on keyboard focus, closing on Escape (#1096)', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await openDashboard(page, { status: owner, summaryOverrides: { unknown_visit_count: 3, unresolved_count: 3 }, queueTotal: 3 });
    await settled(page);
    const figure = page.locator('[data-day-bar-figure="visits"]');
    await expect(figure.locator('.figure')).toHaveText('21');
    // The reason is never a native tooltip on the figure, which a keyboard or a finger cannot open.
    await expect(figure).not.toHaveAttribute('title');
    const hint = figure.getByRole('button', { name: '3 Unknown birds' });
    await expect(hint).toBeVisible();

    // Tab reaches it, focus opens the reason as its description, and Escape closes it.
    await hint.focus();
    await expect(hint).toBeFocused();
    await expect(page.getByRole('tooltip')).toHaveText(UNKNOWN_REASON);
    await expect(hint).toHaveAccessibleDescription(UNKNOWN_REASON);
    await page.keyboard.press('Escape');
    await expect(page.getByRole('tooltip')).toHaveCount(0);
    await expect(hint).not.toHaveAttribute('aria-describedby');

    // A window with no Unknown bird has nothing to explain and offers no control.
    await openDashboard(page, { status: owner, summaryOverrides: { unknown_visit_count: 0, unresolved_count: 0 } });
    await settled(page);
    await expect(figure).not.toContainText('Unknown bird');
    await expect(figure.getByRole('button')).toHaveCount(0);
});

test.describe('the Visits reason on a touch screen (#1096)', () => {
    test.use({ hasTouch: true, viewport: { width: 390, height: 900 } });

    test('a tap opens the reason and a second tap closes it', async ({ page }) => {
        await openDashboard(page, { status: owner, summaryOverrides: { unknown_visit_count: 3, unresolved_count: 3 }, queueTotal: 3 });
        await settled(page);
        const hint = page.locator('[data-day-bar-figure="visits"]').getByRole('button', { name: '3 Unknown birds' });
        // A full 44px touch target, though the line it sits in is one line of small text: a touch
        // 20px above or below the words' middle still lands on it.
        expect(await hint.evaluate(node => {
            const box = node.getBoundingClientRect();
            const x = box.left + box.width / 2;
            const middle = box.top + box.height / 2;
            return [middle - 20, middle + 20].every(y => node.contains(document.elementFromPoint(x, y)));
        })).toBe(true);
        await hint.tap();
        await expect(page.getByRole('tooltip')).toHaveText(UNKNOWN_REASON);
        await hint.tap();
        await expect(page.getByRole('tooltip')).toHaveCount(0);
    });
});

const ENLARGE_ROOT = () => {
    document.addEventListener('DOMContentLoaded', () => {
        const style = document.createElement('style');
        style.textContent = 'html{font-size:200%!important}';
        document.head.append(style);
    });
};

for (const { name, width, enlarged, language, count, words } of [
    { name: 'English at 320px with a 200% root font size', width: 320, enlarged: true, language: 'en', count: 3, words: '3 Unknown birds' },
    { name: 'German at 320px with a 200% root font size', width: 320, enlarged: true, language: 'de', count: 3, words: '3 Unbekannte Vögel' },
    { name: 'German at 320px with a 200% root font size and a four-digit count', width: 320, enlarged: true, language: 'de', count: 1234, words: '1.234 Unbekannte Vögel' },
    { name: 'Russian at 320px with a 200% root font size', width: 320, enlarged: true, language: 'ru', count: 3, words: '3 Неизвестные птицы' },
    { name: 'Russian at 360px', width: 360, enlarged: false, language: 'ru', count: 3, words: '3 Неизвестные птицы' },
    { name: 'English at 390px', width: 390, enlarged: false, language: 'en', count: 3, words: '3 Unknown birds' },
    { name: 'English at 1440px', width: 1440, enlarged: false, language: 'en', count: 3, words: '3 Unknown birds' }
]) {
    test(`the Unknown birds line stays one line inside its control and never moves the band, in ${name} (#1096)`, async ({ page }) => {
        await page.setViewportSize({ width, height: 1000 });
        if (enlarged) await page.addInitScript(ENLARGE_ROOT);
        if (language !== 'en') await page.addInitScript(code => localStorage.setItem('preferred-language', code), language);
        const figure = page.locator('[data-day-bar-figure="visits"]');
        const band = page.locator('[data-dashboard-day-bar] dl');
        // The figure's own content, its value and its note line; the cell itself stretches to the
        // tallest figure in its row, such as Birds found's two-line note.
        const content = figure.locator('dd');
        const measure = async () => ({
            figure: (await content.boundingBox())?.height ?? 0,
            note: (await content.locator(':scope > :last-child').boundingBox())?.height ?? 0,
            band: (await band.boundingBox())?.height ?? 0
        });

        await openDashboard(page, { status: owner, readingDelayMs: 1500, summaryOverrides: { unknown_visit_count: count, unresolved_count: 3 }, queueTotal: 3 });
        await expect(figure.locator('[data-loading-placeholder]').first()).toBeVisible();
        const reading = await measure();
        await settled(page);
        const hint = figure.locator('[data-day-bar-note-hint]');
        await expect(hint).toBeVisible();
        // However the words are cut on screen, the button is named by all of them.
        await expect(hint).toHaveAccessibleName(words);

        // Every line of the words sits inside the button, the button inside its cell and the screen,
        // and nothing reaches up into the value above it.
        const placement = await hint.evaluate(node => {
            const button = node.getBoundingClientRect();
            const cell = node.closest('[data-day-bar-figure]')?.getBoundingClientRect();
            const value = node.closest('[data-day-bar-figure]')?.querySelector('.figure')?.getBoundingClientRect();
            const wordsNode = node.querySelector('[data-day-bar-note-words]');
            const range = document.createRange();
            if (wordsNode) range.selectNodeContents(wordsNode);
            const lines = [...range.getClientRects()].filter(rect => rect.width > 0 && rect.height > 0);
            return {
                // An ellipsis can split one line into several rectangles; lines are distinct tops.
                lines: new Set(lines.map(rect => Math.round(rect.top))).size,
                linesInside: lines.every(rect => rect.top >= button.top - 1 && rect.bottom <= button.bottom + 1),
                wordsInside: !!wordsNode && wordsNode.getBoundingClientRect().right <= button.right + 0.5,
                inCell: !!cell && button.left >= cell.left - 0.5 && button.right <= cell.right + 0.5 && button.right <= innerWidth,
                belowValue: !!value && button.top >= value.bottom - 0.5
            };
        });
        expect(placement).toEqual({ lines: 1, linesInside: true, wordsInside: true, inCell: true, belowValue: true });
        const noted = await measure();

        // Only the Unknown birds differ, so any change in the band is theirs.
        await openDashboard(page, { status: owner, summaryOverrides: { unknown_visit_count: 0, unresolved_count: 3 }, queueTotal: 3 });
        await settled(page);
        await expect(figure.locator('[data-day-bar-note-hint]')).toHaveCount(0);
        const plain = await measure();

        expect(noted.figure).toBeGreaterThan(0);
        expect(Math.abs(noted.note - reading.note)).toBeLessThan(1);
        expect(Math.abs(noted.note - plain.note)).toBeLessThan(1);
        expect(Math.abs(noted.figure - reading.figure)).toBeLessThan(1);
        expect(Math.abs(noted.figure - plain.figure)).toBeLessThan(1);
        expect(Math.abs(noted.band - plain.band)).toBeLessThan(1);
    });
}

for (const { name, width, textSize } of [
    { name: 'the Smallest text size at 1440px, one row of figures', width: 1440, textSize: 'smallest' },
    { name: 'the Smaller text size at 1440px, one row of figures', width: 1440, textSize: 'smaller' },
    { name: 'the Smallest text size at 1024px', width: 1024, textSize: 'smallest' },
    { name: 'the Standard text size at 390px', width: 390, textSize: 'standard' }
]) {
    test(`the Unknown birds line keeps its whole 44px touch target at ${name} (#1096)`, async ({ page }) => {
        await page.setViewportSize({ width, height: 900 });
        await page.addInitScript(size => localStorage.setItem('text_size', size), textSize);
        await openDashboard(page, { status: owner, summaryOverrides: { unknown_visit_count: 3, unresolved_count: 3 }, queueTotal: 3 });
        await settled(page);
        const hint = page.locator('[data-day-bar-figure="visits"] [data-badge-hint]');
        await expect(hint).toBeVisible();
        // A touch anywhere 21px above or below the words' middle lands on the button: nothing clips it.
        const missed = await hint.evaluate(node => {
            const box = node.getBoundingClientRect();
            const middle = box.top + box.height / 2;
            return [box.left + 2, box.left + box.width / 2, box.right - 2].flatMap(x =>
                [-21, -10, 0, 10, 21].filter(offset => !node.contains(document.elementFromPoint(x, middle + offset))).map(offset => `${Math.round(x)},${offset}`)
            );
        });
        expect(missed).toEqual([]);
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
    return londonMidnight();
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
    // Every read was sent, and every one asked for Today.
    for (const path of ['/api/audio/summary', '/api/events/review-queue', '/api/leaderboard/species', '/api/audio/species']) {
        expect(read(path).length, path).toBeGreaterThan(0);
    }
    for (const url of read('/api/audio/summary')) expect(url.searchParams.get('start_date')).toBe(midnight);
    for (const url of read('/api/events/review-queue')) expect(url.searchParams.get('window')).toBe('today');
    for (const url of read('/api/leaderboard/species')) expect(url.searchParams.get('span')).toBe('today');
    for (const url of read('/api/audio/species')) expect(url.searchParams.get('span')).toBe('today');

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

// A day straddled at midnight: the browser is a moment before it, the server already past it.
const OLD_DAY = '2026-11-25T00:00:00.000Z';
const NEW_DAY = '2026-11-26T00:00:00.000Z';

function visitOf(capture: { frigate_event: string; detection_time: string; score: number }) {
    return {
        visit_id: capture.frigate_event, start_time: capture.detection_time, end_time: capture.detection_time, capture_count: 1,
        best_score: capture.score, needs_review: false, audio_confirmed: false, representative: capture, latest: capture, peak_capture: null
    };
}

function gardenVisitOf(id: string, at: string) {
    return {
        id, kind: 'visit', start_time: at, end_time: at, capture_count: 1,
        representative: { id, camera: 'patio', frigate_label: 'fox', observed_at: at, status: 'confirmed', reviewed_at: null, snapshot_url: null }
    };
}

function daySummary(windowStart: string, windowEnd: string, visits: number) {
    return {
        window: 'today', window_start: windowStart, window_end: windowEnd, audio_confirmations: 2, counted_birds: 9,
        counted_captures: 6, hourly_distribution: Array(24).fill(0), hourly_visits: [visits, ...Array(23).fill(0)],
        latest_detection: null, total_count: visits, visit_count: visits, unresolved_count: 0, camera_visits: [], top_species: []
    };
}

test('a load that straddles midnight never shows the new day beside the old one', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.addInitScript(() => {
        localStorage.setItem('yawamf.dashboard.window', 'today');
        // Remember whether anything read for the old day was ever on screen.
        const seen = { oldDay: false };
        (window as unknown as { __oldDay: typeof seen }).__oldDay = seen;
        new MutationObserver(() => {
            if (document.querySelector('[data-field-log-garden="pre-midnight-fox"]') || document.body?.textContent?.includes('Pre-midnight Nightjar')) seen.oldDay = true;
        }).observe(document, { childList: true, subtree: true, characterData: true });
    });
    // Held a few seconds before midnight while the page loads, so its first reads straddle the day.
    await page.clock.install({ time: new Date('2026-11-25T23:59:50Z') });
    await page.clock.pauseAt(new Date('2026-11-25T23:59:55Z'));
    const requests: URL[] = [];
    const oldCapture = { ...detection(0, Date.parse('2026-11-25T23:30:00Z')), frigate_event: 'pre-midnight', display_name: 'Pre-midnight Nightjar', common_name: 'Pre-midnight Nightjar' };
    const newCaptures = [detection(1, Date.parse('2026-11-26T00:00:00.500Z')), detection(2, Date.parse('2026-11-26T00:00:00.200Z'))];
    await openDashboard(page, {
        status: owner,
        garden: true,
        requests,
        answer: (url) => {
            const start = url.searchParams.get('start_time') ?? url.searchParams.get('start') ?? url.searchParams.get('start_date');
            switch (url.pathname) {
                // The server is already on the new day for everything it settles itself.
                case '/api/stats/daily-summary':
                    return { json: daySummary(NEW_DAY, '2026-11-26T00:00:02.000Z', 2) };
                case '/api/events/review-queue':
                    return { json: { items: [], total: 0, window_start: NEW_DAY, window_end: '2026-11-26T00:00:02.000Z' } };
                case '/api/leaderboard/species':
                    return { json: { span: 'today', window_start: NEW_DAY, window_end: '', species: [], nearby_check: 'off' } };
                case '/api/audio/species':
                    return { json: { span: 'today', window_start: NEW_DAY, window_end: '', species: [] } };
                // Exact instants are counted as asked.
                case '/api/visits':
                    return { json: start === NEW_DAY
                        ? { total: 2, gap_seconds: 60, visits: newCaptures.map(visitOf) }
                        : { total: 1, gap_seconds: 60, visits: [visitOf(oldCapture)] } };
                case '/api/garden/visits':
                    return { json: start === NEW_DAY
                        ? { visits: [gardenVisitOf('new-badger', '2026-11-26T00:00:00.800Z')], total: 1, capture_total: 1, limit: 12, offset: 0 }
                        : { visits: [gardenVisitOf('pre-midnight-fox', '2026-11-25T23:40:00Z')], total: 1, capture_total: 1, limit: 12, offset: 0 } };
                case '/api/audio/summary':
                    return { json: { total: start === NEW_DAY ? 33 : 956, species_count: 3, source_count: 1, daily_counts: [], hourly_counts: [], sources: [], top_species: [], window_start: start, window_end: url.searchParams.get('end_date') } };
                default:
                    return undefined;
            }
        }
    });
    const log = page.locator('[data-dashboard-field-log]');
    // Asked three times, answered for the next day each time: nothing is shown as Today.
    await expect(log).toContainText('Visits could not be loaded.');
    const read = (path: string) => requests.filter(url => url.pathname === path);
    expect(read('/api/stats/daily-summary').length).toBe(3);
    await expect(page.locator('[data-day-bar-figure="visits"] .figure')).not.toHaveText('2');

    // Past midnight here too, the page reads the new day from the start.
    await page.clock.runFor(10_000);
    await expect(page.locator('[data-day-bar-figure="visits"] .figure')).toHaveText('2', { timeout: 15_000 });
    await expect(page.locator('[data-day-bar-figure="calls-heard"] .figure')).toHaveText('33');
    await expect(log.locator('[data-field-log-garden="new-badger"]')).toBeVisible();
    await expect(log.locator('[data-field-log-row]')).toHaveCount(3);
    expect(await page.evaluate(() => (window as unknown as { __oldDay: { oldDay: boolean } }).__oldDay.oldDay)).toBe(false);

    // Every reading was taken for Today, and the new day's from its own midnight.
    for (const path of ['/api/leaderboard/species', '/api/audio/species']) {
        expect(read(path).length, path).toBeGreaterThan(0);
        for (const url of read(path)) expect(url.searchParams.get('span')).toBe('today');
    }
    const newDayVisits = read('/api/visits').filter(url => url.searchParams.get('start_time') === NEW_DAY);
    expect(newDayVisits.length).toBeGreaterThan(0);
});

test('an open walkthrough takes the new day\'s list at midnight', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.addInitScript(() => localStorage.setItem('yawamf.dashboard.window', 'today'));
    await page.clock.install({ time: new Date('2026-11-25T23:59:20Z') });
    const unknown = { ...detection(0, Date.parse('2026-11-25T23:10:00Z')), frigate_event: 'unknown-late', display_name: 'Unknown Bird', common_name: null, scientific_name: null, score: 0.3 };
    const newcomer = { ...detection(1, Date.parse('2026-11-22T08:00:00Z')), frigate_event: 'hoopoe', display_name: 'Eurasian Hoopoe', common_name: 'Eurasian Hoopoe', scientific_name: 'Upupa epops' };
    const day = { afterMidnight: false };
    await openDashboard(page, {
        status: owner,
        answer: (url) => {
            const start = day.afterMidnight ? NEW_DAY : OLD_DAY;
            switch (url.pathname) {
                case '/api/stats/daily-summary':
                    return { json: daySummary(start, start, 1) };
                case '/api/events/review-queue':
                    return { json: day.afterMidnight
                        ? { items: [{ event: newcomer, reason: 'new_species', species_sightings: 1 }], total: 1, window_start: start, window_end: start }
                        : { items: [{ event: unknown, reason: 'unknown_species', species_sightings: null }, { event: newcomer, reason: 'new_species', species_sightings: 1 }], total: 2, window_start: start, window_end: start } };
                case '/api/leaderboard/species':
                    return { json: { span: 'today', window_start: start, window_end: '', species: [], nearby_check: 'off' } };
                case '/api/audio/species':
                    return { json: { span: 'today', window_start: start, window_end: '', species: [] } };
                default:
                    return undefined;
            }
        }
    });
    await page.getByRole('button', { name: 'Work through the queue' }).click();
    const walkthrough = page.locator('[data-review-queue-modal]');
    await expect(walkthrough).toContainText('1 of 2');

    await page.clock.pauseAt(new Date('2026-11-25T23:59:50Z'));
    day.afterMidnight = true;
    await page.clock.runFor(15_000);
    // The capture from before midnight drops out; the new species is still waiting.
    await expect(walkthrough).toContainText('1 of 1');
    await expect(walkthrough).toContainText('First Eurasian Hoopoe recorded here');
});

test('a Today refresh that fails after an empty reading says it could not be read', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.addInitScript(() => localStorage.setItem('yawamf.dashboard.window', 'today'));
    const refresh = { fails: false };
    await openDashboard(page, {
        status: owner,
        today: { summary: { visit_count: 0, top_species: [], unresolved_count: 0 }, visits: [], visitTotal: 0 },
        answer: (url) => (refresh.fails && url.pathname === '/api/stats/daily-summary' ? { status: 503 } : undefined)
    });
    const log = page.locator('[data-dashboard-field-log]');
    await expect(log).toContainText('No visits yet today.');
    refresh.fails = true;
    await page.getByRole('button', { name: 'Refresh', exact: true }).click();
    await expect(log).toContainText('Visits could not be loaded.');
    await expect(log).not.toContainText('yet today');
});

test('with Garden unread and no birds, the log says no bird visits, not no visits', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.addInitScript(() => localStorage.setItem('yawamf.dashboard.window', 'today'));
    await openDashboard(page, {
        status: owner,
        garden: true,
        today: { summary: { visit_count: 0, top_species: [], unresolved_count: 0 }, visits: [], visitTotal: 0 },
        answer: (url) => (url.pathname === '/api/garden/visits' ? { status: 503 } : undefined)
    });
    const log = page.locator('[data-dashboard-field-log]');
    await expect(log).toContainText('No bird visits yet today.');
    await expect(log.locator('[data-field-log-garden-unavailable]')).toBeVisible();
    await expect(log).not.toContainText('No visits yet today');
});

test('a Heard summary that could not be read is not "no calls heard"', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.addInitScript(() => localStorage.setItem('yawamf.dashboard.window', 'today'));
    await openDashboard(page, { status: owner, answer: (url) => (url.pathname === '/api/audio/summary' ? { status: 503 } : undefined) });
    const heard = page.locator('[data-dashboard-audio]');
    await expect(heard.locator('[data-dashboard-heard-unavailable]')).toContainText('Calls heard could not be loaded.');
    await expect(heard).not.toContainText('No calls heard');
});

test('an old-day answer that lands just after midnight is not shown as Today', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.addInitScript(() => {
        localStorage.setItem('yawamf.dashboard.window', 'today');
        const seen = { oldDay: false };
        (window as unknown as { __oldDay: typeof seen }).__oldDay = seen;
        new MutationObserver(() => {
            if (document.body?.textContent?.includes('Pre-midnight Nightjar')) seen.oldDay = true;
        }).observe(document, { childList: true, subtree: true, characterData: true });
    });
    await page.clock.install({ time: new Date('2026-11-25T23:59:50Z') });
    await page.clock.pauseAt(new Date('2026-11-25T23:59:59.900Z'));
    // The old day's answers are held until the browser's clock reads 00:00:00.200.
    let release: () => void = () => {};
    const held = new Promise<void>((resolve) => { release = resolve; });
    const phase = { afterMidnight: false };
    const summaryAsked: string[] = [];
    const oldCapture = { ...detection(0, Date.parse('2026-11-25T23:30:00Z')), frigate_event: 'pre-midnight', display_name: 'Pre-midnight Nightjar', common_name: 'Pre-midnight Nightjar' };
    const newCaptures = [detection(1, Date.parse('2026-11-26T00:00:00.100Z'))];
    await openDashboard(page, {
        status: owner,
        answer: async (url) => {
            const day = phase.afterMidnight ? NEW_DAY : OLD_DAY;
            if (url.pathname === '/api/stats/daily-summary') summaryAsked.push(day);
            const answerFor = (): { json?: unknown } | undefined => {
                switch (url.pathname) {
                    case '/api/stats/daily-summary':
                        return { json: daySummary(day, day, day === NEW_DAY ? 1 : 5) };
                    case '/api/visits':
                        return { json: day === NEW_DAY ? { total: 1, gap_seconds: 60, visits: newCaptures.map(visitOf) } : { total: 1, gap_seconds: 60, visits: [visitOf(oldCapture)] } };
                    case '/api/events/review-queue':
                        return { json: { items: [], total: 0, window_start: day, window_end: day } };
                    case '/api/leaderboard/species':
                        return { json: { span: 'today', window_start: day, window_end: '', species: [], nearby_check: 'off' } };
                    case '/api/audio/species':
                        return { json: { span: 'today', window_start: day, window_end: '', species: [] } };
                    default:
                        return undefined;
                }
            };
            const response = answerFor();
            if (response && day === OLD_DAY) await held;
            return response;
        }
    });
    await expect.poll(() => summaryAsked.length).toBeGreaterThan(0);
    await page.clock.runFor(300);
    phase.afterMidnight = true;
    release();
    // The old answers settle after midnight: the page reads the new day instead of showing them.
    await expect(page.locator('[data-day-bar-figure="visits"] .figure')).toHaveText('1');
    expect(summaryAsked).toContain(NEW_DAY);
    expect(await page.evaluate(() => (window as unknown as { __oldDay: { oldDay: boolean } }).__oldDay.oldDay)).toBe(false);
});

test.describe('a guest in Tokyo at UTC midnight', () => {
    test.use({ timezoneId: 'Asia/Tokyo' });

    test('reads the log again from where the shared history starts, never beside earlier captures', async ({ page }) => {
        await page.setViewportSize({ width: 1280, height: 900 });
        await page.addInitScript(() => {
            localStorage.setItem('yawamf.dashboard.window', 'today');
            const seen = { beforeCutoff: false };
            (window as unknown as { __cutoff: typeof seen }).__cutoff = seen;
            new MutationObserver(() => {
                if (document.body?.textContent?.includes('Before Cutoff Wren')) seen.beforeCutoff = true;
            }).observe(document, { childList: true, subtree: true, characterData: true });
        });
        // 08:59:59.9 in Tokyo, whose Today began at 15:00 UTC; the shared UTC day turns a moment later.
        await page.clock.install({ time: new Date('2026-11-25T23:59:50Z') });
        await page.clock.pauseAt(new Date('2026-11-25T23:59:59.900Z'));
        const tokyoMidnight = '2026-11-25T15:00:00.000Z';
        const sharedDay = NEW_DAY;
        const before = { ...detection(0, Date.parse('2026-11-25T23:30:00Z')), frigate_event: 'before-cutoff', display_name: 'Before Cutoff Wren', common_name: 'Before Cutoff Wren' };
        const after = detection(1, Date.parse('2026-11-26T00:00:00.500Z'));
        const visitReads: string[] = [];
        await openDashboard(page, {
            status: guest,
            answer: (url) => {
                switch (url.pathname) {
                    // The summary was answered after UTC midnight: it counted from the new shared day.
                    case '/api/stats/daily-summary':
                        return { json: daySummary(sharedDay, '2026-11-26T00:00:01.000Z', 1) };
                    // The visits read sent from Tokyo's midnight was answered before it, so it holds earlier captures.
                    case '/api/visits': {
                        const start = url.searchParams.get('start_time') ?? '';
                        visitReads.push(start);
                        return { json: start === sharedDay
                            ? { total: 1, gap_seconds: 60, visits: [visitOf(after)] }
                            : { total: 2, gap_seconds: 60, visits: [visitOf(after), visitOf(before)] } };
                    }
                    case '/api/audio/summary':
                        return { json: { total: 0, species_count: 0, source_count: 0, daily_counts: [], hourly_counts: [], sources: [], top_species: [], window_start: sharedDay, window_end: url.searchParams.get('end_date') } };
                    default:
                        return undefined;
                }
            }
        });
        await expect(page.locator('[data-day-bar-shared-from]')).toBeVisible();
        await expect(page.locator('[data-dashboard-field-log] [data-field-log-row]')).toHaveCount(1);
        expect(visitReads).toEqual([tokyoMidnight, sharedDay]);
        expect(await page.evaluate(() => (window as unknown as { __cutoff: { beforeCutoff: boolean } }).__cutoff.beforeCutoff)).toBe(false);
    });
});

test('Garden that fails on a refresh takes its earlier rows down with it', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    const refresh = { gardenFails: false };
    await openDashboard(page, {
        status: owner,
        garden: true,
        answer: (url) => {
            if (url.pathname !== '/api/garden/visits') return undefined;
            if (refresh.gardenFails) return { status: 503 };
            return { json: { visits: [gardenVisitOf('fox-today', new Date(Date.now() - 30 * 60_000).toISOString())], total: 1, capture_total: 1, limit: 12, offset: 0 } };
        }
    });
    const log = page.locator('[data-dashboard-field-log]');
    await expect(log.locator('[data-field-log-garden="fox-today"]')).toBeVisible();
    refresh.gardenFails = true;
    await page.getByRole('button', { name: 'Refresh', exact: true }).click();
    await expect(log.locator('[data-field-log-garden-unavailable]')).toBeVisible();
    await expect(log.locator('[data-field-log-garden="fox-today"]')).toHaveCount(0);
});

for (const [when, at, shown] of [
    ['yesterday', '2026-11-24T23:50:00Z', false],
    ['today', 'NOW', true]
] as const) {
    test(`a latest call from ${when} ${shown ? 'is' : 'is not'} shown under Today's calls`, async ({ page }) => {
        await page.setViewportSize({ width: 1280, height: 800 });
        await page.addInitScript(() => localStorage.setItem('yawamf.dashboard.window', 'today'));
        const heardAt = at === 'NOW' ? new Date(Date.now() - 60_000).toISOString() : at;
        test.skip(at === 'NOW' && Date.parse(heardAt) < Date.parse(londonMidnight()), 'Today began less than a minute ago');
        await openDashboard(page, {
            status: owner,
            answer: (url) => (url.pathname === '/api/audio/recent'
                ? { json: [{ id: 1, species: 'Tawny Owl', scientific_name: 'Strix aluco', confidence: 0.9, timestamp: heardAt, source_name: 'garden-mic' }] }
                : undefined)
        });
        const heard = page.locator('[data-dashboard-audio]');
        await expect(heard.locator('[data-dashboard-species-heard]')).toBeVisible();
        if (shown) await expect(heard.locator('[data-dashboard-latest-call]')).toContainText('Tawny Owl');
        else await expect(heard.locator('[data-dashboard-latest-call]')).toHaveCount(0);
    });
}
