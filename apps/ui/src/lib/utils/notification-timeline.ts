import type { NotificationItem } from '../stores/notification_center.svelte';

/**
 * One chronological river replaces the notification/jobs tab split. A job that failed is the most
 * urgent thing this app can say, and filing it behind a tab put it one click from the place people
 * look. These are the rules that let every kind of event share one list.
 */

export type NotificationFilter = 'all' | 'birds' | 'updates' | 'jobs' | 'errors';

/** Amber is reserved for "this needs a person" (layout-patterns 1.3). Nothing else may claim it. */
export type NotificationTone = 'attention' | 'done' | 'running' | 'info';

export type TimelineGroupKey = 'now' | 'earlier' | 'yesterday' | 'older';

export interface TimelineGroup {
    key: TimelineGroupKey;
    items: NotificationItem[];
}

export const NOW_WINDOW_MS = 30 * 60 * 1000;

/** Owner-only filters are hidden outright rather than shown returning zero. */
export const OWNER_ONLY_FILTERS: readonly NotificationFilter[] = ['jobs', 'errors'];

export function isOwnerOnlyFilter(filter: NotificationFilter): boolean {
    return OWNER_ONLY_FILTERS.includes(filter);
}

function isFailure(item: NotificationItem): boolean {
    // The store carries no severity, so a failure is recognised by the job kind it reports.
    const kind = item.meta?.kind;
    return kind === 'error' || kind === 'failed' || kind === 'failure';
}

export function progressOf(item: NotificationItem): { percent: number; current: number; total: number } | null {
    const meta = item.meta ?? {};
    const total = Number(meta.total ?? 0);
    const current = Number(meta.current ?? meta.processed ?? 0);
    if (!Number.isFinite(total) || total <= 0) return null;
    if (!Number.isFinite(current) || current < 0) return null;
    const percent = Math.min(100, Math.max(0, Math.round((current / total) * 100)));
    return { percent, current, total };
}

export function toneOf(item: NotificationItem): NotificationTone {
    if (isFailure(item)) return 'attention';
    if (item.type === 'process') {
        const progress = progressOf(item);
        // A finished process is done; one still counting is merely running, and neither needs amber.
        return progress && progress.percent < 100 ? 'running' : 'done';
    }
    if (item.type === 'update') return 'info';
    return 'info';
}

export function filterOf(item: NotificationItem): NotificationFilter {
    if (isFailure(item)) return 'errors';
    if (item.type === 'detection') return 'birds';
    if (item.type === 'update') return 'updates';
    return 'jobs';
}

export function matchesFilter(item: NotificationItem, filter: NotificationFilter): boolean {
    if (filter === 'all') return true;
    return filterOf(item) === filter;
}

export function filterNotifications(
    items: readonly NotificationItem[],
    filter: NotificationFilter
): NotificationItem[] {
    return items.filter((item) => matchesFilter(item, filter));
}

/** Counts every bucket in one pass so the chips can state their size before being applied. */
export function countByFilter(items: readonly NotificationItem[]): Record<NotificationFilter, number> {
    const counts: Record<NotificationFilter, number> = {
        all: items.length,
        birds: 0,
        updates: 0,
        jobs: 0,
        errors: 0
    };
    for (const item of items) {
        counts[filterOf(item)] += 1;
    }
    return counts;
}

function startOfDay(at: number): number {
    const date = new Date(at);
    date.setHours(0, 0, 0, 0);
    return date.getTime();
}

export function groupKeyFor(timestamp: number, now: number): TimelineGroupKey {
    if (now - timestamp <= NOW_WINDOW_MS) return 'now';
    const today = startOfDay(now);
    if (timestamp >= today) return 'earlier';
    if (timestamp >= today - 24 * 60 * 60 * 1000) return 'yesterday';
    return 'older';
}

const GROUP_ORDER: readonly TimelineGroupKey[] = ['now', 'earlier', 'yesterday', 'older'];

/**
 * Newest first within each group, and empty groups are dropped rather than rendered as headings
 * with nothing under them.
 */
export function groupNotifications(
    items: readonly NotificationItem[],
    now: number = Date.now()
): TimelineGroup[] {
    const buckets = new Map<TimelineGroupKey, NotificationItem[]>();
    for (const item of items) {
        const key = groupKeyFor(item.timestamp, now);
        const bucket = buckets.get(key);
        if (bucket) bucket.push(item);
        else buckets.set(key, [item]);
    }
    const groups: TimelineGroup[] = [];
    for (const key of GROUP_ORDER) {
        const bucket = buckets.get(key);
        if (!bucket || bucket.length === 0) continue;
        groups.push({ key, items: [...bucket].sort((a, b) => b.timestamp - a.timestamp) });
    }
    return groups;
}
