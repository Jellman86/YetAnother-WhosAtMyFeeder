import { describe, expect, it, vi } from 'vitest';
import { effectiveChoice, parseDeviceChoices } from './accessibility-device.svelte';
import deviceSource from './accessibility-device.svelte.ts?raw';
import appSource from '../../App.svelte?raw';
import indexHtml from '../../../index.html?raw';

describe('accessibility chosen on this device', () => {
    it('reads only the choices it knows, as true or false, and nothing from a broken entry', () => {
        expect(parseDeviceChoices(null)).toEqual({});
        expect(parseDeviceChoices('not json')).toEqual({});
        expect(parseDeviceChoices('[true]')).toEqual({});
        expect(parseDeviceChoices('{"highContrast":true,"dyslexiaFont":"yes","other":true,"reducedMotion":false}')).toEqual({ highContrast: true, reducedMotion: false });
    });

    it('reads its entry before the first paint, as the boot script in index.html does', () => {
        // The boot script cannot import this module, so the two are held to one key and one set of names.
        expect(deviceSource).toContain(`const STORAGE_KEY = 'accessibility_device'`);
        expect(indexHtml).toContain(`localStorage.getItem('accessibility_device')`);
        for (const [choice, className] of [['highContrast', 'high-contrast'], ['dyslexiaFont', 'font-dyslexic'], ['reducedMotion', 'reduced-motion']]) {
            expect(deviceSource).toContain(`'${choice}'`);
            expect(indexHtml).toContain(`device.${choice} === true`);
            expect(indexHtml).toContain(`'${className}'`);
            expect(appSource).toContain(`classList.toggle('${className}'`);
        }
    });

    it('puts this device\'s choice first, then a preview of the default being edited, then the saved default', () => {
        expect(effectiveChoice(undefined, null, false)).toBe(false);
        expect(effectiveChoice(true, null, false)).toBe(true);
        expect(effectiveChoice(false, null, true)).toBe(false);
        expect(effectiveChoice(undefined, true, false)).toBe(true);
        expect(effectiveChoice(false, true, true)).toBe(false);
    });
});

describe('the choices kept on this device', () => {
    it('keeps a choice across a reload and forgets it once set back to the default', async () => {
        const stored = new Map<string, string>();
        vi.stubGlobal('localStorage', {
            getItem: (key: string) => stored.get(key) ?? null,
            setItem: (key: string, value: string) => void stored.set(key, value),
            removeItem: (key: string) => void stored.delete(key)
        });
        vi.resetModules();
        const first = await import('./accessibility-device.svelte');
        first.accessibilityDevice.set('highContrast', true);
        expect(first.accessibilityDevice.get('highContrast')).toBe(true);

        vi.resetModules();
        const reloaded = await import('./accessibility-device.svelte');
        expect(reloaded.accessibilityDevice.get('highContrast')).toBe(true);
        expect(reloaded.accessibilityDevice.get('reducedMotion')).toBeUndefined();

        reloaded.accessibilityDevice.set('highContrast', null);
        expect(reloaded.accessibilityDevice.get('highContrast')).toBeUndefined();
        expect(stored.size).toBe(0);
        vi.unstubAllGlobals();
    });

    it('loads and takes a choice for this visit when the browser refuses all access to storage', async () => {
        // Chrome with site data blocked throws on reading localStorage itself, not only on its methods.
        const original = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
        Object.defineProperty(globalThis, 'localStorage', { configurable: true, get() { throw new Error('SecurityError'); } });
        try {
            vi.resetModules();
            const { accessibilityDevice } = await import('./accessibility-device.svelte');
            accessibilityDevice.set('highContrast', true);
            expect(accessibilityDevice.get('highContrast')).toBe(true);
        } finally {
            if (original) Object.defineProperty(globalThis, 'localStorage', original);
            else delete (globalThis as { localStorage?: unknown }).localStorage;
        }
    });

    it('still takes a choice for this visit when the browser refuses to store it', async () => {
        vi.stubGlobal('localStorage', {
            getItem: () => { throw new Error('denied'); },
            setItem: () => { throw new Error('denied'); },
            removeItem: () => { throw new Error('denied'); }
        });
        vi.resetModules();
        const { accessibilityDevice } = await import('./accessibility-device.svelte');
        accessibilityDevice.set('reducedMotion', true);
        expect(accessibilityDevice.get('reducedMotion')).toBe(true);
        vi.unstubAllGlobals();
    });
});
