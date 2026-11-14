export type NotifyMode = 'silent' | 'final' | 'standard' | 'realtime' | 'custom';

interface StoredNotificationTiming {
    notifications_mode?: string | null;
    notifications_notify_on_insert?: boolean | null;
    notifications_notify_on_update?: boolean | null;
    notifications_delay_until_video?: boolean | null;
}

/**
 * The notification mode the saved settings mean. A copy saved before modes existed is read from
 * its switches, with the same defaults the form loads them with, so loading and the unsaved check
 * can never disagree about an untouched form.
 */
export function savedNotifyMode(stored: StoredNotificationTiming): NotifyMode {
    const mode = stored.notifications_mode;
    if (mode === 'silent' || mode === 'final' || mode === 'standard' || mode === 'realtime' || mode === 'custom') return mode;
    const onInsert = stored.notifications_notify_on_insert ?? true;
    const onUpdate = stored.notifications_notify_on_update ?? false;
    if (!onInsert && !onUpdate) return 'silent';
    if (stored.notifications_delay_until_video ?? false) return 'final';
    if (onInsert && onUpdate) return 'realtime';
    return 'standard';
}

/** Trusted proxies as the form edits them: none saved, or only `*`, both mean any proxy. */
export function savedTrustedProxyHosts(stored: readonly string[] | null | undefined): string[] {
    const hosts = stored ?? [];
    return hosts.length === 0 || (hosts.length === 1 && hosts[0] === '*') ? ['*'] : [...hosts];
}
