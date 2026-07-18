import { describe, expect, it } from 'vitest';

import leaderboardSource from './Species.svelte?raw';

describe('leaderboard field-journal layout', () => {
    it('puts the working ranking surface before secondary analytics', () => {
        const rankings = leaderboardSource.indexOf('data-leaderboard-rankings');
        const analytics = leaderboardSource.indexOf('data-leaderboard-analytics');

        expect(rankings).toBeGreaterThan(-1);
        expect(analytics).toBeGreaterThan(rankings);
    });

    it('uses dedicated mobile and desktop ranking presentations', () => {
        expect(leaderboardSource).toContain('data-leaderboard-mobile-rankings');
        expect(leaderboardSource).toContain('data-leaderboard-desktop-rankings');
        expect(leaderboardSource).not.toContain('min-w-[900px]');
        expect(leaderboardSource).not.toContain('role="button"');
    });

    it('sorts explicitly by the selected source and deduplicates audio-only rows', () => {
        expect(leaderboardSource).toContain('function leaderboardTableRows(mode: SourceMode)');
        expect(leaderboardSource).toContain("mode === 'heard'");
        expect(leaderboardSource).toContain("mode === 'both'");
        expect(leaderboardSource).toContain('if (sciKey) usedAudioKeys.add(sciKey)');
        expect(leaderboardSource).toContain('if (nmKey) usedAudioKeys.add(nmKey)');
    });

    it('removes the tiny-label, emoji-medal, and card-wall treatments', () => {
        expect(leaderboardSource).not.toMatch(/text-\[(?:9|10|11)px\]/);
        expect(leaderboardSource.match(/card-base/g) ?? []).toHaveLength(0);
        expect(leaderboardSource).not.toMatch(/[🐦🥇🥈🥉]/u);
        expect(leaderboardSource).not.toContain('topSpecies');
    });

    it('uses accessible section icons and touch-sized controls', () => {
        expect(leaderboardSource.match(/data-leaderboard-section-icon/g) ?? []).toHaveLength(3);
        expect(leaderboardSource.match(/data-leaderboard-section-icon[^>]+aria-hidden="true"/g) ?? []).toHaveLength(3);
        expect(leaderboardSource).toContain('min-h-11');
        expect(leaderboardSource).toContain('focus-visible:ring-2 focus-visible:ring-teal-500');
    });
});
