export type NotificationLinkTarget = 'yawamf' | 'frigate';

/** A representative event id so the preview reads like a real link. */
const PREVIEW_EVENT_ID = '1788874165.969381-ym7r9s';

const trimBase = (url: string): string => url.trim().replace(/\/+$/, '');

/** The link a notification would carry, mirroring the backend's choice of target; null means no link. */
export function notificationLinkPreview(
    target: NotificationLinkTarget,
    instanceUrl: string,
    frigateExternalUrl: string,
    eventId: string = PREVIEW_EVENT_ID
): string | null {
    if (target === 'frigate') {
        const base = trimBase(frigateExternalUrl);
        return base ? `${base}/explore?event_id=${encodeURIComponent(eventId)}` : null;
    }
    const base = trimBase(instanceUrl);
    return base ? `${base}/events?event=${encodeURIComponent(eventId)}` : null;
}
