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
        expect(leaderboardSource.match(/data-leaderboard-section-icon/g) ?? []).toHaveLength(2);
        expect(leaderboardSource.match(/data-leaderboard-section-icon[^>]+aria-hidden="true"/g) ?? []).toHaveLength(2);
        expect(leaderboardSource).toContain('min-h-11');
        expect(leaderboardSource).toContain('focus-visible:ring-2 focus-visible:ring-brand-500');
    });

    it('uses round species portraits throughout the ranking surface', () => {
        expect(leaderboardSource.match(/data-leaderboard-species-portrait/g) ?? []).toHaveLength(2);
        expect(leaderboardSource.match(/data-leaderboard-species-portrait[^>]+rounded-full/g) ?? []).toHaveLength(2);
    });

    it('exposes toggle state and table headings to assistive technology', () => {
        expect(leaderboardSource).toContain("aria-pressed={span === 'month'}");
        expect(leaderboardSource).toContain("aria-pressed={sourceMode === 'seen'}");
        expect(leaderboardSource.match(/scope="col"/g)?.length ?? 0).toBeGreaterThanOrEqual(6);
        expect(leaderboardSource).toContain('tabular-nums');
    });

    it('links BirdNET-enabled leaderboards to the complete listening history', () => {
        expect(leaderboardSource).toContain("import { toAppPath } from '../app/url-base'");
        expect(leaderboardSource).toContain('data-leaderboard-audio-history-link');
        expect(leaderboardSource).toContain("href={toAppPath('/audio')}");
        expect(leaderboardSource).toContain("$_('nav.audio_history')");
    });

    it('does not turn an unavailable BirdNET result into measured zero activity', () => {
        expect(leaderboardSource).toContain("type AudioLoadState = 'disabled' | 'loading' | 'ready' | 'error'");
        expect(leaderboardSource).toContain("audioLoadState = 'error'");
        expect(leaderboardSource).toContain("sourceMode !== 'seen' && audioLoadState === 'error'");
        expect(leaderboardSource).toContain('leaderboard.audio_unavailable_title');
        expect(leaderboardSource).toContain('let leaderboardRows = $derived(leaderboardTableRows(sourceMode))');
    });

    it('uses source-aware comparisons in both ranking layouts', () => {
        expect(leaderboardSource).toContain('heard_prev_count: heard?.heard_prev_count ?? null');
        expect(leaderboardSource).toContain('trendForMode(item, sourceMode)');
        expect(leaderboardSource).toContain('deltaForMode(item, sourceMode)');
        expect(leaderboardSource).toContain('activityTimestampForMode(item, sourceMode)');
    });

    it('keeps distinct rising and recent facts without repeating the leader', () => {
        expect(leaderboardSource).toContain('data-leaderboard-highlights');
        expect(leaderboardSource).toContain('topByTrend.species !== sourceLeader?.species');
        expect(leaderboardSource).toContain('mostRecent.species !== sourceLeader?.species');
    });
});
