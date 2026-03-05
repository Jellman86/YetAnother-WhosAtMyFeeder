export type NotificationsTab = 'notifications' | 'jobs';

function matchesPathSegment(path: string, segment: string): boolean {
    return path === segment || path.startsWith(`${segment}/`);
}

export function getNotificationsTabPath(tab: NotificationsTab): string {
    return tab === 'jobs' ? '/notifications/jobs' : '/notifications';
}

export function getNotificationsTabFromPath(path: string): NotificationsTab {
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
    if (matchesPathSegment(path, '/notifications')) {
        return '/notifications';
    }
    return null;
}

export function isNotificationRoute(path: string): boolean {
    return matchesPathSegment(path, '/notifications') || matchesPathSegment(path, '/jobs');
}
