import { describe, expect, it } from 'vitest';
import { Disclosure, SettingsDisclosures } from './disclosures.svelte';

describe('Settings disclosures', () => {
    it('follow their default until opened or closed, and the page remembers by id', () => {
        const page = new SettingsDisclosures();
        const first = new Disclosure(page, () => ({ id: 'a', openByDefault: true }));
        expect(first.open).toBe(true);
        first.toggle();
        // A section shown again later (the tab was left and reopened) reads what was remembered.
        expect(new Disclosure(page, () => ({ id: 'a', openByDefault: true })).open).toBe(false);
    });

    it('can be opened by the page, as for a refused field inside', () => {
        const page = new SettingsDisclosures();
        const outer = new Disclosure(page, () => ({ id: 'outer' }));
        const inner = new Disclosure(page, () => ({ id: 'inner' }));
        page.reveal(['outer', 'inner']);
        expect([outer.open, inner.open]).toEqual([true, true]);
    });

    it('holds its own state outside the Settings page', () => {
        const own = new Disclosure(undefined, () => ({ id: 'a' }));
        own.toggle();
        expect(own.open).toBe(true);
    });
});
