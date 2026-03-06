export interface ReclassifyStatusResponse {
    video_classification_status?: string | null;
    video_classification_error?: string | null;
}

interface ReclassifyJob {
    id: string;
    kind: string;
    title: string;
    message?: string;
    route?: string;
    status: string;
    current: number;
    total: number;
    updatedAt?: number;
}

interface JobProgressStoreLike {
    activeJobs: ReclassifyJob[];
    upsertRunning: (input: {
        id: string;
        kind: string;
        title: string;
        message?: string;
        route?: string;
        current: number;
        total: number;
        source: 'poll';
    }) => void;
    markCompleted: (input: {
        id: string;
        kind: string;
        title: string;
        message?: string;
        route?: string;
        current: number;
        total: number;
        source: 'poll';
    }) => void;
    markFailed: (input: {
        id: string;
        kind: string;
        title: string;
        message?: string;
        route?: string;
        current: number;
        total: number;
        source: 'poll';
    }) => void;
}

interface LoggerLike {
    warn: (message: string, context?: any) => void;
}

interface ReclassifyRecoveryOptions {
    fetchStatus: (eventId: string) => Promise<ReclassifyStatusResponse>;
    jobProgress: JobProgressStoreLike;
    logger: LoggerLike;
    retryMs?: number;
    now?: () => number;
}

const RECLASSIFY_JOB_ID_PREFIX = 'reclassify:';

export function createReclassifyRecovery(options: ReclassifyRecoveryOptions) {
    const retryMs = Number.isFinite(options.retryMs) ? Math.max(1000, Math.floor(options.retryMs as number)) : 30_000;
    const now = options.now ?? (() => Date.now());
    const probeInFlight = new Set<string>();
    const lastProbeAt = new Map<string, number>();

    function parseEventId(jobId: string): string | null {
        if (typeof jobId !== 'string') return null;
        if (!jobId.startsWith(RECLASSIFY_JOB_ID_PREFIX)) return null;
        const eventId = jobId.slice(RECLASSIFY_JOB_ID_PREFIX.length).trim();
        return eventId.length > 0 ? eventId : null;
    }

    async function reconcile(): Promise<void> {
        const currentTime = now();
        const reconcilableJobs = options.jobProgress.activeJobs.filter((job) => {
            if (job.kind !== 'reclassify') return false;
            if (job.status === 'stale') return true;
            if (job.status !== 'running') return false;
            const updatedAt = Number.isFinite(Number(job.updatedAt)) ? Number(job.updatedAt) : 0;
            return currentTime - updatedAt >= retryMs;
        });
        if (reconcilableJobs.length === 0) return;

        for (const job of reconcilableJobs) {
            const eventId = parseEventId(job.id);
            if (!eventId) continue;
            if (probeInFlight.has(eventId)) continue;

            const previousProbeAt = lastProbeAt.get(eventId) ?? 0;
            if (currentTime - previousProbeAt < retryMs) continue;

            lastProbeAt.set(eventId, currentTime);
            probeInFlight.add(eventId);
            try {
                const status = await options.fetchStatus(eventId);
                const normalizedStatus = String(status.video_classification_status ?? '').trim().toLowerCase();

                if (normalizedStatus === 'completed') {
                    options.jobProgress.markCompleted({
                        id: job.id,
                        kind: job.kind,
                        title: job.title,
                        message: job.message,
                        route: job.route,
                        current: job.current,
                        total: job.total,
                        source: 'poll'
                    });
                    continue;
                }

                if (normalizedStatus === 'failed' || normalizedStatus === 'error') {
                    options.jobProgress.markFailed({
                        id: job.id,
                        kind: job.kind,
                        title: job.title,
                        message: status.video_classification_error?.trim() || 'Unknown error',
                        route: job.route,
                        current: job.current,
                        total: job.total,
                        source: 'poll'
                    });
                    continue;
                }

                if (normalizedStatus === 'processing' || normalizedStatus === 'pending') {
                    options.jobProgress.upsertRunning({
                        id: job.id,
                        kind: job.kind,
                        title: job.title,
                        message: job.message,
                        route: job.route,
                        current: job.current,
                        total: job.total,
                        source: 'poll'
                    });
                }
            } catch (error) {
                options.logger.warn('reclassify_status_probe_failed', { eventId, error });
            } finally {
                probeInFlight.delete(eventId);
            }
        }
    }

    return {
        parseEventId,
        reconcile
    };
}
