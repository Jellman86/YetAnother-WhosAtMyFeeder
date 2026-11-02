import { describe, expect, it } from 'vitest';
import { needsYourCall, type NeedsYourCallInput } from './needs-your-call';

const measuredClear: NeedsYourCallInput = {
    canReview: true,
    queueStatus: 'ready',
    queueTotal: 0,
    checksStatus: 'ready',
    checkCount: 0
};

describe('needsYourCall', () => {
    it('says nothing is waiting only when both visits and species checks were measured as zero', () => {
        expect(needsYourCall(measuredClear)).toEqual({ visible: true, visits: 'clear', checks: 'clear', total: 0, nothingWaiting: true });
    });

    it('does not claim nothing is waiting while the species check is loading', () => {
        const state = needsYourCall({ ...measuredClear, checksStatus: 'loading' });
        expect(state.nothingWaiting).toBe(false);
        expect(state.visits).toBe('clear');
        expect(state.checks).toBe('loading');
    });

    it('does not claim nothing is waiting when the species check could not be read', () => {
        const state = needsYourCall({ ...measuredClear, checksStatus: 'unavailable' });
        expect(state.nothingWaiting).toBe(false);
        expect(state.checks).toBe('unavailable');
    });

    it('does not claim nothing is waiting while the visits are loading', () => {
        const state = needsYourCall({ ...measuredClear, queueStatus: 'loading' });
        expect(state.nothingWaiting).toBe(false);
        expect(state.visits).toBe('loading');
    });

    it('counts one species check as waiting work', () => {
        expect(needsYourCall({ ...measuredClear, checkCount: 1 })).toEqual({
            visible: true,
            visits: 'clear',
            checks: 'waiting',
            total: 1,
            nothingWaiting: false
        });
    });

    it('adds a species check to the unidentified visits', () => {
        const state = needsYourCall({ ...measuredClear, queueTotal: 3, checkCount: 1 });
        expect(state.total).toBe(4);
        expect(state.visits).toBe('waiting');
        expect(state.checks).toBe('waiting');
    });

    it('keeps shown work while a later reading is in flight', () => {
        const state = needsYourCall({ ...measuredClear, queueStatus: 'loading', queueTotal: 2, checksStatus: 'unavailable', checkCount: 0 });
        expect(state.visits).toBe('waiting');
        expect(state.total).toBe(2);
    });

    it('hides the panel from a guest, as it always has', () => {
        const state = needsYourCall({ ...measuredClear, canReview: false, checkCount: 1, queueTotal: 2 });
        expect(state).toEqual({ visible: false, visits: 'clear', checks: 'clear', total: 0, nothingWaiting: false });
    });
});
