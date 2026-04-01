import { fetchAnalysisStatus, type AnalysisStatus } from '../api/maintenance';
import type { QueueTelemetryByKind } from '../jobs/pipeline';
import { authStore } from './auth.svelte';
import { jobDiagnosticsStore } from './job_diagnostics.svelte';
import { jobProgressStore } from './job_progress.svelte';
import { notificationCenter } from './notification_center.svelte';

const RECLASSIFY_PROGRESS_ID = 'reclassify:progress';
const DEFAULT_BATCH_ANALYSIS_TITLE = 'Batch Analysis';
const DEFAULT_BATCH_ANALYSIS_COMPLETE_MESSAGE = 'Batch analysis complete';

interface AnalysisQueueStatusStoreOptions {
    fetchAnalysisStatus?: () => Promise<AnalysisStatus>;
    pollIntervalMs?: number;
    hasOwnerAccess?: () => boolean;
    recordError?: (input: {
        source: 'job';
        component: string;
        stage: 'poll';
        reasonCode: string;
        message: string;
        severity: 'warning';
        context: Record<string, unknown>;
    }) => void;
}

function toErrorMessage(error: unknown, fallback: string): string {
    if (error instanceof Error) return error.message || fallback;
    if (typeof error === 'string' && error.trim().length > 0) return error.trim();
    return fallback;
}

function normalizeCount(value: unknown): number {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return 0;
    return Math.max(0, Math.floor(parsed));
}

function settleSyntheticBatchProgress(status: AnalysisStatus): void {
    const remaining = normalizeCount(status.pending) + normalizeCount(status.active);
    if (remaining > 0) return;

    const existingBatchJob = jobProgressStore.activeJobs.find((job) => job.id === RECLASSIFY_PROGRESS_ID) ?? null;
    const existingProgressNotification = notificationCenter.items.find((item) => item.id === RECLASSIFY_PROGRESS_ID) ?? null;
    const completedTotal = Math.max(
        0,
        normalizeCount(existingBatchJob?.total),
        normalizeCount(existingBatchJob?.current),
        normalizeCount(existingProgressNotification?.meta?.total),
        normalizeCount(existingProgressNotification?.meta?.current)
    );

    if (existingProgressNotification) {
        if (completedTotal > 0) {
            notificationCenter.upsert({
                ...existingProgressNotification,
                type: 'update',
                title: existingProgressNotification.title || existingBatchJob?.title || DEFAULT_BATCH_ANALYSIS_TITLE,
                message: DEFAULT_BATCH_ANALYSIS_COMPLETE_MESSAGE,
                timestamp: Date.now(),
                read: true,
                meta: {
                    ...(existingProgressNotification.meta ?? {}),
                    kind: 'reclassify_batch',
                    current: completedTotal,
                    total: completedTotal,
                    route: '/settings#data',
                    open_label: existingProgressNotification.meta?.open_label
                }
            });
        } else {
            notificationCenter.remove(RECLASSIFY_PROGRESS_ID);
        }
    }

    if (existingBatchJob || completedTotal > 0) {
        jobProgressStore.markCompleted({
            id: RECLASSIFY_PROGRESS_ID,
            kind: 'reclassify_batch',
            title: existingBatchJob?.title || existingProgressNotification?.title || DEFAULT_BATCH_ANALYSIS_TITLE,
            message: DEFAULT_BATCH_ANALYSIS_COMPLETE_MESSAGE,
            route: existingBatchJob?.route || '/settings#data',
            current: completedTotal,
            total: completedTotal,
            source: 'poll'
        });
        return;
    }

    jobProgressStore.remove(RECLASSIFY_PROGRESS_ID);
}

export class AnalysisQueueStatusStore {
    analysisStatus = $state<AnalysisStatus | null>(null);
    queueByKind = $state<QueueTelemetryByKind>({});
    private analysisStatusSignature = '';
    private refCount = 0;
    private pollTimer: ReturnType<typeof setInterval> | null = null;
    private readonly fetcher: () => Promise<AnalysisStatus>;
    private readonly pollIntervalMs: number;
    private readonly hasOwnerAccess: () => boolean;
    private readonly recordError?: AnalysisQueueStatusStoreOptions['recordError'];

