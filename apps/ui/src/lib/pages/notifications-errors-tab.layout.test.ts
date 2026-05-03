import { describe, expect, it } from 'vitest';
import notificationsSource from './Notifications.svelte?raw';

describe('notifications page tabs', () => {
    it('keeps error diagnostics out of the notifications tab strip', () => {
        expect(notificationsSource).not.toContain("activeTab === 'errors'");
        expect(notificationsSource).not.toContain("setTab('errors')");
        expect(notificationsSource).not.toContain("<Errors");
    });
});
