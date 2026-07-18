import { describe, expect, it } from 'vitest';
import speciesSource from './Species.svelte?raw';

describe('Species request lifecycle', () => {
    it('aborts superseded leaderboard loads and ignores stale results', () => {
        expect(speciesSource).toContain('leaderboardAbortController?.abort();');
        expect(speciesSource).toContain('const loadGeneration = ++leaderboardLoadGeneration;');
        expect(speciesSource).toContain('if (loadGeneration !== leaderboardLoadGeneration) return;');
        expect(speciesSource).toContain('signal: controller.signal');
    });

    it('limits enrichment fan-out and bounds the in-memory species cache', () => {
        expect(speciesSource).toContain('const MAX_SPECIES_INFO_CONCURRENCY = 3;');
        expect(speciesSource).toContain('const MAX_SPECIES_INFO_CACHE_ENTRIES = 100;');
        expect(speciesSource).toContain('await acquireSpeciesInfoSlot();');
        expect(speciesSource).toContain('pruneSpeciesInfoCache');
    });
});
