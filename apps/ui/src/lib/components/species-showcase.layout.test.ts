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
        expect(showcaseSource).toContain('out:leave={{ key: tile.key }}');
        expect(showcaseSource).toContain('out:leave={{ key: expanded.key }}');
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

    it('takes a leaving photograph out of flow so nothing below it moves', () => {
        // The departing hero and tile stay in the DOM until the morph ends; pinned as absolute
        // boxes they no longer hold a grid cell, so the new hero and the tile grid stay put.
        expect(showcaseSource).toContain('function leave(node: HTMLElement, params: { key: string })');
        expect(showcaseSource).toContain("position: 'absolute'");
        expect(showcaseSource).toContain('return send(node, params);');
        expect(showcaseSource).toContain('class="relative grid gap-3 md:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]"');
        // The rise plays once on first paint, and its fill never outlives it (that would swallow the hover lift).
        expect(showcaseSource).toContain('class:showcase-intro={!introDone}');
        expect(showcaseSource).toContain('cubic-bezier(0.2, 0.7, 0.2, 1) backwards');
        expect(showcaseSource).not.toContain('cubic-bezier(0.2, 0.7, 0.2, 1) both');
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
