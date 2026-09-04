function matchesPathSegment(path: string, segment: string): boolean {
    return path === segment || path.startsWith(`${segment}/`);
}

export function getCanonicalNotificationRoute(path: string): string | null {
    // The jobs view was folded into the notifications timeline, which already carried every
    // job it listed. Its links stay valid and land on the surface that replaced it.
    if (matchesPathSegment(path, '/jobs')) {
        return '/notifications';
    }
    if (matchesPathSegment(path, '/notifications/errors')) {
        return '/settings/health';
    }
    if (matchesPathSegment(path, '/notifications')) {
        return '/notifications';
    }
    return null;
}

export function canonicalizeNotificationRouteForAccess(path: string, canAccessOwnerTabs: boolean): string {
    const canonical = getCanonicalNotificationRoute(path) ?? path;
    if (!canAccessOwnerTabs && matchesPathSegment(canonical, '/settings/health')) {
        return '/notifications';
    }
    return canonical;
}

export function isNotificationRoute(path: string): boolean {
    return matchesPathSegment(path, '/notifications') || matchesPathSegment(path, '/jobs');
}
