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

describe('sections holding a problem the owner must act on', () => {
    const ids = ['hardware', 'report'];
    const sections = (page: SettingsDisclosures) => ids.map((id) => new Disclosure(page, () => ({ id })));

    it('open when a problem appears, and stay open after it clears on a later poll', () => {
        const page = new SettingsDisclosures();
        const [hardware, report] = sections(page);
        page.attend(ids, null);
        expect([hardware.open, report.open]).toEqual([false, false]);
        page.attend(ids, 'fallback:intel_gpu');
        expect([hardware.open, report.open]).toEqual([true, true]);
        page.attend(ids, null);
        expect([hardware.open, report.open]).toEqual([true, true]);
    });

    it('stay closed when the owner closed them and the same problem polls again', () => {
        const page = new SettingsDisclosures();
        const [, report] = sections(page);
        page.attend(ids, 'fallback:intel_gpu');
        report.toggle();
        page.attend(ids, 'fallback:intel_gpu');
        page.attend(ids, null);
        page.attend(ids, 'fallback:intel_gpu');
        expect(report.open).toBe(false);
    });

    it('reopen for a new, different problem after one was dismissed', () => {
        const page = new SettingsDisclosures();
        const [, report] = sections(page);
        page.attend(ids, 'fallback:intel_gpu');
        report.toggle();
        page.attend(ids, 'compile:openvino');
        expect(report.open).toBe(true);
    });

    it('behave the same when the tab is left and its sections are shown again', () => {
        const page = new SettingsDisclosures();
        const [, report] = sections(page);
        page.attend(ids, 'fallback:intel_gpu');
        report.toggle();
        // The tab is left: its components go away, the page keeps the state, polling goes on.
        page.attend(ids, 'fallback:intel_gpu');
        const [hardwareAgain, reportAgain] = sections(page);
        expect([hardwareAgain.open, reportAgain.open]).toEqual([true, false]);
        page.attend(ids, 'circuit:video');
        expect(reportAgain.open).toBe(true);
    });
});
