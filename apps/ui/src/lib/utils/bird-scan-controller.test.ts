import { afterEach, describe, expect, it, vi } from 'vitest';
import { createBirdScanController, birdScanMediaVersion } from './bird-scan-controller';
import type { BirdScanResponse } from '../api/media';

function state(status: BirdScanResponse['status']): BirdScanResponse {
    return { event_id: 'event', candidate_id: 'scene', status, available: true, unavailable_reason: null, error: null, result_count: status === 'completed' ? 0 : null, retained_previous: false, updated_at: null };
}
function deferred<T>() {
    let resolve!: (value: T) => void;
    const promise = new Promise<T>((done) => { resolve = done; });
    return { promise, resolve };
}
afterEach(() => vi.useRealTimers());
describe('bird scan polling', () => {
    it('shares in-flight reads, polls active work, and finishes zero-bird scans once', async () => {
        vi.useFakeTimers();
        const pending = deferred<BirdScanResponse>();
        const read = vi.fn().mockReturnValueOnce(pending.promise).mockResolvedValue(state('completed'));
        const completed = vi.fn();
        const change = vi.fn();
        const controller = createBirdScanController({ eventId: 'event', candidateId: 'scene', read, start: vi.fn(), onChange: change, onCompleted: completed, isVisible: () => true });
        const first = controller.refresh();
        void controller.refresh();
        expect(read).toHaveBeenCalledTimes(1);
        pending.resolve(state('running'));
        await first;
        await vi.advanceTimersByTimeAsync(2000);
        expect(read).toHaveBeenCalledTimes(2);
        expect(completed).toHaveBeenCalledTimes(1);
        expect(change.mock.lastCall?.[0].response.result_count).toBe(0);
        await vi.advanceTimersByTimeAsync(20_000);
        expect(read).toHaveBeenCalledTimes(2);
        controller.dispose();
    });
    it('does not poll hidden tabs and resumes one read when visible', async () => {
        vi.useFakeTimers();
        let visible = false;
        const read = vi.fn().mockResolvedValue(state('queued'));
        const controller = createBirdScanController({ eventId: 'event', candidateId: 'scene', read, start: vi.fn(), onChange: vi.fn(), onCompleted: vi.fn(), isVisible: () => visible });
        await controller.refresh();
        expect(read).not.toHaveBeenCalled();
        visible = true;
        await controller.visibilityChanged();
        expect(read).toHaveBeenCalledTimes(1);
        visible = false;
        await controller.visibilityChanged();
        await vi.advanceTimersByTimeAsync(20_000);
        expect(read).toHaveBeenCalledTimes(1);
        controller.dispose();
    });
    it('aborts and ignores a late previous-scene answer', async () => {
        const pending = deferred<BirdScanResponse>();
        const change = vi.fn();
        const completed = vi.fn();
        const read = vi.fn().mockReturnValue(pending.promise);
        const controller = createBirdScanController({ eventId: 'event', candidateId: 'scene', read, start: vi.fn(), onChange: change, onCompleted: completed, isVisible: () => true });
        const job = controller.refresh();
        const callsBeforeDispose = change.mock.calls.length;
        controller.dispose();
        expect(read.mock.calls[0][0].aborted).toBe(true);
        pending.resolve(state('completed'));
        await job;
        expect(change).toHaveBeenCalledTimes(callsBeforeDispose);
        expect(completed).not.toHaveBeenCalled();
    });
    it('deduplicates clicks and refreshes existing results after a cached completion', async () => {
        const pending = deferred<BirdScanResponse>();
        const start = vi.fn().mockReturnValue(pending.promise);
        const completed = vi.fn();
        const controller = createBirdScanController({ eventId: 'event', candidateId: 'scene', read: vi.fn(), start, onChange: vi.fn(), onCompleted: completed, isVisible: () => true });
        const job = controller.start(true);
        void controller.start(true);
        expect(start).toHaveBeenCalledTimes(1);
        expect(start.mock.calls[0][0]).toBe(true);
        pending.resolve(state('completed'));
        await job;
        expect(completed).toHaveBeenCalledTimes(1);
        controller.dispose();
    });
});

it('backs off failed requests, rejects another scene, and never replays an unconfirmed POST', async () => {
    vi.useFakeTimers();
    const change = vi.fn();
    const read = vi.fn().mockResolvedValueOnce({ ...state('completed'), candidate_id: 'other' }).mockResolvedValue(state('queued'));
    const start = vi.fn().mockRejectedValue(new Error('Response lost'));
    const completed = vi.fn();
    const controller = createBirdScanController({ eventId: 'event', candidateId: 'scene', read, start, onChange: change, onCompleted: completed, isVisible: () => true });
    await controller.start();
    expect(change.mock.lastCall?.[0].startUnconfirmed).toBe(true);
    await vi.advanceTimersByTimeAsync(9_999);
    expect(read).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(change.mock.lastCall?.[0].readError).toBe(true);
    expect(completed).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(10_000);
    expect(change.mock.lastCall?.[0].response.status).toBe('queued');
    expect(start).toHaveBeenCalledTimes(1);
    controller.dispose();
});


it('refreshes bird results when an unconfirmed POST completed before the first status read', async () => {
    vi.useFakeTimers();
    const completed = vi.fn();
    const read = vi.fn().mockResolvedValue(state('completed'));
    const start = vi.fn().mockRejectedValue(new Error('Response lost'));
    const controller = createBirdScanController({ eventId: 'event', candidateId: 'scene', read, start, onChange: vi.fn(), onCompleted: completed, isVisible: () => true });
    await controller.start();
    await vi.advanceTimersByTimeAsync(10_000);
    expect(completed).toHaveBeenCalledTimes(1);
    expect(start).toHaveBeenCalledTimes(1);
    await controller.refresh();
    expect(completed).toHaveBeenCalledTimes(1);
    controller.dispose();
});


it('requires the exact retained image revision and refuses missing or ambiguous versions', () => {
    expect(birdScanMediaVersion('/photo.jpg?v=old-revision&auth=example')).toBe('old-revision');
    expect(birdScanMediaVersion('https://example.test/photo.jpg?v=123-456')).toBe('123-456');
    for (const url of [null, '/photo.jpg', '/photo.jpg?v=', '/photo.jpg?v=a&v=b', '/photo.jpg?v=' + 'a'.repeat(129)]) {
        expect(birdScanMediaVersion(url)).toBeNull();
    }
});
