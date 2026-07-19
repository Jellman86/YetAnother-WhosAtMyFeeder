import { describe, expect, it } from 'vitest';

import { shouldShowUpdateBanner, type UpdateStatus } from './system';

const status = (overrides: Partial<UpdateStatus>): UpdateStatus => ({
    current_version: '2.10.0',
    channel: 'stable',
    latest_version: '2.12.0',
    update_available: true,
    release_url: 'https://example/releases',
    checked_at: '2026-07-11T00:00:00Z',
    enabled: true,
    error: null,
    ...overrides
});

describe('shouldShowUpdateBanner', () => {
    it('shows when an update is available and not yet dismissed', () => {
        expect(shouldShowUpdateBanner(status({}), null)).toBe(true);
    });

    it('hides when the current latest version was already dismissed', () => {
        expect(shouldShowUpdateBanner(status({ latest_version: '2.12.0' }), '2.12.0')).toBe(false);
    });

    it('re-shows when a newer version supersedes a previously dismissed one', () => {
        expect(shouldShowUpdateBanner(status({ latest_version: '2.13.0' }), '2.12.0')).toBe(true);
    });

    it('hides when no update is available', () => {
        expect(shouldShowUpdateBanner(status({ update_available: false }), null)).toBe(false);
    });

    it('is safe with null status', () => {
        expect(shouldShowUpdateBanner(null, null)).toBe(false);
    });
});
