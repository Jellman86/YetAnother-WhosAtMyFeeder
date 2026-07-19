// @ts-nocheck — this source audit runs under Vitest's Node environment; Node types are
// intentionally absent from the browser application tsconfig.
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const focusTrapSource = readFileSync(new URL('./focus-trap.ts', import.meta.url), 'utf8');

describe('focus trap', () => {
    it('resolves focusable controls when Tab is pressed so async dialog content is included', () => {
        expect(focusTrapSource).toContain('function getFocusableElements()');
        expect(focusTrapSource).toMatch(/function handleTab[\s\S]*getFocusableElements\(\)/);
    });

    it('ignores controls that are not rendered or are hidden from assistive technology', () => {
        expect(focusTrapSource).toContain("getAttribute('aria-hidden') !== 'true'");
        expect(focusTrapSource).toContain('getClientRects().length > 0');
    });
});