    constructor(options: AnalysisQueueStatusStoreOptions = {}) {
        this.fetcher = options.fetchAnalysisStatus ?? fetchAnalysisStatus;
        this.pollIntervalMs = options.pollIntervalMs ?? 5000;
        this.hasOwnerAccess = options.hasOwnerAccess ?? (() => authStore.showSettings);
        this.recordError = options.recordError;
    }

    retain(): () => void {
        this.refCount += 1;
        if (this.refCount === 1) {
            void this.refresh();
            this.pollTimer = setInterval(() => {
                void this.refresh();
            }, this.pollIntervalMs);
        }

        return () => {
            this.refCount = Math.max(0, this.refCount - 1);
            if (this.refCount === 0 && this.pollTimer) {
                clearInterval(this.pollTimer);
                this.pollTimer = null;
            }
        };
    }

    async refresh() {
        if (!this.hasOwnerAccess()) return;
        try {
            const status = await this.fetcher();
            settleSyntheticBatchProgress(status);
            const signature = [
                status.pending ?? 0,
                status.active ?? 0,
                status.circuit_open ? 1 : 0,
                status.open_until ?? '',
                status.failure_count ?? '',
                status.pending_capacity ?? '',
                status.pending_available ?? '',
                status.max_concurrent_configured ?? '',
                status.max_concurrent_effective ?? '',
                status.mqtt_pressure_level ?? '',
                status.throttled_for_mqtt_pressure ? 1 : 0,
                status.throttled_for_live_pressure ? 1 : 0,
                status.live_pressure_active ? 1 : 0,
                status.live_in_flight ?? '',
                status.live_queued ?? '',
                status.mqtt_in_flight ?? '',
                status.mqtt_in_flight_capacity ?? ''
            ].join('|');
            if (signature !== this.analysisStatusSignature) {
                this.analysisStatus = status;
                this.analysisStatusSignature = signature;
            }
            this.queueByKind = {
                ...this.queueByKind,
                reclassify: {
                    queued: normalizeCount(status.pending),
                    running: normalizeCount(status.active),
                    queueDepthKnown: true,
                    updatedAt: Date.now(),
                    maxConcurrentConfigured: normalizeCount(status.max_concurrent_configured),
                    maxConcurrentEffective: normalizeCount(status.max_concurrent_effective),
                    mqttPressureLevel: typeof status.mqtt_pressure_level === 'string' ? status.mqtt_pressure_level : undefined,
                    throttledForMqttPressure: status.throttled_for_mqtt_pressure === true,
                    throttledForLivePressure: status.throttled_for_live_pressure === true,
                    liveInFlight: normalizeCount(status.live_in_flight),
                    liveQueued: normalizeCount(status.live_queued),
                    mqttInFlight: normalizeCount(status.mqtt_in_flight),
                    mqttInFlightCapacity: normalizeCount(status.mqtt_in_flight_capacity)
                }
            };
        } catch (error) {
            this.recordError?.({
                source: 'job',
                component: 'reclassify_queue',
                stage: 'poll',
                reasonCode: 'status_fetch_failed',
                message: toErrorMessage(error, 'Failed to fetch reclassification queue status'),
                severity: 'warning',
                context: { route: '/api/maintenance/analysis/status' }
            });
            if (!this.queueByKind.reclassify) {
                this.queueByKind = {
                    ...this.queueByKind,
                    reclassify: {
                        queued: 0,
                        running: 0,
                        queueDepthKnown: false,
                        updatedAt: Date.now()
                    }
                };
            }
        }
    }
}

export const analysisQueueStatusStore = new AnalysisQueueStatusStore({
    recordError: (input) => {
        jobDiagnosticsStore.recordError(input);
    }
});
