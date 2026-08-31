import { describe, expect, it } from 'vitest';
import topVisitorsSource from './TopVisitors.svelte?raw';

describe('the top-visitors list survives a duplicated species', () => {
    // A duplicate key in a keyed each is a runtime crash in Svelte 5, and it
    // took the lower half of the dashboard down when the API split one bird
    // into two rows. The list dedupes before keying instead of trusting the
    // payload.
    it('merges duplicate species before the keyed each', () => {
        expect(topVisitorsSource).toContain('const merged = new Map');
        expect(topVisitorsSource).toContain('existing.count + item.count');
        const dedupeAt = topVisitorsSource.indexOf('const merged = new Map');
        const eachAt = topVisitorsSource.indexOf('(item.species)');
        expect(dedupeAt).toBeGreaterThan(-1);
        expect(eachAt).toBeGreaterThan(dedupeAt);
    });
});
