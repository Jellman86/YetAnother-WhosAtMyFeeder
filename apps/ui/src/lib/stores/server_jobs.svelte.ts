import { get } from 'svelte/store';
import { _, locale } from 'svelte-i18n';
import type { JobsSnapshot, ServerJob } from '../api/jobs';
import type { QueueTelemetryByKind } from '../jobs/pipeline';
import type { JobProgressItem } from './job_progress.svelte';

function parseTimestamp(value: string | null | undefined, fallback: number): number {
    if (!value) return fallback;
    const parsed = Date.parse(value);
    return Number.isFinite(parsed) ? parsed : fallback;
}

function titleForJob(job: ServerJob): string {
    // A Frigate event id is an identifier, not a title. Naming the work is what tells an owner
    // whether a row matters to them; the event it belongs to is reachable by opening the row.
    const words = job.kind.replace(/_/g, ' ');
    const humanKind = words.charAt(0).toUpperCase() + words.slice(1);
    // A poll can materialize jobs before the locale finishes loading, and formatting then throws.
    if (!get(locale)) return humanKind;
    return get(_)(`jobs.kind_${job.kind}`, { default: humanKind });
}

/** Two jobs of one kind look identical without it, so the event stays visible as detail. */
function detailForJob(job: ServerJob): string | undefined {
    const phaseLabels: Record<string, { key: string; fallback: string }> = {
        updating_photo: { key: 'jobs.phase_updating_photo', fallback: 'Updating photograph' },
        waiting_for_clip: { key: 'jobs.phase_waiting_for_clip', fallback: 'Waiting for recording clip' },
        waiting_for_worker: { key: 'jobs.phase_waiting_for_worker', fallback: 'Waiting for worker recovery' },
        waiting_for_frigate: { key: 'jobs.phase_waiting_for_frigate', fallback: 'Waiting for Frigate to answer' }
    };
    const label = phaseLabels[job.phase ?? ''];
    const phase = label
        ? get(locale) ? get(_)(label.key, { default: label.fallback }) : label.fallback
        : job.phase;
    const parts = [phase, job.event_id].filter((part): part is string => Boolean(part));
    return parts.length > 0 ? parts.join(' \u00b7 ') : undefined;
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
        message: detailForJob(job),
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

/** The server's jobs, as the pushed status snapshot last reported them. */
export class ServerJobsStore {
    snapshot = $state.raw<JobsSnapshot | null>(null);
    private materializedSnapshot: JobsSnapshot | null = null;
    private materializedActive: JobProgressItem[] = [];
    private materializedHistory: JobProgressItem[] = [];
    private previousById = new Map<string, JobProgressItem>();

    ingest(snapshot: JobsSnapshot): void {
        this.snapshot = snapshot;
    }

    clear(): void {
        this.snapshot = null;
    }

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
        // A backfill the browser watches over the stream and the same backfill in the server
        // snapshot share an id; they are one job, whichever side reported last.
        const localById = new Map(localJobs.map((job) => [job.id, job] as const));
        const reconciledServerJobs = serverJobs.map((serverJob) => {
            const eventId = correlationEventId(serverJob);
            const localJob = (eventId ? localByEventId.get(eventId) : undefined) ?? localById.get(serverJob.id);
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
        return [...reconciledServerJobs, ...this.withoutServerJobs(localJobs, reconciledServerJobs)];
    }

    /**
     * The jobs only this browser owns: rows that follow no server job. Ownership is carried by the
     * row (`serverJobId`, set where the row starts following server work), never inferred from a
     * job's absence in the server's list, which stops at a hundred while its lane totals count
     * every job. The banner adds these to the server's own totals.
     */
    browserOnlyActive(localJobs: JobProgressItem[]): JobProgressItem[] {
        return localJobs.filter((job) => !job.serverJobId);
    }

    private withoutServerJobs(localJobs: JobProgressItem[], serverJobs: JobProgressItem[]): JobProgressItem[] {
        const serverEventIds = new Set(serverJobs.map(correlationEventId).filter((id): id is string => Boolean(id)));
        const serverIds = new Set(serverJobs.map((job) => job.id));
        return localJobs.filter((job) => {
            if (serverIds.has(job.id)) return false;
            const eventId = correlationEventId(job);
            return !eventId || !serverEventIds.has(eventId);
        });
    }

    mergeHistory(localJobs: JobProgressItem[]): JobProgressItem[] {
        const byId = new Map(localJobs.map((job) => [job.id, job]));
        for (const job of this.historyJobs) byId.set(job.id, job);
        return [...byId.values()];
    }
}

export const serverJobsStore = new ServerJobsStore();
