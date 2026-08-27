import { describe, expect, it } from 'vitest';

const sources = import.meta.glob('../**/*.svelte', { eager: true, query: '?raw', import: 'default' }) as Record<
    string,
    string
>;

/**
 * #259: "it is not clear when it is collapsed and where not, also it is not
 * clear what is in the section... I see the collapsable section implemented
 * differently across the app."
 *
 * The app has three disclosure mechanisms and they are not all the same kind of
 * control — a terminal panel and an inline "show technical details" link should
 * not look alike. What they must share is the contract a person needs to use
 * one: it says whether it is open, it is big enough to hit, and it shows that
 * it has keyboard focus.
 */
const SUMMARY = /<summary\b([^>]*)>/gs;

function offenders(check: (attrs: string, body: string) => boolean): string[] {
    const found: string[] = [];
    for (const [path, source] of Object.entries(sources)) {
        if (typeof source !== 'string') continue;
        for (const match of source.matchAll(SUMMARY)) {
            const attrs = match[1];
            const body = source.slice(match.index! + match[0].length, match.index! + match[0].length + 700);
            if (check(attrs, body)) {
                const line = source.slice(0, match.index).split('\n').length;
                found.push(`${path.split('/').pop()}:${line}`);
            }
        }
    }
    return found.sort();
}

describe('every disclosure carries the same affordances', () => {
    it('shows whether it is open', () => {
        // A caret that never changes, or no indicator at all, is what the
        // report means by "not clear when it is collapsed and where not".
        const missing = offenders(
            (attrs, body) =>
                !/rotate-180|group-open/.test(attrs + body) && !/\.hide'|\.show'|Hide |Show /.test(body)
        );
        expect(missing, 'these disclosures never say whether they are open').toEqual([]);
    });

    it('is big enough to hit', () => {
        // The visual standard puts the floor at min-h-11 (44px). Anything at or
        // above it passes: two disclosures already use min-h-12, and asserting
        // the literal class would have argued them down to the floor.
        const missing = offenders(attrs => {
            const match = attrs.match(/min-h-(\d+)/);
            return !match || Number(match[1]) < 11;
        });
        expect(missing, 'these disclosures are under the touch-target floor').toEqual([]);
    });

    it('shows that it has keyboard focus', () => {
        // Same WCAG 2.2 AA floor as every other control in the app.
        const missing = offenders(
            attrs => !/focus-visible:ring|focus:ring|focus-ring/.test(attrs)
        );
        expect(missing, 'these disclosures give a keyboard user no focus indicator').toEqual([]);
    });
});
