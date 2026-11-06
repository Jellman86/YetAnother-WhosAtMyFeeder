import { describe, expect, it } from 'vitest';
// @ts-expect-error -- node:fs resolves at runtime, not in the app tsconfig
import { readFileSync } from 'node:fs';

const appCss = readFileSync(new URL('./app.css', import.meta.url), 'utf8');

function rule(selector: string): string {
    const start = appCss.indexOf(`${selector} {`);
    if (start < 0) return '';
    return appCss.slice(start, appCss.indexOf('}', start));
}

/** The shared controls carry their own touch target and stay visible in both modes. */
describe('the kit controls', () => {
    it('gives a tab and an icon button the 44px floor and a keyboard ring', () => {
        expect(rule('.tab-button')).toContain('min-h-11');
        expect(rule('.tab-button')).toContain('focus-ring');
        expect(rule('.btn-icon')).toContain('min-h-11');
        expect(rule('.btn-icon')).toContain('min-w-11');
    });

    it('draws the select chevron in a fixed colour for each mode, since a data URI cannot read currentColor', () => {
        const light = rule('.select-base');
        const dark = rule('.dark .select-base');
        expect(light).not.toContain('currentColor');
        expect(light).toContain("stroke='%2364748b'");
        expect(dark).toContain('background-image');
        expect(dark).toContain("stroke='%2394a3b8'");
    });
});
