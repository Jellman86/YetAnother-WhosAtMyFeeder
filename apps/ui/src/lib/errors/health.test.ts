import { describe, expect, it } from 'vitest';

import { getFrigateMediaAdvisory, getVideoClassifierCardState } from './health';

describe('frigate media advisory', () => {
    const health = (started: number, dropReasons: Record<string, number>) => ({
        event_pipeline: { started_events: started, drop_reasons: dropReasons }
    });

    it('flags elevated when snapshot-unavailable drops are a material share of a real sample', () => {
        const advisory = getFrigateMediaAdvisory(health(100, { classify_snapshot_unavailable: 30 }));
        expect(advisory.elevated).toBe(true);
        expect(advisory.dropped).toBe(30);
        expect(advisory.rate).toBeCloseTo(0.3);
    });

    it('counts snapshot timeout drops too, but not config-driven filter drops', () => {
        const advisory = getFrigateMediaAdvisory(
            health(100, { classify_snapshot_unavailable: 10, classify_snapshot_timeout: 8, filter_low_confidence: 500 })
        );
        expect(advisory.dropped).toBe(18);
        expect(advisory.elevated).toBe(true);
    });

    it('stays quiet on a small sample even at a high rate', () => {
        const advisory = getFrigateMediaAdvisory(health(10, { classify_snapshot_unavailable: 9 }));
        expect(advisory.elevated).toBe(false);
    });

    it('stays quiet when the rate is low', () => {
        const advisory = getFrigateMediaAdvisory(health(1000, { classify_snapshot_unavailable: 5 }));
        expect(advisory.elevated).toBe(false);
        expect(advisory.dropped).toBe(5);
    });

    it('is safe with missing/empty health', () => {
        expect(getFrigateMediaAdvisory(null).elevated).toBe(false);
        expect(getFrigateMediaAdvisory({}).elevated).toBe(false);
        expect(getFrigateMediaAdvisory({ event_pipeline: {} }).dropped).toBe(0);
    });
});

describe('video classifier health card state', () => {
    it('derives processing when active jobs exist even if backend status is absent', () => {
        const state = getVideoClassifierCardState({
            video_classifier: {
                active: 1,
                pending: 0,
                circuit_open: false,
                failure_count: 0
            }
        });

        expect(state.status).toBe('processing');
        expect(state.summary).toContain('1 active');
    });

    it('prefers the explicit backend status when it is available', () => {
        const state = getVideoClassifierCardState({
            video_classifier: {
                status: 'queued',
                active: 0,
                pending: 3,
                circuit_open: false,
                failure_count: 0
            }
        });

        expect(state.status).toBe('queued');
    });
});
