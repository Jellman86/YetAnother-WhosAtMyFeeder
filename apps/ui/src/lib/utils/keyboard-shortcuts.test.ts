import { afterEach, describe, expect, it, vi } from 'vitest';
import { initKeyboardShortcuts } from './keyboard-shortcuts';

type Listener = (event: unknown) => void;

/** The window's keydown listener, as the app shell registers it, with a key press to give it. */
function shortcuts(handlers: Record<string, () => void>): { press: (key: string, more?: { shiftKey?: boolean; inField?: boolean }) => { prevented: boolean }; stop: () => void } {
    let listener: Listener = () => undefined;
    vi.stubGlobal('window', {
        addEventListener: (_type: string, added: Listener) => { listener = added; },
        removeEventListener: () => undefined,
        setTimeout: () => 0
    });
    vi.stubGlobal('document', { querySelector: () => null });
    const stop = initKeyboardShortcuts(handlers);
    return {
        stop,
        press: (key, more = {}) => {
            const event = { key, shiftKey: more.shiftKey ?? false, defaultPrevented: false, target: { matches: () => more.inField ?? false }, preventDefault() { event.defaultPrevented = true; } };
            listener(event);
            return { prevented: event.defaultPrevented };
        }
    };
}

describe('app keyboard shortcuts', () => {
    afterEach(() => vi.unstubAllGlobals());

    it('opens the shortcuts panel on "?", however the keyboard types it', () => {
        const open = vi.fn();
        const { press, stop } = shortcuts({ '?': open });
        expect(press('?', { shiftKey: true }).prevented).toBe(true);
        expect(press('?').prevented).toBe(true);
        expect(open).toHaveBeenCalledTimes(2);
        stop();
    });

    it('leaves "/" alone where the keyboard types it with Shift, so a page\'s search can take it', () => {
        // German, Spanish, Italian, Portuguese and French keyboards type "/" with Shift.
        const open = vi.fn();
        const { press, stop } = shortcuts({ '?': open });
        expect(press('/', { shiftKey: true }).prevented).toBe(false);
        expect(press('/').prevented).toBe(false);
        expect(open).not.toHaveBeenCalled();
        stop();
    });

    it('ignores keys typed into a field', () => {
        const open = vi.fn();
        const { press, stop } = shortcuts({ '?': open });
        expect(press('?', { inField: true }).prevented).toBe(false);
        expect(open).not.toHaveBeenCalled();
        stop();
    });
});
