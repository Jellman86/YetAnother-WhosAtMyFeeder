import { describe, expect, it } from 'vitest';
import { historyIndexOf, withHistoryIndex } from './history-index';

describe('history positions', () => {
    it('records a position without dropping what an entry already holds', () => {
        const state = withHistoryIndex({ scroll: 120 }, 3);
        expect(state).toEqual({ scroll: 120, yawamfHistoryIndex: 3 });
        expect(historyIndexOf(state)).toBe(3);
    });

    it('has no position for an entry the app did not write', () => {
        expect(historyIndexOf(null)).toBeNull();
        expect(historyIndexOf({ yawamfHistoryIndex: '2' })).toBeNull();
        expect(historyIndexOf(withHistoryIndex(null, 0))).toBe(0);
    });
});
