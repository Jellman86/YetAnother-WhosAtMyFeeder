import { describe, expect, it } from 'vitest';
import dayBarSource from './DayBar.svelte?raw';

/**
 * The day bar's figures arrive after the page is drawn. A figure that can carry a note (Unresolved,
 * Cross-confirmed, Birds found) keeps the note's line whether or not a note arrives: Unresolved has
 * none while visits wait, and dropping its reserved line moved everything below the bar up 18px on a
 * phone (CLS 0.125 at 390 px in the round-5 kit).
 */
describe('the day bar holds its height while its figures arrive', () => {
    it('keeps a noted figure\'s line after it is read, with or without a note', () => {
        expect(dayBarSource).toMatch(/\{:else if noted\}\s*<span class="flex h-4 items-center" aria-hidden="true"/);
        expect(dayBarSource).not.toContain('{:else if noted && value === null && pending}');
    });

    it('shows the placeholder bar in that line only while the figure is still loading', () => {
        expect(dayBarSource).toMatch(/\{#if value === null && pending\}\s*<span class="h-2\.5 w-20/);
    });
});
