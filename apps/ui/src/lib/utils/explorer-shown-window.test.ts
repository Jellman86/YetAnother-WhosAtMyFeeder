import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Detection } from '../api';
import type { DetectionVisit } from '../api/visits';

const fetchVisitCaptures = vi.fn();
vi.mock('../api/visits', async (importOriginal) => ({
    ...(await importOriginal<typeof import('../api/visits')>()),
    fetchVisitCaptures: (...args: unknown[]) => fetchVisitCaptures(...args)
}));

const { VisitCaptureList } = await import('./visit-capture-list.svelte');
const { ShownExplorerWindow } = await import('./explorer-shown-window.svelte');
const { explorerWindow } = await import('./explorer-query');
const { authStore } = await import('../stores/auth.svelte');

function bird(id: string, at: string): Detection {
    return { frigate_event: id, display_name: 'Prunella modularis', camera_name: 'birdcam', detection_time: at, score: 0.9 } as Detection;
}

// The visit began 30 seconds after the cutoff of the window it was read in.
const FIRST_CAPTURE = '2026-11-24T10:00:30Z';
const visit = {
    visit_id: 'visit-near-cutoff', start_time: FIRST_CAPTURE, end_time: '2026-11-24T10:04:00Z', capture_count: 2,
    best_score: 0.9, needs_review: false, audio_confirmed: false,
    representative: bird('lead', FIRST_CAPTURE), latest: bird('last', '2026-11-24T10:04:00Z'), peak_capture: null
} as unknown as DetectionVisit;

let savedAuth: Pick<typeof authStore, 'authRequired' | 'isAuthenticated' | 'statusLoaded' | 'statusHealthy'>;

beforeEach(() => {
    fetchVisitCaptures.mockReset();
    fetchVisitCaptures.mockResolvedValue({ captures: [visit.representative, visit.latest], total: 2 });
    savedAuth = { authRequired: authStore.authRequired, isAuthenticated: authStore.isAuthenticated, statusLoaded: authStore.statusLoaded, statusHealthy: authStore.statusHealthy };
    Object.assign(authStore, { authRequired: true, isAuthenticated: true, statusLoaded: true, statusHealthy: true });
});

afterEach(() => {
    Object.assign(authStore, savedAuth);
});

describe('the Explorer window an expanded visit reads in (#1098)', () => {
    it('stays the shown window while a refresh is in flight, after it fails, and moves only with its results', async () => {
        const shown = new ShownExplorerWindow();
        const firstRead = explorerWindow('24h', {}, new Date('2026-11-25T10:00:00Z'));
        shown.publish(firstRead);
        const list = new VisitCaptureList(() => ({ visit, window: { ...shown.current.request } }));
        await list.load(true);
        expect(fetchVisitCaptures).toHaveBeenCalledTimes(1);
        expect(fetchVisitCaptures.mock.calls[0][1]).toMatchObject({ startTime: '2026-11-24T10:00:00.000Z', endTime: '2026-11-25T10:00:00.000Z' });
        const shownKey = list.key;

        // A refresh a minute later works out its own window, which no longer reaches the visit's first capture.
        const refresh = explorerWindow('24h', {}, new Date('2026-11-25T10:01:00Z'));
        expect(refresh.request.startTime && refresh.request.startTime > FIRST_CAPTURE).toBe(true);
        list.ensure();
        expect(list.key).toBe(shownKey);
        expect(fetchVisitCaptures).toHaveBeenCalledTimes(1);
        expect(list.captures.map((capture) => capture.frigate_event)).toEqual(['lead', 'last']);

        // The refresh fails, so nothing is published: the visit on screen keeps its captures and its window.
        list.ensure();
        expect([list.loaded, list.failed]).toEqual([true, false]);
        expect(fetchVisitCaptures).toHaveBeenCalledTimes(1);

        // A refresh that succeeds publishes its window with its visits, and only then are captures read in it.
        shown.publish(refresh);
        expect(list.key).not.toBe(shownKey);
        list.ensure();
        expect(fetchVisitCaptures).toHaveBeenCalledTimes(2);
        expect(fetchVisitCaptures.mock.calls[1][1]).toMatchObject({ startTime: refresh.request.startTime, endTime: refresh.request.endTime });
    });

    it('shows no window before the first read is published', () => {
        const shown = new ShownExplorerWindow();
        expect(shown.current).toEqual({ request: {}, start: null, end: null });
    });
});
