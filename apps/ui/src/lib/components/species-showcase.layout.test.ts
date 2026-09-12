import { describe, expect, it } from 'vitest';
import showcaseSource from './SpeciesShowcase.svelte?raw';
import leaderboardSource from '../pages/Species.svelte?raw';
import en from '../i18n/locales/en.json';

describe('the leaderboard showcase (expanded view)', () => {
    it('expands the leader and keeps the rest as tiles that swap places with it', () => {
        expect(leaderboardSource).toContain("import SpeciesShowcase from '../components/SpeciesShowcase.svelte'");
        expect(leaderboardSource).not.toContain('TopSpeciesCollage');
        expect(showcaseSource).toContain('data-leaderboard-showcase');
        expect(showcaseSource).toContain('const [send, receive] = crossfade({');
        expect(showcaseSource).toContain('in:receive={{ key: expanded.key }}');
        expect(showcaseSource).toContain('out:send={{ key: tile.key }}');
        expect(showcaseSource).toContain('animate:flip={{ duration: reduceMotion ? 0 : MORPH_MS, easing: cubicOut }}');
        expect(showcaseSource).toContain('onclick={() => (chosenKey = tile.key)}');
        // Derived from the rows, so the first paint is already right and nothing swaps on load.
        expect(showcaseSource).toContain('const expandedKey = $derived(');
    });

    it('says where every photograph came from', () => {
        // This feeder's own crop first; a reference image only as a labelled stand-in; then a placeholder.
        expect(showcaseSource).toContain("return { url: withAuthParams(row.photo), source: 'feeder' }");
        expect(showcaseSource).toContain("return { url: row.reference, source: 'reference' }");
        expect(showcaseSource).toContain('data-showcase-reference-note');
        expect(showcaseSource).toContain('data-showcase-reference-badge');
        expect(showcaseSource).toContain("data-photo-source={picture?.source ?? 'none'}");
        expect(en.leaderboard.showcase_reference.toLowerCase()).toContain('not from this feeder');
        expect(en.leaderboard.showcase_reference_from).toContain('{source}');
        // A species brought forward is named by its rank, never as "most detected".
        expect(showcaseSource).toContain('{rankOf(expanded) === 1 ? eyebrow : rankEyebrow(rankOf(expanded))}');
        expect(en.leaderboard.showcase_rank_month).toBe('Rank {rank} this month');
    });

    it('moves only where motion is welcome', () => {
        expect(showcaseSource).toContain('let reduceMotion = $state(false)');
        expect(showcaseSource).toContain('duration: () => (reduceMotion ? 0 : MORPH_MS)');
        expect(showcaseSource).toContain('@media (prefers-reduced-motion: reduce)');
        expect(showcaseSource).toContain(':global(.reduced-motion) .showcase-drift');
        expect(showcaseSource).toContain('hover:-translate-y-1 hover:border-brand-400/70 hover:shadow-xl active:translate-y-0 active:scale-[0.98]');
    });

    it('degrades a broken photograph to the next honest source, and points past the tiles at the rankings', () => {
        expect(showcaseSource).toContain('function markFailed(url: string): void');
        expect(showcaseSource).toContain('data-showcase-more');
        expect(leaderboardSource).toContain("document.querySelector('[data-leaderboard-rankings]')?.scrollIntoView");
        expect(leaderboardSource).toContain('fetchLeaderboardPortraits(requestedSpan, controller.signal)');
        expect(leaderboardSource).toContain("logger.warn('Leaderboard portraits unavailable'");
    });
});
