import { describe, expect, it } from 'vitest';
import { uptimeCoverage } from './uptime-coverage';

const bucket = (hour: number, state: 'up' | 'down' | 'unknown') => ({ start: `2026-11-13T${String(hour).padStart(2, '0')}:00:00Z`, state, samples: state === 'up' ? 12 : 0 });

describe('uptimeCoverage', () => {
    it('covers the whole window only when every bucket was recorded', () => {
        const coverage = uptimeCoverage([bucket(0, 'up'), bucket(1, 'down'), bucket(2, 'up')], 60);
        expect(coverage).toEqual({ complete: true, recordedHours: 3, recordedSince: '2026-11-13T00:00:00Z' });
    });

    it('counts only recorded buckets and says where recording began', () => {
        const coverage = uptimeCoverage([bucket(0, 'unknown'), bucket(1, 'unknown'), bucket(2, 'up'), bucket(3, 'up')], 60);
        expect(coverage).toEqual({ complete: false, recordedHours: 2, recordedSince: '2026-11-13T02:00:00Z' });
    });

    it('has nothing to say about a window with no recording', () => {
        expect(uptimeCoverage([bucket(0, 'unknown')], 60)).toEqual({ complete: false, recordedHours: 0, recordedSince: null });
    });
});
