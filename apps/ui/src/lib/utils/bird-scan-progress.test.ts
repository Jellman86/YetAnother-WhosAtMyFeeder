import { describe, expect, it } from 'vitest';
import type { BirdScanResponse } from '../api/media';
import { birdScanElapsedSeconds, birdScanProgress } from './bird-scan-progress';

function running(stage: BirdScanResponse['stage'], done?: number, total?: number): BirdScanResponse {
    return {
        event_id: 'e', candidate_id: 'c', status: 'running', available: true, unavailable_reason: null, error: null,
        result_count: null, retained_previous: false, updated_at: null, stage, stage_done: done ?? null, stage_total: total ?? null
    };
}

describe('bird scan progress', () => {
    it('fills finished steps and the named share of the naming step', () => {
        expect(birdScanProgress(running('naming', 2, 5))).toEqual({ step: 2, stage: 'naming', segments: [1, 0.4, 0, 0] });
    });

    it('never shows a step done before the next one starts', () => {
        expect(birdScanProgress(running('detecting')).segments).toEqual([0, 0, 0, 0]);
        expect(birdScanProgress(running('saving')).segments).toEqual([1, 1, 1, 0]);
    });

    it('names no step when the server cannot say which one is running', () => {
        expect(birdScanProgress(running(null))).toEqual({ step: null, stage: null, segments: [0, 0, 0, 0] });
        expect(birdScanProgress({ ...running('naming'), status: 'queued' }).step).toBeNull();
    });

    it('treats a naming step with nothing to name as just started', () => {
        expect(birdScanProgress(running('naming', 0, 0)).segments).toEqual([1, 0, 0, 0]);
    });

    it('counts from the server start, or from first sight when the start is missing or ahead of this clock', () => {
        const now = Date.parse('2026-10-10T10:00:30Z');
        expect(birdScanElapsedSeconds('2026-10-10T10:00:00Z', now - 5_000, now)).toBe(30);
        expect(birdScanElapsedSeconds(null, now - 5_000, now)).toBe(5);
        expect(birdScanElapsedSeconds('2026-10-10T10:01:00Z', now - 5_000, now)).toBe(5);
    });
});
