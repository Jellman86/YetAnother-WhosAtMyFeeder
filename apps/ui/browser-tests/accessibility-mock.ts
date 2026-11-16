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

const HEALTHY_CONNECTIONS = {
    mqtt: { state: 'connected', server: 'mqtt', port: 1883 },
    frigate: { state: 'reachable', url: 'http://frigate:5000', availability: 'online' },
    generated_at: '2026-11-16T00:00:00Z'
};

function recordedJson(path: string): unknown {
    return recordedFor(new URL(path, 'http://fixture'))?.json;
}

/** The recorded sidebar sample, as the status carries it, so the owner's CPU line has a reading. */
function replayedTelemetry(): unknown {
    const sample = recordedJson('/api/system-telemetry') as {
        cpu_percent?: number | null;
        accelerator?: { kind: string; label: string; utilization_percent: number | null } | null;
    } | undefined;
    if (!sample) return null;
    return {
        sampled_at: Date.now() / 1000,
        cpu_percent: sample.cpu_percent ?? null,
        accelerator_percent: sample.accelerator?.utilization_percent ?? null,
        accelerator_kind: sample.accelerator?.kind ?? null,
        accelerator_label: sample.accelerator?.label ?? null
    };
}

/**
 * The pushed status the shell reads (`/api/status`), built from the recording's own answers for the
 * parts it carries, so the replayed jobs, queue, connections and cameras are the ones shown. A test
 * that overrides the workspace without connections gets measured, healthy connections, as before
 * the status existed, when such a workspace counted no connection problem.
 */
function replayedStatus(overrides: Record<string, unknown>): unknown {
    const workspace = overrides['/api/diagnostics/workspace'] as { connections?: unknown } | undefined;
    const connections = overrides['/api/diagnostics/connections']
        ?? workspace?.connections
        ?? (workspace ? HEALTHY_CONNECTIONS : recordedJson('/api/diagnostics/connections'));
    const jobs = overrides['/api/jobs'] ?? recordedJson('/api/jobs?include_routine=true')
        ?? { captured_at: new Date().toISOString(), items: [], lanes: [] };
    const lanes = (jobs as { lanes?: { kind: string; running?: number; queued?: number }[] }).lanes ?? [];
    const routine = new Set(['auto_video', 'high_quality_snapshot', 'full_visit', 'favorite_archive']);
    const prominent = lanes.filter((lane) => !routine.has(lane.kind));
    return {
        revision: 1,
        generated_at: new Date().toISOString(),
        startup_instance_id: 'fixture',
        // A version other than the page's own would make deploy recovery reload the page.
        version: 'unknown',
        overall: { state: 'ok', cause: 'ok', subsystem: null },
        subsystems: [],
        jobs_summary: {
            running: prominent.reduce((sum, lane) => sum + (lane.running ?? 0), 0),
            queued: prominent.reduce((sum, lane) => sum + (lane.queued ?? 0), 0),
            progress: null
        },
        jobs,
        analysis: overrides['/api/maintenance/analysis/status'] ?? recordedJson('/api/maintenance/analysis/status')
            ?? { pending: 0, active: 0, circuit_open: false },
        model: { state: 'ok', cause: 'ready', revision: 'fixture' },
        connections,
        cameras: overrides['/api/frigate/cameras/status'] ?? recordedJson('/api/frigate/cameras/status') ?? null,
        telemetry: replayedTelemetry(),
        diagnostics_revision: 0,
        health_revision: 'fixture'
    };
}

/** Answer the app's requests from the recording, and open it in `theme` with motion settled. */
export async function replayFeeder(
    page: Page,
    theme: Theme,
    overrides: Record<string, unknown> = {},
    /** Changes a recorded answer before it is replayed, for a state the recording does not hold. */
    rewrite: (json: unknown, url: URL) => unknown = (json) => json
): Promise<void> {
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
        if (url.pathname === '/api/status') return route.fulfill({ json: replayAt(replayedStatus(overrides), shiftMs) });
        if (route.request().resourceType() === 'image' || /\.(?:jpg|jpeg|png|webp)$/.test(url.pathname)) {
            return route.fulfill({ contentType: 'image/svg+xml', body: PHOTOGRAPH });
        }
        if (route.request().method() !== 'GET') return route.fulfill({ status: 503, json: { detail: 'The fixture is read-only' } });
        const recorded = recordedFor(url);
        if (!recorded || recorded.json === undefined) return route.fulfill({ status: 404, json: { detail: 'Not part of this fixture' } });
        return route.fulfill({ status: recorded.status, json: replayAt(rewrite(recorded.json, url), shiftMs) });
    });
}

/** Wait until the page has stopped asking for data and drawing it. */
export async function settled(page: Page): Promise<void> {
    // A request held open on purpose (a clip that never arrives) must not hold the page up for ever.
    await Promise.race([page.waitForLoadState('networkidle'), page.waitForTimeout(5000)]);
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
