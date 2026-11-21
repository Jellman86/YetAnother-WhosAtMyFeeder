import { describe, expect, it, vi } from 'vitest';
import { isTestedSubsystem, sessionTests } from './session-tests.svelte';
import storeSource from './session-tests.svelte.ts?raw';

describe('the tests run during this visit', () => {
    it('keeps the latest result of each part, with when it ran and what was tested', () => {
        sessionTests.record('frigate', true, undefined, 1000);
        sessionTests.record('notifications', false, 'Discord', 2000);
        sessionTests.record('frigate', false, undefined, 3000);
        expect(sessionTests.results.frigate).toEqual({ passed: false, at: 3000, subject: undefined, draft: '' });
        expect(sessionTests.results.notifications).toEqual({ passed: false, at: 2000, subject: 'Discord', draft: '' });
        expect(sessionTests.results.mqtt).toBeUndefined();
    });

    it('offers a section\'s test only while the section offers it', () => {
        const run = vi.fn();
        const withdraw = sessionTests.provide(['frigate', 'mqtt'], run);
        expect(sessionTests.runners.frigate).toBe(run);
        expect(sessionTests.runners.mqtt).toBe(run);
        withdraw();
        expect(sessionTests.runners.frigate).toBeUndefined();
        expect(sessionTests.runners.mqtt).toBeUndefined();
    });

    it('withdraws only its own test when a newer one took the part', () => {
        const older = vi.fn();
        const newer = vi.fn();
        const withdrawOlder = sessionTests.provide(['audio'], older);
        const withdrawNewer = sessionTests.provide(['audio'], newer);
        withdrawOlder();
        expect(sessionTests.runners.audio).toBe(newer);
        withdrawNewer();
        expect(sessionTests.runners.audio).toBeUndefined();
    });

    it('reads its runners untracked, so a section may offer its test from inside an effect', () => {
        // Vitest runs Svelte's server build, where effects never run, so the loop itself is caught in
        // the browser (settings-status-help.spec.ts fails on any page error, with BirdNET-Go's runner
        // offered from its effect). Here: both reads of the runners stay outside any tracking.
        const provide = storeSource.slice(storeSource.indexOf('provide(keys'), storeSource.indexOf('export const sessionTests'));
        expect(provide.match(/untrack\(\(\) => this\.runners\)/g)).toHaveLength(2);
        expect(provide).not.toMatch(/\{ \.\.\.this\.runners \}/);
    });

    it('shows a result only while the values it ran with stand, and says when they were not saved', () => {
        let draft = 'edited-url';
        const untrackDraft = sessionTests.trackDraft(() => draft);
        sessionTests.record('mqtt', true, undefined, 5000);
        expect(sessionTests.shown('mqtt')).toEqual({ passed: true, at: 5000, subject: undefined, unsaved: true });
        // Saved, or discarded, or edited again: the result no longer describes the page.
        draft = '';
        expect(sessionTests.shown('mqtt')).toBeNull();
        sessionTests.record('mqtt', false, undefined, 6000);
        expect(sessionTests.shown('mqtt')).toEqual({ passed: false, at: 6000, subject: undefined, unsaved: false });
        draft = 'another-edit';
        expect(sessionTests.shown('mqtt')).toBeNull();
        untrackDraft();
    });

    it('has tests for the connections and alerts only', () => {
        expect(['frigate', 'mqtt', 'audio', 'notifications'].every((key) => isTestedSubsystem(key as never))).toBe(true);
        expect(['classifier', 'finder', 'storage'].some((key) => isTestedSubsystem(key as never))).toBe(false);
    });
});
