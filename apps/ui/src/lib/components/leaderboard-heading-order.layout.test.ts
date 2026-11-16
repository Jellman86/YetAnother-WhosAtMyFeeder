import { describe, expect, it } from 'vitest';
import speciesSource from '../pages/Species.svelte?raw';
import checksSource from './SpeciesChecks.svelte?raw';
import wallSource from './CaptureWall.svelte?raw';

const template = speciesSource.slice(speciesSource.lastIndexOf('</script>'));

/**
 * The page's h1 is in the header. In Heard mode there is no wall, so its h2 is absent and
 * "Full rankings" as an h3 skipped a level. Every section of the page is an h2 in its own right,
 * and what sits inside a section is an h3, whichever view is chosen.
 */
describe('the Leaderboard heading order', () => {
    it('makes each page section an h2, with or without the wall above it', () => {
        expect(wallSource).toMatch(/<h2\b/);
        expect(checksSource).toMatch(/<h2 id="spotlight-checks-title"/);
        for (const key of ['leaderboard.full_rankings', 'leaderboard.analytics_section', 'leaderboard.no_species', 'leaderboard.audio_unavailable_title']) {
            expect(template, key).toMatch(new RegExp(`<h2\\b[^>]*>\\{\\$_\\('${key.replace('.', '\\.')}'`));
        }
    });

    it('never skips from a section to an h4', () => {
        expect(template.match(/<h[4-6]\b/g) ?? []).toEqual([]);
        expect(template.match(/<h3\b/g)?.length).toBeGreaterThan(0);
    });
});
