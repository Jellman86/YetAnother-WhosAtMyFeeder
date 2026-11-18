import { describe, expect, it } from 'vitest';
import settingsSource from './Settings.svelte?raw';

/**
 * An address that names a part further down a section (a former tab's address such as
 * /settings/beta) lands there without moving under the reader. The round-5 kit measured a layout
 * shift of 0.60 at 1440 px and 1.15 at 390 px for /settings/beta: the page scrolled while the parts
 * above it were still filling in.
 */
describe('a Settings part address lands in place', () => {
    const reveal = settingsSource.slice(settingsSource.indexOf('async function revealPart'), settingsSource.indexOf('// The fragment that names a part.'));

    it('scrolls once the section has stopped changing size', () => {
        expect(reveal).toContain('await layoutSettled(watchElementSize(sectionRoot));');
        expect(reveal.indexOf('layoutSettled(')).toBeLessThan(reveal.lastIndexOf('scrollIntoView'));
    });

    it('leaves a reader who scrolled meanwhile, or a newer address, where they are', () => {
        expect(reveal).toContain('if (generation !== revealGeneration || Math.abs(window.scrollY - startY) > 1) return;');
    });

    it('finds the part again before scrolling, since a part can be drawn again while it waits', () => {
        const settled = reveal.indexOf('await layoutSettled(');
        expect(reveal.indexOf('document.querySelector<HTMLElement>(`[data-settings-part="${part}"]`)?.scrollIntoView', settled)).toBeGreaterThan(settled);
    });
});
