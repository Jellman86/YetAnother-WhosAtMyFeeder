import type { Page } from '@playwright/test';
import recording from './fixtures/accessibility-api.json' with { type: 'json' };

/**
 * A feeder with a month of visits, replayed from `fixtures/accessibility-api.json`: every GET the
 * owner's main routes make, recorded once from a seeded install (no real feeder, host or key in it).
 * The pages are checked with their real content on them, not their empty states, because contrast
 * and naming failures live in the rows, chips and charts that only appear with data.
 */
interface Recorded { status: number; json?: unknown }
const RECORDED_AT = Date.parse((recording as { recordedAt: string }).recordedAt);
const RESPONSES = (recording as { responses: Record<string, Recorded> }).responses;

const DAY_MS = 86_400_000;
const INSTANT = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(Z|[+-]\d{2}:\d{2})?$/;
const CALENDAR_DAY = /^\d{4}-\d{2}-\d{2}$/;

/** Move every recorded instant forward by the age of the recording, so "the last 24 hours" is never empty. */
function replayAt(value: unknown, shiftMs: number): unknown {
    if (typeof value === 'string') {
        const instant = INSTANT.exec(value);
        if (instant) {
            const shifted = new Date(Date.parse(instant[1] ? value : `${value}Z`) + shiftMs).toISOString();
            return instant[1] ? shifted : shifted.replace(/Z$/, '');
        }
        if (CALENDAR_DAY.test(value)) {
            return new Date(Date.parse(`${value}T00:00:00Z`) + Math.round(shiftMs / DAY_MS) * DAY_MS).toISOString().slice(0, 10);
        }
        return value;
    }
    if (Array.isArray(value)) return value.map((item) => replayAt(item, shiftMs));
    if (value && typeof value === 'object') {
        return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, replayAt(item, shiftMs)]));
    }
    return value;
}

/** The recorded answer for this request: the same path, and of those the one whose query agrees most. */
function recordedFor(url: URL): Recorded | undefined {
    const exact = RESPONSES[url.pathname + url.search];
    if (exact) return exact;
    let best: Recorded | undefined;
    let bestScore = -1;
    for (const [key, response] of Object.entries(RESPONSES)) {
        const recorded = new URL(key, 'http://fixture');
        if (recorded.pathname !== url.pathname) continue;
        let score = 0;
        for (const [name, value] of url.searchParams) if (recorded.searchParams.get(name) === value) score += 1;
        if (score > bestScore) [best, bestScore] = [response, score];
    }
    return best;
}

const PHOTOGRAPH = '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="480"><rect width="640" height="480" fill="#e7ecd9"/><circle cx="320" cy="240" r="90" fill="#6b7f3a"/></svg>';

const NOTIFICATIONS = (now: number) => [
    { id: 'fixture:det:1', type: 'detection', title: 'Eurasian Blue Tit', message: 'feeder · 94%', timestamp: now - 6 * 60_000, read: false, meta: { source: 'sse', route: '/events' } },
    { id: 'fixture:proc:running', type: 'process', title: 'Video analysis', message: 'Analysing queued clips', timestamp: now - 3 * 60_000, read: false, meta: { source: 'poll', kind: 'video_classification', status: 'running', current: 7, total: 19, processed: 7, route: '/settings/health' } },
    { id: 'fixture:proc:failed', type: 'process', title: 'Taxonomy sync', message: 'iNaturalist did not answer', timestamp: now - 2 * 3_600_000, read: false, meta: { source: 'poll', kind: 'taxonomy_sync', status: 'failed', current: 41, total: 120, route: '/settings/enrichment' } },
    { id: 'fixture:proc:done', type: 'process', title: 'Backfill finished', message: '148 events checked', timestamp: now - 5 * 3_600_000, read: true, meta: { source: 'poll', kind: 'backfill', status: 'completed', current: 148, total: 148 } },
    { id: 'fixture:sys:error', type: 'system', title: 'MQTT connection lost', message: 'The broker could not be reached', timestamp: now - 26 * 3_600_000, read: true, meta: { source: 'system', route: '/settings/health' } }
];

export type Theme = 'light' | 'dark';

/** Answer the app's requests from the recording, and open it in `theme` with motion settled. */
export async function replayFeeder(page: Page, theme: Theme, overrides: Record<string, unknown> = {}): Promise<void> {
    const shiftMs = Date.now() - RECORDED_AT;
    await page.emulateMedia({ reducedMotion: 'reduce', colorScheme: theme });
    await page.addInitScript(([chosen, notifications]) => {
        localStorage.setItem('theme', chosen as string);
        localStorage.setItem('yawamf_notification_center', JSON.stringify(notifications));
    }, [theme, NOTIFICATIONS(Date.now())] as const);
    // Nothing leaves the machine: the web font, encyclopedia pictures and map tiles are stood in for.
    await page.route(/^https?:\/\/(?!127\.0\.0\.1)/, (route) => {
        const type = route.request().resourceType();
        if (type === 'stylesheet') return route.fulfill({ contentType: 'text/css', body: '' });
        if (type === 'image') return route.fulfill({ contentType: 'image/svg+xml', body: PHOTOGRAPH });
        return route.abort();
    });
    // The backend's own /health only: the same glob would also answer the /settings/health page.
    await page.route((url) => url.pathname === '/health', (route) => route.fulfill({ json: { status: 'healthy' } }));
    await page.route((url) => url.pathname.startsWith('/api/'), (route) => {
        const url = new URL(route.request().url());
        if (url.pathname in overrides) return route.fulfill({ json: overrides[url.pathname] });
        if (url.pathname === '/api/sse') return route.abort();
        if (route.request().resourceType() === 'image' || /\.(?:jpg|jpeg|png|webp)$/.test(url.pathname)) {
            return route.fulfill({ contentType: 'image/svg+xml', body: PHOTOGRAPH });
        }
        if (route.request().method() !== 'GET') return route.fulfill({ status: 503, json: { detail: 'The fixture is read-only' } });
        const recorded = recordedFor(url);
        if (!recorded || recorded.json === undefined) return route.fulfill({ status: 404, json: { detail: 'Not part of this fixture' } });
        return route.fulfill({ status: recorded.status, json: replayAt(recorded.json, shiftMs) });
    });
}

/** Wait until the page has stopped asking for data and drawing it. */
export async function settled(page: Page): Promise<void> {
    await page.waitForLoadState('networkidle');
    await page.evaluate(async () => {
        await document.fonts.ready;
        // A picture still decoding leaves its caption over nothing, which reads as a contrast failure.
        await Promise.all([...document.images].filter((image) => !image.complete).map((image) => new Promise((done) => {
            image.addEventListener('load', done, { once: true });
            image.addEventListener('error', done, { once: true });
            setTimeout(done, 3000);
        })));
    });
    await page.waitForTimeout(400);
}
