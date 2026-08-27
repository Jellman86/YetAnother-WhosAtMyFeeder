import { beforeEach, describe, expect, it, vi } from 'vitest';
import { explorerViewStore } from './explorer_view.svelte';

/** The suite runs without a DOM, so stand up the storage the store reaches for. */
function stubStorage(): Map<string, string> {
    const backing = new Map<string, string>();
    Object.defineProperty(globalThis, 'localStorage', {
        configurable: true,
        value: {
            getItem: (key: string) => backing.get(key) ?? null,
            setItem: (key: string, value: string) => {
                backing.set(key, String(value));
            },
            removeItem: (key: string) => {
                backing.delete(key);
            },
            clear: () => backing.clear()
        }
    });
    return backing;
}

/**
 * Settings → Appearance sets the install default; the Explorer's own toggle
 * sets what this browser shows. The two are not rivals: the device answer wins
 * where there is one, because the list exists for a phone and the cards suit a
 * desktop, and one shared answer would be wrong on whichever device lost.
 */
describe('the Explorer view preference', () => {
    beforeEach(() => {
        stubStorage();
        explorerViewStore.clear();
    });

    it('follows the install default until this device says otherwise', () => {
        expect(explorerViewStore.hasOverride).toBe(false);
        expect(explorerViewStore.resolve('list')).toBe('list');
        expect(explorerViewStore.resolve('cards')).toBe('cards');
    });

    it('falls back to cards when the install has said nothing', () => {
        expect(explorerViewStore.resolve(undefined)).toBe('cards');
        expect(explorerViewStore.resolve(null)).toBe('cards');
    });

    it('lets this device disagree with the install default', () => {
        explorerViewStore.set('list');
        expect(explorerViewStore.resolve('cards')).toBe('list');
        expect(explorerViewStore.hasOverride).toBe(true);
    });

    it('goes back to following the install default when cleared', () => {
        explorerViewStore.set('list');
        explorerViewStore.clear();
        expect(explorerViewStore.hasOverride).toBe(false);
        expect(explorerViewStore.resolve('cards')).toBe('cards');
    });

    it('remembers the choice for next time', () => {
        explorerViewStore.set('list');
        expect(localStorage.getItem('yawamf:explorer-view')).toBe('list');
    });

    it('still works when storage is unavailable', () => {
        // Private browsing throws on write. A view preference is not worth an
        // error dialog; it just does not outlive the session.
        const throwing = vi.fn(() => {
            throw new Error('QuotaExceededError');
        });
        Object.defineProperty(globalThis, 'localStorage', {
            configurable: true,
            value: { getItem: () => null, setItem: throwing, removeItem: throwing }
        });

        expect(() => explorerViewStore.set('list')).not.toThrow();
        expect(explorerViewStore.resolve('cards')).toBe('list');
        expect(throwing).toHaveBeenCalled();
    });

    it('ignores a stored value that is not a layout', () => {
        localStorage.setItem('yawamf:explorer-view', 'mosaic');
        explorerViewStore.clear();
        expect(explorerViewStore.resolve('cards')).toBe('cards');
    });
});
