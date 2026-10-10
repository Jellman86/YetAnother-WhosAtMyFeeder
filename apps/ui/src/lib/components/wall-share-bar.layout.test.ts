import { describe, expect, it } from 'vitest';
import wallSource from './CaptureWall.svelte?raw';
import checksSource from './SpeciesChecks.svelte?raw';
import leaderboardSource from '../pages/Species.svelte?raw';
import en from '../i18n/locales/en.json';

describe('the leaderboard share bar, now the wall\'s navigation', () => {
    it('sits on top of the wall in place of species chips, and no longer has a component of its own', () => {
        expect(leaderboardSource).not.toContain('SpeciesShareBar');
        expect(leaderboardSource).not.toContain('SpeciesSpotlight');
        expect(wallSource).toContain('data-capture-wall-share');
        expect(wallSource).not.toContain('class="chip');
        // The photographs the wall shows come from the capture list; the portraits only say which
        // visits have a film made.
        expect(leaderboardSource).toContain('fetchLeaderboardPortraits(requestedSpan, controller.signal, SPOTLIGHT_PORTRAITS)');
    });

    it('fills the bar from the same segments and colours as before', () => {
        expect(wallSource).toContain('const segments = $derived(shareSegments(rows));');
        expect(wallSource).toContain('const groups = $derived(spotlightGroups(rows));');
        expect(leaderboardSource).toContain('colourFor={(key) => (key ? speciesSeriesColor(speciesSlot().get(key) ?? SPECIES_SERIES_SLOTS, isDark()) : otherSeriesColor(isDark()))}');
    });

    it('opens a segment out on hover and focus, and pins its highlight on click, which is all touch has', () => {
        expect(wallSource).toContain("onpointerenter={(event) => event.pointerType !== 'touch' && segmentEnter(segment.key)}");
        expect(wallSource).toContain("event.currentTarget.matches(':focus-visible')");
        expect(wallSource).toContain('pinnedSegment = pinned === key ? null : key;');
        expect(wallSource).toContain('aria-pressed={segment.kind === \'checks\' ? undefined : pinned === segment.key}');
        // Opening out is a flex weight, so a thin segment becomes readable and the rest give way.
        expect(wallSource).toContain('const OPEN_SHARE = 30;');
        expect(wallSource).toContain('transition: flex-grow');
        // The share, count and unit are said when open, never colour alone.
        expect(wallSource).toContain('{percentOfTotal(segment.count)} · {segment.count.toLocaleString()} {countLabel(segment.count)}');
        // The ink on every segment is chosen for contrast, not fixed, and the ring shows on any colour.
        expect(wallSource).toContain('style:color={readableInk(colour)}');
        expect(wallSource).toContain('box-shadow: inset 0 0 0 2px #fff;');
    });

    it('lights the species of a segment, or of everyone else together, and dims the rest', () => {
        expect(wallSource).toContain("activeSegment === 'others' ? othersKeys");
        expect(wallSource).toContain('const lit = $derived.by');
        expect(wallSource).toContain("{lit !== null ? 'has-active' : ''}");
        // A highlight always points at something: a key that left the bar, or a species with no visit on the wall, dims nothing.
        expect(wallSource).toContain('segmentKeys.has(pinnedSegment)');
        expect(wallSource).toContain('shown.some((tile) => tile.speciesKey !== null && keys.has(tile.speciesKey))');
        // A pinned species can be opened from the header; a click on the bar never leaves the page.
        expect(wallSource).toContain('data-capture-wall-open');
    });

    it('points the needs-a-check segment at the flagged species, named apart for a person to check', () => {
        expect(wallSource).toContain("if (kind === 'checks') {\n            onchecks();");
        expect(leaderboardSource).toContain('onchecks={scrollToChecks}');
        expect(checksSource).toContain('data-spotlight-checks');
        expect(checksSource).toContain('{#each checks as row (row.key)}');
        expect(en.leaderboard.spotlight_needs_check).toBe('Needs a check');
    });

    it('has an English string for every wall key the page asks for, so no language falls back silently', () => {
        const keys = new Set<string>();
        for (const source of [wallSource, leaderboardSource]) {
            for (const match of source.matchAll(/\$_\('leaderboard\.(wall_[a-z_]+)'/g)) keys.add(match[1]);
        }
        expect(keys.size).toBeGreaterThan(10);
        const strings: Record<string, unknown> = en.leaderboard;
        for (const key of keys) expect(strings[key], key).toBeTypeOf('string');
    });
});
