import { describe, expect, it } from 'vitest';
import { TEXT_SIZE_SCALE } from './lib/stores/theme.svelte';
// @ts-expect-error -- node:fs resolves at runtime, not in the app tsconfig
import { readFileSync } from 'node:fs';

const appCss = readFileSync(new URL('./app.css', import.meta.url), 'utf8');

/**
 * Every size in the kit is rem, so one root size scales the app. On a large display the page
 * used to stay at laptop size, with the field log and Explorer read at 10-14px across 2560px.
 * The smallest print never falls under 12px, at any text size.
 */
describe('the type scale on large displays', () => {
    const root = appCss.match(/\nhtml \{([^}]*)\}/)?.[1] ?? '';

    it('grows the root size with the window, from the reader’s own size to a cap', () => {
        expect(root.replace(/\s+/g, '')).toContain('font-size:calc(clamp(100%,calc(100%+(100vw-1280px)/256),125%)*var(--text-scale,1))');
    });

    it('starts from a percentage, so the browser text-size setting still applies', () => {
        expect(root).not.toMatch(/font-size:\s*\d+px/);
    });

    it('keeps a 44px touch target at the smaller text sizes', () => {
        expect(appCss).toContain('--spacing-11: max(2.75rem, 44px);');
    });

    describe('the floor under the small steps', () => {
        const steps: Record<string, number> = { '3xs': 0.6875, '2xs': 0.75, xs: 0.75, sm: 0.875 };
        // Appearance sizes from smallest to largest.
        const scales = Object.values(TEXT_SIZE_SCALE).sort((a, b) => a - b);
        /** The size a step is drawn at: its rem, or the floor, whichever is larger. */
        const drawn = (rem: number, browserPx: number, scale: number): number => {
            const root = browserPx * scale;
            return Math.max(rem * root, (0.5 * root) / scale + root / 3);
        };

        it('is written in rem, part from the browser size and part from the Appearance size', () => {
            expect(appCss).toContain('--text-floor: calc(0.5rem / var(--text-scale, 1) + 1rem / 3);');
            for (const [step, rem] of Object.entries(steps)) {
                expect(appCss, step).toContain(`--text-${step}: max(${rem}rem, var(--text-floor));`);
            }
            expect(appCss).not.toMatch(/--text-[\w-]+:[^;]*\d+px/);
        });

        it('is 12px at the smallest Appearance size and never under it', () => {
            for (const rem of Object.values(steps)) {
                expect(drawn(rem, 16, scales[0])).toBeCloseTo(12, 6);
                for (const scale of scales) expect(drawn(rem, 16, scale)).toBeGreaterThanOrEqual(12 - 1e-9);
            }
        });

        it('grows with every Appearance step: a larger setting never leaves small print the same size', () => {
            for (const [step, rem] of Object.entries(steps)) {
                for (let index = 1; index < scales.length; index += 1) {
                    expect(drawn(rem, 16, scales[index]), `${step} at ${scales[index]}`).toBeGreaterThan(drawn(rem, 16, scales[index - 1]) + 0.3);
                }
            }
        });

        it('doubles when the browser text size doubles', () => {
            for (const scale of scales) {
                for (const rem of Object.values(steps)) expect(drawn(rem, 32, scale)).toBeCloseTo(2 * drawn(rem, 16, scale), 6);
            }
        });

        it('never inverts the steps', () => {
            for (const scale of scales) {
                expect(drawn(steps.sm, 16, scale)).toBeGreaterThanOrEqual(drawn(steps.xs, 16, scale));
                expect(drawn(steps.xs, 16, scale)).toBeGreaterThanOrEqual(drawn(steps['3xs'], 16, scale));
            }
        });
    });
});
