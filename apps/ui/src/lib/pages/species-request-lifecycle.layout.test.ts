import { describe, expect, it } from 'vitest';
import speciesSource from './Species.svelte?raw';

describe('Species request lifecycle', () => {
    it('aborts superseded leaderboard loads and ignores stale results', () => {
        expect(speciesSource).toContain('leaderboardAbortController?.abort();');
        expect(speciesSource).toContain('const loadGeneration = ++leaderboardLoadGeneration;');
        expect(speciesSource).toContain('const superseded = () => loadGeneration !== leaderboardLoadGeneration || controller.signal.aborted;');
        expect(speciesSource.match(/if \(superseded\(\)\) return;/g)?.length ?? 0).toBeGreaterThanOrEqual(2);
        expect(speciesSource).toContain('signal: controller.signal');
    });

    it('limits enrichment fan-out and bounds the in-memory species cache', () => {
        expect(speciesSource).toContain('const MAX_SPECIES_INFO_CONCURRENCY = 3;');
        expect(speciesSource).toContain('const MAX_SPECIES_INFO_CACHE_ENTRIES = 100;');
        expect(speciesSource).toContain('await acquireSpeciesInfoSlot();');
        expect(speciesSource).toContain('pruneSpeciesInfoCache');
    });
});
