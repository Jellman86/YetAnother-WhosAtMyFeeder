export type NotificationsTab = 'notifications' | 'jobs' | 'errors';

function matchesPathSegment(path: string, segment: string): boolean {
    return path === segment || path.startsWith(`${segment}/`);
}

export function getNotificationsTabPath(tab: NotificationsTab): string {
    if (tab === 'jobs') return '/notifications/jobs';
    if (tab === 'errors') return '/notifications/errors';
    return '/notifications';
}

export function isOwnerOnlyNotificationsTab(tab: NotificationsTab): boolean {
    return tab === 'jobs' || tab === 'errors';
}

export function getNotificationsTabPathForAccess(tab: NotificationsTab, canAccessOwnerTabs: boolean): string {
    if (!canAccessOwnerTabs && isOwnerOnlyNotificationsTab(tab)) {
        return '/notifications';
    }
    return getNotificationsTabPath(tab);
}

export function getNotificationsTabFromPath(path: string): NotificationsTab {
    if (matchesPathSegment(path, '/notifications/errors')) {
        return 'errors';
    }
    if (matchesPathSegment(path, '/jobs') || matchesPathSegment(path, '/notifications/jobs')) {
        return 'jobs';
    }
    return 'notifications';
}

export function getCanonicalNotificationRoute(path: string): string | null {
    if (matchesPathSegment(path, '/jobs')) {
        return '/notifications/jobs';
    }
    if (matchesPathSegment(path, '/notifications/jobs')) {
        return '/notifications/jobs';
    }
    if (matchesPathSegment(path, '/notifications/errors')) {
        return '/notifications/errors';
    }
    if (matchesPathSegment(path, '/notifications')) {
        return '/notifications';
    }
    return null;
}

export function canonicalizeNotificationRouteForAccess(path: string, canAccessOwnerTabs: boolean): string {
    const canonical = getCanonicalNotificationRoute(path) ?? path;
    if (!canAccessOwnerTabs && matchesPathSegment(canonical, '/notifications/jobs')) {
        return '/notifications';
    }
    if (!canAccessOwnerTabs && matchesPathSegment(canonical, '/notifications/errors')) {
        return '/notifications';
    }
    return canonical;
}

export function isNotificationRoute(path: string): boolean {
    return matchesPathSegment(path, '/notifications') || matchesPathSegment(path, '/jobs');
}
