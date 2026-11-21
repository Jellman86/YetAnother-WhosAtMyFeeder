import { describe, expect, it } from 'vitest';
import { savedNotifyMode, savedTrustedProxyHosts } from './notification-mode';

describe('the saved notification mode', () => {
    it('uses the saved mode when there is one', () => {
        expect(savedNotifyMode({ notifications_mode: 'final' })).toBe('final');
    });

    it('reads an older copy from its switches with the same defaults the form loads', () => {
        expect(savedNotifyMode({})).toBe('standard');
        expect(savedNotifyMode({ notifications_notify_on_insert: false })).toBe('silent');
        expect(savedNotifyMode({ notifications_notify_on_update: true })).toBe('realtime');
        expect(savedNotifyMode({ notifications_delay_until_video: true })).toBe('final');
    });
});

describe('saved trusted proxies', () => {
    it('treats none saved and a lone wildcard alike, as any proxy', () => {
        expect(savedTrustedProxyHosts([])).toEqual(['*']);
        expect(savedTrustedProxyHosts(undefined)).toEqual(['*']);
        expect(savedTrustedProxyHosts(['*'])).toEqual(['*']);
        expect(savedTrustedProxyHosts(['nginx-rp'])).toEqual(['nginx-rp']);
    });
});
