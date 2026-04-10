import { describe, expect, it } from 'vitest';

import { getVideoClassifierCardState } from './health';

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
