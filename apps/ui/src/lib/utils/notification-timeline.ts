import type { NotificationItem } from '../stores/notification_center.svelte';
import type { JobProgressItem } from '../stores/job_progress.svelte';

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
    if (item.meta?.status === 'failed') return true;
    // Retain compatibility with persisted notifications written before job status was attached.
    const kind = item.meta?.kind;
    return kind === 'error' || kind === 'failed' || kind === 'failure';
}

function notificationJobId(item: NotificationItem): string {
    if (item.type === 'process' && item.id.startsWith('reclassify:progress:')) {
        return `reclassify:${item.id.slice('reclassify:progress:'.length)}`;
    }
    return item.id;
}

function jobIdentity(job: JobProgressItem): string {
    if (job.id.startsWith('video:')) return `event:${job.id.slice('video:'.length)}`;
    if (job.id.startsWith('reclassify:') && !job.id.startsWith('reclassify:progress:')) {
        return `event:${job.id.slice('reclassify:'.length)}`;
    }
    return `job:${job.id}`;
}

function jobTimestamp(job: JobProgressItem): number {
    // A terminal transition is a real timeline event, so it belongs at its completion time.
    // Active updatedAt values are only progress heartbeats; retaining admission time there
    // prevents rows changing position on every tick.
    if (job.status === 'completed' || job.status === 'failed') {
        return job.finishedAt || job.updatedAt || job.startedAt;
    }
    return job.startedAt || job.finishedAt || job.updatedAt;
}

function jobAsNotification(job: JobProgressItem): NotificationItem {
    return {
        id: job.id,
        type: 'process',
        title: job.title,
        message: job.message,
        timestamp: jobTimestamp(job),
        // Job history has no read state. Do not inflate the alert badge with synthetic unread rows.
        read: true,
        meta: {
            source: job.source,
            route: job.route,
            kind: job.kind,
            status: job.status,
            current: job.current,
            total: job.total
        }
    };
}

/**
 * Build the single timeline from both stores. Job state is authoritative for progress and terminal
 * status, while a matching notification keeps its user-facing title, message and read state.
 */
export function buildTimelineItems(
    notifications: readonly NotificationItem[],
    jobs: readonly JobProgressItem[]
): NotificationItem[] {
    // The server uses video:<event> while the browser uses reclassify:<event>. Later entries are
    // authoritative, matching ServerJobsStore's local-then-server merge order.
    const jobsByIdentity = new Map<string, JobProgressItem>();
    for (const job of jobs) jobsByIdentity.set(jobIdentity(job), job);
    const jobsById = new Map<string, JobProgressItem>();
    for (const job of jobsByIdentity.values()) {
        jobsById.set(job.id, job);
        const identity = jobIdentity(job);
        if (identity.startsWith('event:')) {
            const eventId = identity.slice('event:'.length);
            jobsById.set(`video:${eventId}`, job);
            jobsById.set(`reclassify:${eventId}`, job);
        }
    }
    const consumedJobs = new Set<string>();
    const items = notifications.map((notification) => {
        const jobId = notificationJobId(notification);
        const job = jobsById.get(jobId);
        if (!job) return notification;
        consumedJobs.add(jobIdentity(job));
        const jobItem = jobAsNotification(job);
        return {
            ...jobItem,
            ...notification,
            id: notification.id,
            timestamp: jobItem.timestamp,
            meta: {
                ...notification.meta,
                ...jobItem.meta,
                route: job.route ?? notification.meta?.route,
                open_label: notification.meta?.open_label
            }
        };
    });

    for (const [identity, job] of jobsByIdentity) {
        if (!consumedJobs.has(identity)) items.push(jobAsNotification(job));
    }

    return items.sort((left, right) => {
        const timestampDiff = right.timestamp - left.timestamp;
        return timestampDiff !== 0 ? timestampDiff : right.id.localeCompare(left.id);
    });
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
    if (item.meta?.status === 'stale') return 'attention';
    if (item.meta?.status === 'completed') return 'done';
    if (item.meta?.status === 'queued' || item.meta?.status === 'running') return 'running';
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
    if (item.meta?.status) return 'jobs';
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
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    if (timestamp >= yesterday.getTime()) return 'yesterday';
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
