import { describe, expect, it } from 'vitest';
import {
    getNotificationsTabFromPath,
    getNotificationsTabPath,
    getCanonicalNotificationRoute,
    isNotificationRoute
} from './notifications_route';

describe('notifications_route', () => {
    it('routes jobs tab to nested notifications path', () => {
        expect(getNotificationsTabPath('notifications')).toBe('/notifications');
        expect(getNotificationsTabPath('jobs')).toBe('/notifications/jobs');
        expect(getNotificationsTabPath('errors')).toBe('/notifications/errors');
    });

    it('parses notification tab from route path', () => {
        expect(getNotificationsTabFromPath('/notifications')).toBe('notifications');
        expect(getNotificationsTabFromPath('/notifications/jobs')).toBe('jobs');
        expect(getNotificationsTabFromPath('/notifications/errors')).toBe('errors');
        expect(getNotificationsTabFromPath('/jobs')).toBe('jobs');
        expect(getNotificationsTabFromPath('/notifications/other')).toBe('notifications');
    });

    it('canonicalizes legacy jobs route to notifications jobs tab route', () => {
        expect(getCanonicalNotificationRoute('/jobs')).toBe('/notifications/jobs');
        expect(getCanonicalNotificationRoute('/jobs/anything')).toBe('/notifications/jobs');
        expect(getCanonicalNotificationRoute('/notifications/jobs')).toBe('/notifications/jobs');
        expect(getCanonicalNotificationRoute('/notifications/errors')).toBe('/notifications/errors');
        expect(getCanonicalNotificationRoute('/notifications')).toBe('/notifications');
        expect(getCanonicalNotificationRoute('/settings')).toBeNull();
    });

    it('identifies all notification surface routes', () => {
        expect(isNotificationRoute('/notifications')).toBe(true);
        expect(isNotificationRoute('/notifications/jobs')).toBe(true);
        expect(isNotificationRoute('/notifications/errors')).toBe(true);
        expect(isNotificationRoute('/jobs')).toBe(true);
        expect(isNotificationRoute('/events')).toBe(false);
        expect(isNotificationRoute('/notifications-old')).toBe(false);
        expect(isNotificationRoute('/jobsmith')).toBe(false);
    });

    it('enforces route segment boundaries for canonicalization', () => {
        expect(getCanonicalNotificationRoute('/notifications-old')).toBeNull();
        expect(getCanonicalNotificationRoute('/jobsmith')).toBeNull();
    });
});
