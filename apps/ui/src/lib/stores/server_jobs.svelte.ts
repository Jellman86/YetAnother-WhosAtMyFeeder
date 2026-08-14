import { fetchJobsSnapshot, type JobsSnapshot, type ServerJob } from '../api/jobs';
import type { QueueTelemetryByKind } from '../jobs/pipeline';
import { authStore } from './auth.svelte';
import type { JobProgressItem } from './job_progress.svelte';

const ACTIVE_REFRESH_MS = 5_000;
const IDLE_REFRESH_MS = 30_000;

function parseTimestamp(value: string | null | undefined, fallback: number): number {
    if (!value) return fallback;
    const parsed = Date.parse(value);
    return Number.isFinite(parsed) ? parsed : fallback;
}

function titleForJob(job: ServerJob): string {
    return job.event_id ?? job.kind.replace(/_/g, ' ');
}

function toProgressItem(
    job: ServerJob,
    capturedAt: number,
    previous?: JobProgressItem
): JobProgressItem {
    const reportedStartedAt = parseTimestamp(job.created_at, capturedAt);
    const startedAt = previous ? Math.min(previous.startedAt, reportedStartedAt) : reportedStartedAt;
    const reportedUpdatedAt = parseTimestamp(job.updated_at, startedAt);
    const updatedAt = previous ? Math.max(previous.updatedAt, reportedUpdatedAt) : reportedUpdatedAt;
    const terminal = job.status === 'completed' || job.status === 'failed';
    const reportedCurrent = Math.max(0, Math.floor(job.current ?? 0));
    const reportedTotal = Math.max(0, Math.floor(job.total ?? 0));
    const current = previous ? Math.max(previous.current, reportedCurrent) : reportedCurrent;
    const total = previous ? Math.max(previous.total, reportedTotal, current) : Math.max(reportedTotal, current);
    return {
        id: job.id,
        kind: job.kind,
        title: titleForJob(job),
        message: job.phase,
        route: job.route ?? undefined,
        status: job.status === 'failed'
            ? 'failed'
            : terminal
                ? 'completed'
                : job.status === 'stale'
                    ? 'stale'
                    : job.status === 'queued' || job.status === 'retrying'
                        ? 'queued'
                        : 'running',
        current,
        total,
        startedAt,
        updatedAt,
        finishedAt: terminal ? parseTimestamp(job.finished_at, updatedAt) : undefined,
        source: 'system',
        phase: job.phase,
        unit: job.unit,
        visibility: job.visibility
    };
}

function correlationEventId(job: JobProgressItem): string | null {
    if (job.id.startsWith('reclassify:') && !job.id.startsWith('reclassify:progress')) {
        return job.id.slice('reclassify:'.length) || null;
    }
    if (job.id.startsWith('video:')) return job.id.slice('video:'.length) || null;
    return null;
}

/** Stable across the browser's reclassify id and the server's video id for one event. */
export function stableJobIdentity(job: JobProgressItem): string {
    const eventId = correlationEventId(job);
    return eventId ? `event:${eventId}` : `job:${job.id}`;
}

export class ServerJobsStore {
    snapshot = $state<JobsSnapshot | null>(null);
    loading = $state(false);
    error = $state<string | null>(null);
    private retainCount = 0;
    private timer: ReturnType<typeof setTimeout> | null = null;
    private request: Promise<void> | null = null;
    private materializedSnapshot: JobsSnapshot | null = null;
    private materializedActive: JobProgressItem[] = [];
    private materializedHistory: JobProgressItem[] = [];
    private previousById = new Map<string, JobProgressItem>();

    private materializeSnapshot(): void {
        const snapshot = this.snapshot;
        if (snapshot === this.materializedSnapshot) return;
        this.materializedSnapshot = snapshot;
        if (!snapshot) {
            this.materializedActive = [];
            this.materializedHistory = [];
            this.previousById.clear();
            return;
        }

        const capturedAt = parseTimestamp(snapshot.captured_at, Date.now());
        const nextById = new Map<string, JobProgressItem>();
        for (const job of snapshot.items) {
            const item = toProgressItem(job, capturedAt, this.previousById.get(job.id));
            nextById.set(item.id, item);
        }
        this.previousById = nextById;
        const items = [...nextById.values()];
        this.materializedActive = items.filter((job) => job.status !== 'completed' && job.status !== 'failed');
        this.materializedHistory = items.filter((job) => job.status === 'completed' || job.status === 'failed');
    }

