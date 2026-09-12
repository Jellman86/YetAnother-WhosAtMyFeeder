import { describe, expect, it } from 'vitest';
import showcaseSource from './SpeciesShowcase.svelte?raw';
import leaderboardSource from '../pages/Species.svelte?raw';
import en from '../i18n/locales/en.json';

describe('the leaderboard showcase (expanded view)', () => {
    it('expands the leader and keeps the rest as tiles that trade places with it', () => {
        expect(leaderboardSource).toContain("import SpeciesShowcase from '../components/SpeciesShowcase.svelte'");
        expect(leaderboardSource).not.toContain('TopSpeciesCollage');
        expect(showcaseSource).toContain('data-leaderboard-showcase');
        // One element per species for its whole life: the same keyed item is a tile or the hero.
        expect(showcaseSource).toContain('{#each orderedRows as row, index (row.key)}');
        expect(showcaseSource).toContain("{@const isHero = row.key === expandedKey}");
        expect(showcaseSource).toContain('onclick={() => bringForward(row.key)}');
        // The chosen species takes the leader's place and the leader takes its slot; nothing else moves.
        expect(showcaseSource).toContain('displayOrder = swapDisplayOrder(');
        // Derived from the rows, so the first paint is already right and nothing swaps on load.
        expect(showcaseSource).toContain('const expandedKey = $derived(');
    });

    it('moves the two boxes from where they were to where they are, measured, never guessed', () => {
        // No crossfade pairing: rects are taken before the change and after the DOM update, and the
        // element itself animates between them with width and height so the photograph is
        // re-cropped as it grows rather than stretched.
        expect(showcaseSource).not.toContain('crossfade');
        expect(showcaseSource).not.toContain('animate:flip');
        expect(showcaseSource).toContain('before.set(candidate, element.getBoundingClientRect())');
        expect(showcaseSource).toContain('await tick();');
        expect(showcaseSource).toContain('const to = element.getBoundingClientRect();');
        expect(showcaseSource).toContain("transform: `translate(${from.left - to.left}px, ${from.top - to.top}px)`");
        expect(showcaseSource).toContain('width: `${from.width}px`');
        expect(showcaseSource).toContain("{ transform: 'none', width: `${to.width}px`, height: `${to.height}px` }");
        // The grid's tracks come from the container, so a box in flight never resizes a cell.
        expect(showcaseSource).toContain('grid-auto-rows: minmax(0, 1fr);');
        expect(showcaseSource).toContain('aspect-ratio: 7.05 / 3;');
        expect(showcaseSource).toContain('grid-template-columns: minmax(0, 4.05fr) repeat(3, minmax(0, 1fr));');
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
        expect(showcaseSource).toContain('{rankOf(row) === 1 ? eyebrow : rankEyebrow(rankOf(row))}');
        expect(en.leaderboard.showcase_rank_month).toBe('Rank {rank} this month');
    });

    it('moves only where motion is welcome', () => {
        expect(showcaseSource).toContain('let reduceMotion = $state(false)');
        expect(showcaseSource).toContain('if (reduceMotion) return;');
        expect(showcaseSource).toContain('@media (prefers-reduced-motion: reduce)');
        expect(showcaseSource).toContain(':global(.reduced-motion) .showcase-drift');
        expect(showcaseSource).toContain('hover:-translate-y-1 hover:border-brand-400/70 hover:shadow-xl active:translate-y-0 active:scale-[0.98]');
        // The rise plays once on first paint, and its fill never outlives it (that would swallow the hover lift).
        expect(showcaseSource).toContain('class:showcase-intro={!introDone}');
        expect(showcaseSource).toContain('cubic-bezier(0.2, 0.7, 0.2, 1) backwards');
        // Keyboard focus follows the species it brought forward; the tile's button is gone with the tile.
        expect(showcaseSource).toContain("itemFor(key)?.querySelector<HTMLElement>('button')?.focus({ preventScroll: true });");
    });

    it('degrades a broken photograph to the next honest source, and points past the tiles at the rankings', () => {
        expect(showcaseSource).toContain('function markFailed(url: string): void');
        expect(showcaseSource).toContain('data-showcase-more');
        expect(leaderboardSource).toContain("document.querySelector('[data-leaderboard-rankings]')?.scrollIntoView");
        expect(leaderboardSource).toContain('fetchLeaderboardPortraits(requestedSpan, controller.signal)');
        expect(leaderboardSource).toContain("logger.warn('Leaderboard portraits unavailable'");
    });
});
