import { describe, expect, it } from 'vitest';
import {
    canonicalizeNotificationRouteForAccess,
    getCanonicalNotificationRoute,
    isNotificationRoute
} from './notifications_route';

describe('notifications_route', () => {
    it('lands every former jobs link on the timeline that replaced it', () => {
        expect(getCanonicalNotificationRoute('/jobs')).toBe('/notifications');
        expect(getCanonicalNotificationRoute('/jobs/anything')).toBe('/notifications');
        expect(getCanonicalNotificationRoute('/notifications/jobs')).toBe('/notifications');
        expect(getCanonicalNotificationRoute('/notifications/errors')).toBe('/settings/health');
        expect(getCanonicalNotificationRoute('/notifications')).toBe('/notifications');
        expect(getCanonicalNotificationRoute('/settings')).toBeNull();
    });

    it('sends a guest to the timeline rather than an owner-only surface', () => {
        expect(canonicalizeNotificationRouteForAccess('/notifications', false)).toBe('/notifications');
        expect(canonicalizeNotificationRouteForAccess('/jobs', false)).toBe('/notifications');
        expect(canonicalizeNotificationRouteForAccess('/notifications/jobs', false)).toBe('/notifications');
        expect(canonicalizeNotificationRouteForAccess('/notifications/errors', false)).toBe('/notifications');
        expect(canonicalizeNotificationRouteForAccess('/notifications/jobs', true)).toBe('/notifications');
        expect(canonicalizeNotificationRouteForAccess('/notifications/errors', true)).toBe('/settings/health');
        expect(canonicalizeNotificationRouteForAccess('/events', false)).toBe('/events');
    });

    it('identifies all notification surface routes', () => {
        expect(isNotificationRoute('/notifications')).toBe(true);
        expect(isNotificationRoute('/notifications/jobs')).toBe(true);
        expect(isNotificationRoute('/notifications/errors')).toBe(true);
        expect(isNotificationRoute('/settings/health')).toBe(false);
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
