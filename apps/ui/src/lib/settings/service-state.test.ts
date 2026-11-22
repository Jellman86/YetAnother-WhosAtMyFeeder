import { describe, expect, it } from 'vitest';
import { serviceState, serviceStateText, type ServiceTest } from './service-state';

const test = (passed: boolean, signature = 'a'): ServiceTest => ({ passed, message: 'The token was refused.', at: 1000, signature });

describe('what an integration says about itself', () => {
    it('says off before anything else', () => {
        expect(serviceState({ enabled: false, missing: 'an API key', signature: 'a', test: test(true) })).toEqual({ kind: 'off' });
    });

    it('names what is missing while it is on', () => {
        expect(serviceState({ enabled: true, missing: 'an API key', signature: 'a', test: null })).toEqual({ kind: 'not_set_up', missing: 'an API key' });
    });

    it('never claims a result that was not measured on this visit', () => {
        expect(serviceState({ enabled: true, missing: null, signature: 'a', test: null })).toEqual({ kind: 'not_tested' });
        expect(serviceState({ enabled: true, missing: null, signature: 'a' })).toEqual({ kind: 'no_test' });
    });

    it('states the last test while its values still stand', () => {
        expect(serviceState({ enabled: true, missing: null, signature: 'a', test: test(true) })).toEqual({ kind: 'passed', at: 1000 });
        expect(serviceState({ enabled: true, missing: null, signature: 'a', test: test(false) })).toEqual({ kind: 'failed', at: 1000, reason: 'The token was refused.' });
    });

    it('retires a test once a value it ran with is edited', () => {
        expect(serviceState({ enabled: true, missing: null, signature: 'b', test: test(true) })).toEqual({ kind: 'not_tested' });
    });

    it('words every state, a failure with its reason', () => {
        const translate = (_key: string, options?: { values?: Record<string, string>; default?: string }): string =>
            Object.entries(options?.values ?? {}).reduce((text, [name, value]) => text.replace(`{${name}}`, value), options?.default ?? '');
        const time = (): string => '10:32';
        expect(serviceStateText({ kind: 'off' }, translate, time)).toBe('Off.');
        expect(serviceStateText({ kind: 'not_set_up', missing: 'add the API key' }, translate, time)).toBe('On, but not set up: add the API key.');
        expect(serviceStateText({ kind: 'passed', at: 1 }, translate, time)).toBe('On. The test passed at 10:32.');
        expect(serviceStateText({ kind: 'failed', at: 1, reason: 'The token was refused.' }, translate, time)).toBe('On, but the test failed at 10:32: The token was refused.');
        expect(serviceStateText({ kind: 'not_tested' }, translate, time)).toContain('Not tested on this visit');
        expect(serviceStateText({ kind: 'no_test' }, translate, time)).toContain('no connection test');
    });
});
