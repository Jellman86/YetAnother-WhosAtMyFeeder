import { describe, expect, it } from 'vitest';
import {
    canonicalizeNotificationRouteForAccess,
    getNotificationsTabFromPath,
    getNotificationsTabPath,
    getNotificationsTabPathForAccess,
    getCanonicalNotificationRoute,
    isOwnerOnlyNotificationsTab,
    isNotificationRoute
} from './notifications_route';

describe('notifications_route', () => {
    it('routes jobs tab to nested notifications path', () => {
        expect(getNotificationsTabPath('notifications')).toBe('/notifications');
        expect(getNotificationsTabPath('jobs')).toBe('/notifications/jobs');
    });

    it('marks jobs tab as owner-only', () => {
        expect(isOwnerOnlyNotificationsTab('notifications')).toBe(false);
        expect(isOwnerOnlyNotificationsTab('jobs')).toBe(true);
    });

    it('resolves notification tab paths for guest vs owner access', () => {
        expect(getNotificationsTabPathForAccess('notifications', false)).toBe('/notifications');
        expect(getNotificationsTabPathForAccess('jobs', false)).toBe('/notifications');
        expect(getNotificationsTabPathForAccess('jobs', true)).toBe('/notifications/jobs');
    });

    it('parses notification tab from route path', () => {
        expect(getNotificationsTabFromPath('/notifications')).toBe('notifications');
        expect(getNotificationsTabFromPath('/notifications/jobs')).toBe('jobs');
        expect(getNotificationsTabFromPath('/notifications/errors')).toBe('notifications');
        expect(getNotificationsTabFromPath('/jobs')).toBe('jobs');
        expect(getNotificationsTabFromPath('/notifications/other')).toBe('notifications');
    });

    it('canonicalizes legacy jobs route to notifications jobs tab route', () => {
        expect(getCanonicalNotificationRoute('/jobs')).toBe('/notifications/jobs');
        expect(getCanonicalNotificationRoute('/jobs/anything')).toBe('/notifications/jobs');
        expect(getCanonicalNotificationRoute('/notifications/jobs')).toBe('/notifications/jobs');
        expect(getCanonicalNotificationRoute('/notifications/errors')).toBe('/settings/errors');
        expect(getCanonicalNotificationRoute('/notifications')).toBe('/notifications');
        expect(getCanonicalNotificationRoute('/settings')).toBeNull();
    });

    it('canonicalizes owner-only notification routes to the public tab for guests', () => {
        expect(canonicalizeNotificationRouteForAccess('/notifications', false)).toBe('/notifications');
        expect(canonicalizeNotificationRouteForAccess('/jobs', false)).toBe('/notifications');
        expect(canonicalizeNotificationRouteForAccess('/notifications/jobs', false)).toBe('/notifications');
        expect(canonicalizeNotificationRouteForAccess('/notifications/errors', false)).toBe('/notifications');
        expect(canonicalizeNotificationRouteForAccess('/notifications/jobs', true)).toBe('/notifications/jobs');
        expect(canonicalizeNotificationRouteForAccess('/notifications/errors', true)).toBe('/settings/errors');
        expect(canonicalizeNotificationRouteForAccess('/events', false)).toBe('/events');
    });

    it('identifies all notification surface routes', () => {
        expect(isNotificationRoute('/notifications')).toBe(true);
        expect(isNotificationRoute('/notifications/jobs')).toBe(true);
        expect(isNotificationRoute('/notifications/errors')).toBe(true);
        expect(isNotificationRoute('/settings/errors')).toBe(false);
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
