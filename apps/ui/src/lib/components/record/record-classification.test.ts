import { describe, expect, it } from 'vitest';
import type { Detection } from '../../api';
import { recordClassificationKey } from './record-classification';

const base = { frigate_event: 'event-1', display_name: 'Great Tit', category_name: 'Parus major', manual_tagged: false } as Detection;

describe('recordClassificationKey', () => {
    it('changes when the species, its category or the owner confirmation changes', () => {
        const key = recordClassificationKey(base);
        expect(recordClassificationKey({ ...base, display_name: 'Dunnock' })).not.toBe(key);
        expect(recordClassificationKey({ ...base, category_name: 'Prunella modularis' })).not.toBe(key);
        expect(recordClassificationKey({ ...base, manual_tagged: true })).not.toBe(key);
        expect(recordClassificationKey({ ...base, frigate_event: 'event-2' })).not.toBe(key);
    });

    it('holds while only the analysis itself changes', () => {
        expect(recordClassificationKey({ ...base, ai_analysis: 'A note', ai_analysis_timestamp: '2026-11-17T09:00:00Z' })).toBe(recordClassificationKey(base));
    });
});
