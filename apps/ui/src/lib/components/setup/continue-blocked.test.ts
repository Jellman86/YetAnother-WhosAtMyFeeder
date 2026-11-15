import { describe, expect, it } from 'vitest';

import { loadBlockedReason } from './continue-blocked';

const translate = (_key: string, options: { default: string }): string => options.default;

describe('why a setup step cannot continue', () => {
    it('says the settings are still loading, or could not be loaded', () => {
        expect(loadBlockedReason('loading', translate)).toContain('once the current settings have loaded');
        expect(loadBlockedReason('error', translate)).toContain('could not be loaded');
    });

    it('gives no reason once the settings are ready, leaving the step to give its own', () => {
        expect(loadBlockedReason('ready', translate)).toBe('');
    });
});
