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

function toProgressItem(job: ServerJob, capturedAt: number): JobProgressItem {
    const startedAt = parseTimestamp(job.created_at, capturedAt);
    const updatedAt = parseTimestamp(job.updated_at, startedAt);
    const terminal = job.status === 'completed' || job.status === 'failed';
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
        current: Math.max(0, Math.floor(job.current ?? 0)),
        total: Math.max(0, Math.floor(job.total ?? 0)),
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

export class ServerJobsStore {
    snapshot = $state<JobsSnapshot | null>(null);
    loading = $state(false);
    error = $state<string | null>(null);
    private retainCount = 0;
    private timer: ReturnType<typeof setTimeout> | null = null;
    private request: Promise<void> | null = null;

    get activeJobs(): JobProgressItem[] {
        const snapshot = this.snapshot;
        if (!snapshot) return [];
        const capturedAt = parseTimestamp(snapshot.captured_at, Date.now());
        return snapshot.items
            .filter((job) => !['completed', 'failed'].includes(job.status))
            .map((job) => toProgressItem(job, capturedAt));
    }

    get historyJobs(): JobProgressItem[] {
        const snapshot = this.snapshot;
        if (!snapshot) return [];
        const capturedAt = parseTimestamp(snapshot.captured_at, Date.now());
        return snapshot.items
            .filter((job) => ['completed', 'failed'].includes(job.status))
            .map((job) => toProgressItem(job, capturedAt));
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
        const serverEventIds = new Set(serverJobs.map(correlationEventId).filter((id): id is string => Boolean(id)));
        const local = localJobs.filter((job) => {
            const eventId = correlationEventId(job);
            return !eventId || !serverEventIds.has(eventId);
        });
        return [...serverJobs, ...local];
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
