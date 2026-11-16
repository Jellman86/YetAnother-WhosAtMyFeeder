import { describe, expect, it } from 'vitest';
import reviewQueueCard from './components/ReviewQueueCard.svelte?raw';
import reviewQueueModal from './components/ReviewQueueModal.svelte?raw';
import detectionPreview from './components/DetectionPreview.svelte?raw';
import feederPortrait from './components/FeederPortrait.svelte?raw';
import dashboard from './pages/Dashboard.svelte?raw';

const svelteSources = import.meta.glob('./**/*.svelte', { eager: true, query: '?raw', import: 'default' }) as Record<string, string>;

/**
 * One bird has one name and one score colour on a screen (layout-patterns.md §3 and §6). The
 * Dashboard drew the same visit three ways: the field log named it through the reader's naming
 * preference and banded its score, the review card printed the raw English label with every score
 * in amber, and the capture pop-out printed every score in the brand colour.
 */
describe('one name and one score colour for a visit', () => {
    it('names the review card, the queue and the portrait through the shared naming helper', () => {
        for (const [file, source] of Object.entries({ reviewQueueCard, reviewQueueModal, feederPortrait })) {
            expect(source, file).toContain('$birdNames(');
            // Printing the raw label skips the naming preference and the reader's language.
            expect(source.match(/\{\s*\w+\.display_name\s*\}/g) ?? [], file).toEqual([]);
            expect(source.match(/(?:species|name|primaryName)[:=]\s*\{?\s*\w+\.display_name\b/g) ?? [], file).toEqual([]);
        }
        expect(dashboard).not.toMatch(/values:\s*\{\s*species:\s*detection\.display_name/);
    });

    it('bands every printed classification score through scoreBand()', () => {
        for (const [file, source] of Object.entries({ reviewQueueCard, detectionPreview })) {
            expect(source, file).toMatch(/SCORE_TEXT\[scoreBand\(/);
        }
        // A score percentage with a fixed ink is the bug: the band decides the colour.
        const fixedInk = /class="[^"]*\btext-(?:brand|attention|success)-\d+[^"]*"[^>]*>\s*\{(?:score\(\w+\)|Math\.round\(\(\w+\.score[^}]*)\}%/;
        const offenders = Object.entries(svelteSources)
            .filter(([, source]) => fixedInk.test(source))
            .map(([file]) => file);
        expect(offenders).toEqual([]);
    });

    it('lets the pop-out name wrap instead of cutting it off at a larger text size', () => {
        const nameLine = detectionPreview.slice(detectionPreview.indexOf('{primaryName}') - 200, detectionPreview.indexOf('{primaryName}'));
        expect(nameLine).not.toContain('truncate');
        expect(nameLine).toContain('wrap-break-word');
    });
});
