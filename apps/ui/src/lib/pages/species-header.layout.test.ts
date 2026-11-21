import { describe, expect, it } from 'vitest';
import speciesPageSource from './Species.svelte?raw';

describe('species page header layout', () => {
    it('does not duplicate the global page header with a local leaderboard title row', () => {
        expect(speciesPageSource).not.toContain('<h2 class="text-2xl font-bold text-slate-900 dark:text-white">{$_(\'leaderboard.title\')}</h2>');
        expect(speciesPageSource).not.toContain("$_('leaderboard.species_count'");
        expect(speciesPageSource).not.toContain("$_('leaderboard.detections_count'");
    });
});

describe('leaderboard span bar', () => {
    const options = speciesPageSource.slice(speciesPageSource.indexOf('const spanOptions'), speciesPageSource.indexOf('const sourceOptions'));
    const spanBar = speciesPageSource.slice(speciesPageSource.lastIndexOf('<Segmented', speciesPageSource.indexOf('data-leaderboard-span-bar')), speciesPageSource.indexOf('data-leaderboard-span-bar'));

    it('runs from the shortest window to the longest, as the standard lists it', () => {
        const order = ['sort_by_day', 'sort_by_week', 'sort_by_month', 'sort_by_total'].map((key) => options.indexOf(key));
        expect(order.every((at) => at > -1)).toBe(true);
        expect([...order].sort((a, b) => a - b)).toEqual(order);
    });

    it('is a named group of tabs, so the name is read', () => {
        // The shared control is a named group; on a phone the same choice is a labelled select.
        expect(spanBar).toContain("label={$_('leaderboard.span_group'");
        expect(speciesPageSource).toMatch(/<span class="sr-only">\{\$_\('leaderboard\.span_group'[^<]*<\/span>\s*<select[^>]*bind:value=\{span\}/);
        expect(speciesPageSource).not.toContain("aria-label={$_('leaderboard.title')}");
    });
});

describe('one window for the Leaderboard', () => {
    it('names the window the wall, the rankings and the composition count over one way', () => {
        // The wall said "Last 30 days" beside rankings that said "Month · 18 Oct-17 Nov" for the same span.
        expect(speciesPageSource).not.toMatch(/leaderboard\.last_(?:7|30)_days/);
        expect(speciesPageSource).toContain("return `${spanLabel()} · ${formatRangeCompact(leaderboardWindow?.start, leaderboardWindow?.end)}`;");
        // The composition sits under the Analytics window, so it states its total, not the window again.
        expect(speciesPageSource).not.toMatch(/description=\{`\$\{selectedCountLabel\(\)\}/);
    });
});

