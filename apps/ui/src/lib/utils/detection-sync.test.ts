import { describe, expect, it } from 'vitest';
import type { Detection } from '../api';
import { withLiveFields } from './detection-sync';

const record = {
    frigate_event: 'evt-1',
    display_name: 'Dunnock',
    score: 0.8,
    detection_time: '2026-11-26T08:00:00Z',
    camera_name: 'feeder',
    is_hidden: false
} as Detection;

describe('an open record follows the live store', () => {
    it('keeps the same record when nothing it shows has changed', () => {
        expect(withLiveFields(record, { camera_name: 'feeder' })).toBe(record);
        expect(withLiveFields(record, undefined)).toBe(record);
    });

    it('takes the fields the store changed, and ignores the ones it left undefined', () => {
        const next = withLiveFields(record, { display_name: 'Robin', score: undefined, bird_summary: null });
        expect(next).not.toBe(record);
        expect(next.display_name).toBe('Robin');
        expect(next.score).toBe(0.8);
    });

    it('notices a bird count change', () => {
        const counted = withLiveFields(record, { bird_summary: { count: 2 } as unknown as Detection['bird_summary'] });
        expect(counted).not.toBe(record);
    });
});
