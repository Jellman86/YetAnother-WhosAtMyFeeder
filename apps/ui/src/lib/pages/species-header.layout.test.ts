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
    const opening = speciesPageSource.lastIndexOf('<div', speciesPageSource.indexOf('data-leaderboard-span-bar'));
    const spanBar = speciesPageSource.slice(opening, speciesPageSource.indexOf('</div>', opening));

    it('runs from the shortest window to the longest, as the standard lists it', () => {
        const order = ['sort_by_day', 'sort_by_week', 'sort_by_month', 'sort_by_total'].map((key) => spanBar.indexOf(key));
        expect(order.every((at) => at > -1)).toBe(true);
        expect([...order].sort((a, b) => a - b)).toEqual(order);
    });

    it('is a named group of tabs, so the name is read', () => {
        expect(spanBar).toContain('role="group"');
        expect(spanBar).toContain("aria-label={$_('leaderboard.span_group'");
        expect(speciesPageSource).not.toContain("aria-label={$_('leaderboard.title')}");
    });
});
