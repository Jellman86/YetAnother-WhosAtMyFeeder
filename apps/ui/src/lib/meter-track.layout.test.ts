import { describe, expect, it } from 'vitest';

const sources = import.meta.glob(['./**/*.svelte'], { eager: true, query: '?raw', import: 'default' }) as Record<string, string>;

/**
 * A meter is a rounded track with a fill sized by a style width (a score bar, a level). Its track
 * is the `track` token, which design-tokens.contrast.test.ts holds at 3:1 against every status and
 * accent fill in every mode. On `line`, high contrast drew a 77% brand fill yellow on a yellow
 * track and the bar read as full (#991 review).
 */
describe('meters', () => {
    it('draw their fill on the track token, never on a rule colour', () => {
        const offenders: string[] = [];
        let meters = 0;
        for (const [file, source] of Object.entries(sources)) {
            for (const match of source.matchAll(/class="[^"]*\boverflow-hidden rounded-full (bg-[\w/-]+)[^"]*"[^>]*>\s*<span[^>]*style="width:/g)) {
                meters += 1;
                if (match[1] !== 'bg-track') offenders.push(`${file}: ${match[1]}`);
            }
            for (const match of source.matchAll(/class="[^"]*\bh-1 overflow-hidden rounded-full (bg-[\w/-]+)[^"]*"/g)) {
                meters += 1;
                if (match[1] !== 'bg-track') offenders.push(`${file}: ${match[1]}`);
            }
        }
        expect(meters).toBeGreaterThan(4);
        expect(offenders).toEqual([]);
    });
});
