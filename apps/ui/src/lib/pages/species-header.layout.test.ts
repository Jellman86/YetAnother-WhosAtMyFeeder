import { describe, expect, it } from 'vitest';
import speciesPageSource from './Species.svelte?raw';

describe('species page header layout', () => {
    it('does not duplicate the global page header with a local leaderboard title row', () => {
        expect(speciesPageSource).not.toContain('<h2 class="text-2xl font-bold text-slate-900 dark:text-white">{$_(\'leaderboard.title\')}</h2>');
        expect(speciesPageSource).not.toContain("$_('leaderboard.species_count'");
        expect(speciesPageSource).not.toContain("$_('leaderboard.detections_count'");
    });
});