    get activeJobs(): JobProgressItem[] {
        this.materializeSnapshot();
        return this.materializedActive;
    }

    get historyJobs(): JobProgressItem[] {
        this.materializeSnapshot();
        return this.materializedHistory;
    }

    get queueByKind(): QueueTelemetryByKind {
        const capturedAt = parseTimestamp(this.snapshot?.captured_at, Date.now());
        return Object.fromEntries((this.snapshot?.lanes ?? []).map((lane) => [
            lane.kind,
            {
                queued: Math.max(0, Math.floor(lane.queued ?? 0)),
                running: Math.max(0, Math.floor(lane.running ?? 0)),
                queueDepthKnown: true,
                updatedAt: capturedAt,
                maxConcurrentConfigured: lane.max_concurrent_configured ?? undefined,
                maxConcurrentEffective: lane.max_concurrent_effective ?? undefined,
                throttledForLivePressure: lane.blocker === 'waiting_for_live_detections'
            }
        ]));
    }

    mergeActive(localJobs: JobProgressItem[], prominentOnly = false): JobProgressItem[] {
        const serverJobs = this.activeJobs.filter((job) => !prominentOnly || job.visibility === 'prominent');
        const localByEventId = new Map(
            localJobs
                .map((job) => [correlationEventId(job), job] as const)
                .filter((entry): entry is [string, JobProgressItem] => Boolean(entry[0]))
        );
        const reconciledServerJobs = serverJobs.map((serverJob) => {
            const eventId = correlationEventId(serverJob);
            const localJob = eventId ? localByEventId.get(eventId) : undefined;
            if (!localJob) return serverJob;
            const current = Math.max(serverJob.current, localJob.current);
            const total = Math.max(serverJob.total, localJob.total, current);
            return {
                ...serverJob,
                current,
                total,
                startedAt: Math.min(serverJob.startedAt, localJob.startedAt),
                updatedAt: Math.max(serverJob.updatedAt, localJob.updatedAt),
                ratePerMinute: localJob.ratePerMinute ?? serverJob.ratePerMinute,
                etaSeconds: localJob.etaSeconds ?? serverJob.etaSeconds
            };
        });
        const serverEventIds = new Set(reconciledServerJobs.map(correlationEventId).filter((id): id is string => Boolean(id)));
        const local = localJobs.filter((job) => {
            const eventId = correlationEventId(job);
            return !eventId || !serverEventIds.has(eventId);
        });
        return [...reconciledServerJobs, ...local];
    }

    mergeHistory(localJobs: JobProgressItem[]): JobProgressItem[] {
        const byId = new Map(localJobs.map((job) => [job.id, job]));
        for (const job of this.historyJobs) byId.set(job.id, job);
        return [...byId.values()];
    }

    async refresh(): Promise<void> {
        if (!authStore.showSettings) {
            this.snapshot = null;
            this.error = null;
            this.loading = false;
            this.scheduleNext();
            return;
        }
        if (this.request) return this.request;
        this.loading = this.snapshot === null;
        this.request = (async () => {
            try {
                this.snapshot = await fetchJobsSnapshot(true);
                this.error = null;
            } catch (error) {
                this.error = error instanceof Error ? error.message : 'Jobs status is temporarily unavailable.';
            } finally {
                this.loading = false;
                this.request = null;
                this.scheduleNext();
            }
        })();
        return this.request;
    }

    retain(): () => void {
        this.retainCount += 1;
        if (this.retainCount === 1) void this.refresh();
        return () => {
            this.retainCount = Math.max(0, this.retainCount - 1);
            if (this.retainCount === 0 && this.timer) {
                clearTimeout(this.timer);
                this.timer = null;
            }
        };
    }

    private scheduleNext(): void {
        if (this.retainCount <= 0) return;
        if (this.timer) clearTimeout(this.timer);
        const delay = this.activeJobs.length > 0 ? ACTIVE_REFRESH_MS : IDLE_REFRESH_MS;
        this.timer = setTimeout(() => void this.refresh(), delay);
    }
}

export const serverJobsStore = new ServerJobsStore();
