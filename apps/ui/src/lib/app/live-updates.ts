import type { Detection } from '../api';
import type { AnalysisStatus } from '../api/maintenance';
import { formatBackfillProgressSummary, resolveRunningBackfillMessage } from '../backfill/progress';
import { notificationPolicy } from '../notifications/policy';

const STALE_PROCESS_MAX_AGE_MS = 45 * 60 * 1000;
const ORPHAN_PROCESS_GRACE_MS = 2 * 60 * 1000;
const RECLASSIFY_PROGRESS_ID = 'reclassify:progress';
const LEGACY_RECLASSIFY_PROGRESS_PREFIX = 'reclassify:progress:';
const RECLASSIFY_STATE_MAX_IDLE_MS = 5 * 60 * 1000;
const ANALYSIS_STATUS_POLL_ROUTE = '/api/maintenance/analysis/status';

type TranslateFn = (key: string, values?: Record<string, any>) => string;

interface NotificationCenterLike {
    items: any[];
    add(item: any): void;
    upsert(item: any): void;
    remove(id: string): void;
}

interface DetectionsStoreLike {
    setConnected(value: boolean): void;
    addDetection(detection: Detection): void;
    updateDetection(detection: Detection): void;
    removeDetection(eventId: string, timestamp?: string): void;
    startReclassification(eventId: string, totalFrames: number, strategy: string | null): void;
    updateReclassificationProgress(
        eventId: string,
        currentFrame: number,
        totalFrames: number,
        frameScore: number,
        topLabel: string,
        frameThumb: string,
        frameIndex: number,
        clipTotal: number,
        modelName: string,
        ramUsage?: string | null
    ): void;
    completeReclassification(eventId: string, results: any): void;
}

interface SettingsStoreLike {
    liveAnnouncements: boolean;
}

interface JobProgressLike {
    activeJobs?: Array<{
        id?: string;
        kind?: string;
        status?: string;
        current?: number;
        total?: number;
    }>;
    upsertRunning(input: {
        id: string;
        kind: string;
        title: string;
        message?: string;
        route?: string;
        current?: number;
        total?: number;
        source?: 'sse' | 'poll' | 'ui' | 'system';
    }): void;
    markCompleted(input: {
        id: string;
        kind: string;
        title: string;
        message?: string;
        route?: string;
        current?: number;
        total?: number;
        source?: 'sse' | 'poll' | 'ui' | 'system';
    }): void;
    markFailed(input: {
        id: string;
        kind: string;
        title: string;
        message?: string;
        route?: string;
        current?: number;
        total?: number;
        source?: 'sse' | 'poll' | 'ui' | 'system';
    }): void;
    markStale(maxIdleMs: number): void;
    remove?(id: string): void;
}

interface LoggerLike {
    warn(message: string, payload?: any): void;
    error(message: string, error?: any, payload?: any): void;
    sseEvent(event: string, payload?: any): void;
}

interface JobDiagnosticsLike {
    ingestHealth(health: any): void;
    recordError(input: {
        source: 'health' | 'sse' | 'runtime' | 'job' | 'system';
        component: string;
        stage?: string;
        reasonCode: string;
        message: string;
        severity?: 'warning' | 'error' | 'critical';
        eventId?: string;
        context?: Record<string, unknown>;
        healthSnapshot?: any;
    }): void;
}

interface LiveUpdateDeps {
    t: TranslateFn;
    shouldNotify: () => boolean;
    hasOwnerAccess?: () => boolean;
    applyNotificationPolicy: (id: string, signature: string, throttleMs?: number) => boolean;
    notificationCenter: NotificationCenterLike;
    jobProgress: JobProgressLike;
    detectionsStore: DetectionsStoreLike;
    settingsStore: SettingsStoreLike;
    announcer: { announce(message: string): void };
    logger: LoggerLike;
    checkHealth: () => Promise<any>;
    fetchCacheStats: () => Promise<any>;
    fetchAnalysisStatus: () => Promise<AnalysisStatus>;
    diagnostics?: JobDiagnosticsLike;
    syncDiagnosticsWorkspace?: () => Promise<void>;
    onConnected?: () => void;
}

function toDetection(data: any): Detection {
    return {
        frigate_event: data.frigate_event,
        display_name: data.display_name,
        category_name: data.category_name,
        score: data.score,
        detection_time: data.timestamp,
        camera_name: data.camera,
        has_clip: data.has_clip,
        is_hidden: data.is_hidden,
        is_favorite: data.is_favorite,
        frigate_score: data.frigate_score,
        sub_label: data.sub_label,
        manual_tagged: data.manual_tagged,
        audio_confirmed: data.audio_confirmed,
        audio_species: data.audio_species,
        audio_score: data.audio_score,
        temperature: data.temperature,
        weather_condition: data.weather_condition,
        weather_cloud_cover: data.weather_cloud_cover,
        weather_wind_speed: data.weather_wind_speed,
        weather_wind_direction: data.weather_wind_direction,
        weather_precipitation: data.weather_precipitation,
        weather_rain: data.weather_rain,
        weather_snowfall: data.weather_snowfall,
        scientific_name: data.scientific_name,
        common_name: data.common_name,
        taxa_id: data.taxa_id,
        video_classification_score: data.video_classification_score,
        video_classification_label: data.video_classification_label,
        video_classification_status: data.video_classification_status,
        video_classification_provider: data.video_classification_provider,
        video_classification_backend: data.video_classification_backend,
        video_classification_model_id: data.video_classification_model_id,
        video_classification_model_name: data.video_classification_model_name,
        video_classification_timestamp: data.video_classification_timestamp
    };
}

export class LiveUpdateCoordinator {
    private deps: LiveUpdateDeps;
    private activeReclassifyEvents = new Map<string, { strategy?: string }>();
    private reclassifyProgressByEvent = new Map<string, { current: number; total: number }>();
    private reclassifyLastUpdateByEvent = new Map<string, number>();
    private reclassifyStartedCount = 0;
    private reclassifyCompletedCount = 0;
    private analysisQueueBaselineTotal = 0;
    private lastStartupInstanceId: string | null = null;

    constructor(deps: LiveUpdateDeps) {
        this.deps = deps;
    }

    pruneStaleProcessNotifications() {
        const stale = notificationPolicy.settleStale(this.deps.notificationCenter.items, STALE_PROCESS_MAX_AGE_MS);
        for (const item of stale) {
            this.deps.notificationCenter.upsert(item);
        }
        this.settleOrphanProcessNotifications();
        this.deps.jobProgress.markStale(RECLASSIFY_STATE_MAX_IDLE_MS);
        this.pruneStaleReclassifyState();
    }

    async runOwnerSystemChecks() {
        if (!this.deps.shouldNotify()) return;
        if (this.deps.hasOwnerAccess && !this.deps.hasOwnerAccess()) return;
        let startupInstanceId = 'unknown';

        try {
            const health: any = await this.deps.checkHealth();
            this.deps.diagnostics?.ingestHealth(health);
            startupInstanceId = String(health?.startup_instance_id ?? 'unknown');
            this.reconcileBackendInstance(startupInstanceId);
            this.reconcileSyntheticBatchFromHealth(health);
            const status = String(health?.status ?? '').trim().toLowerCase();
            if (status && !this.isSystemHealthyStatus(status)) {
                const id = `system:health:${startupInstanceId}`;
                this.removeNotificationsByPrefix('system:health');
                if (!this.deps.notificationCenter.items.some((item) => item.id === id)) {
                    this.deps.notificationCenter.add({
                        id,
                        type: 'system',
                        title: this.deps.t('notifications.system_health_title'),
                        message: this.deps.t('notifications.system_health_message', { status: String(health?.status ?? 'unknown') }),
                        meta: { source: 'health', route: '/settings' }
                    });
                }
            } else {
                this.removeNotificationsByPrefix('system:health');
            }
        } catch (error) {
            this.deps.logger.warn('health_check_failed', { error });
            this.deps.diagnostics?.recordError({
                source: 'health',
                component: 'health_check',
                reasonCode: 'request_failed',
                message: this.toErrorMessage(error, 'Health check request failed'),
                severity: 'warning',
                context: { scope: 'runOwnerSystemChecks' }
            });
        }

        try {
            const cache = await this.deps.fetchCacheStats();
            if (!cache.cache_enabled) {
                const id = `system:cache-disabled:${startupInstanceId}`;
                this.removeNotificationsByPrefix('system:cache-disabled');
                if (!this.deps.notificationCenter.items.some((item) => item.id === id)) {
                    this.deps.notificationCenter.add({
                        id,
                        type: 'system',
                        title: this.deps.t('notifications.system_cache_disabled_title'),
                        message: this.deps.t('notifications.system_cache_disabled_message'),
                        meta: { source: 'cache', route: '/settings' }
                    });
                }
            } else {
                this.removeNotificationsByPrefix('system:cache-disabled');
            }
        } catch (error) {
            this.deps.logger.warn('cache_stats_check_failed', { error });
            this.deps.diagnostics?.recordError({
                source: 'health',
                component: 'cache_stats',
                reasonCode: 'request_failed',
                message: this.toErrorMessage(error, 'Cache stats request failed'),
                severity: 'warning',
                context: { scope: 'runOwnerSystemChecks' }
            });
        }

        if (this.deps.syncDiagnosticsWorkspace) {
            try {
                await this.deps.syncDiagnosticsWorkspace();
            } catch (error) {
                this.deps.logger.warn('diagnostics_workspace_sync_failed', { error });
                this.deps.diagnostics?.recordError({
                    source: 'health',
                    component: 'diagnostics_workspace',
                    reasonCode: 'request_failed',
                    message: this.toErrorMessage(error, 'Diagnostics workspace refresh failed'),
                    severity: 'warning',
                    context: { scope: 'runOwnerSystemChecks' }
                });
            }
        }
    }

    async syncAnalysisQueueStatus() {
        if (!this.deps.shouldNotify()) return;
        if (this.deps.hasOwnerAccess && !this.deps.hasOwnerAccess()) return;

        try {
            const status = await this.deps.fetchAnalysisStatus();
            this.reconcileAnalysisQueueStatus(status);
        } catch (error) {
            this.deps.logger.warn('analysis_status_check_failed', { error });
            this.deps.diagnostics?.recordError({
                source: 'job',
                component: 'analysis_status',
                stage: 'poll',
                reasonCode: 'status_fetch_failed',
                message: this.toErrorMessage(error, 'Failed to load analysis status'),
                severity: 'warning',
                context: { route: ANALYSIS_STATUS_POLL_ROUTE, scope: 'syncAnalysisQueueStatus' }
            });
        }
    }

    handlePayload(payload: any) {
        if (!payload || typeof payload !== 'object') {
            this.deps.logger.error('SSE Invalid payload structure', undefined, { payload });
            this.deps.diagnostics?.recordError({
                source: 'sse',
                component: 'sse',
                reasonCode: 'invalid_payload',
                message: 'SSE payload was not an object',
                severity: 'warning',
                context: { payload }
            });
            return;
        }
        if (!payload.type) {
            this.deps.logger.error('SSE Missing payload type', undefined, { payload });
            this.deps.diagnostics?.recordError({
                source: 'sse',
                component: 'sse',
                reasonCode: 'missing_type',
                message: 'SSE payload missing type field',
                severity: 'warning',
                context: { payload }
            });
            return;
        }

        try {
            if (payload.type === 'connected') {
                this.deps.detectionsStore.setConnected(true);
                this.deps.onConnected?.();
                this.deps.logger.sseEvent('connected', { message: payload.message });
                return;
            }

            if (payload.type === 'detection') {
                if (!payload.data || !payload.data.frigate_event) {
                    this.deps.logger.error('SSE Invalid detection data', undefined, { payload });
                    return;
                }
                const newDetection = toDetection(payload.data);
                this.deps.detectionsStore.addDetection(newDetection);
                if (this.deps.settingsStore.liveAnnouncements) {
                    this.deps.announcer.announce(`New bird detected: ${newDetection.display_name} at ${newDetection.camera_name}`);
                }
                this.addDetectionNotification(newDetection);
                return;
            }

            if (payload.type === 'detection_updated') {
                if (!payload.data || !payload.data.frigate_event) {
                    this.deps.logger.error('SSE Invalid detection_updated data', undefined, { payload });
                    return;
                }
                this.deps.detectionsStore.updateDetection(toDetection(payload.data));
                this.reconcileReclassifyFromDetectionUpdate(payload.data);
                return;
            }

            if (payload.type === 'detection_deleted') {
                if (!payload.data || !payload.data.frigate_event) {
                    this.deps.logger.error('SSE Invalid detection_deleted data', undefined, { payload });
                    return;
                }
                this.deps.detectionsStore.removeDetection(payload.data.frigate_event, payload.data.timestamp);
                return;
            }

            if (payload.type === 'reclassification_started') {
                if (!payload.data || !payload.data.event_id) {
                    this.deps.logger.warn('SSE invalid reclassification_started payload', { payload });
                    return;
                }
                if (!this.deps.shouldNotify()) {
                    return;
                }
                this.markReclassifyStarted(payload.data.event_id, payload.data.total_frames ?? 0, payload.data.strategy);
                const isBatch = payload.data.strategy === 'auto_video';
                if (!isBatch) {
                    this.deps.jobProgress.upsertRunning({
                        id: `reclassify:${payload.data.event_id}`,
                        kind: 'reclassify',
                        title: this.deps.t('actions.reclassify'),
                        route: `/events?event=${encodeURIComponent(payload.data.event_id)}`,
                        current: 0,
                        total: Number(payload.data.total_frames ?? 0),
                        source: 'sse'
                    });
                }
                this.deps.detectionsStore.startReclassification(
                    payload.data.event_id,
                    payload.data.total_frames ?? 15,
                    payload.data.strategy ?? null
                );
                this.updateReclassifyProgress(payload.data.event_id, 0, payload.data.total_frames ?? 0);
                return;
            }

            if (payload.type === 'reclassification_progress') {
                if (!payload.data || !payload.data.event_id) {
                    this.deps.logger.warn('SSE invalid reclassification_progress payload', { payload });
                    return;
                }
                if (!this.deps.shouldNotify()) {
                    return;
                }
                this.deps.detectionsStore.updateReclassificationProgress(
                    payload.data.event_id,
                    payload.data.current_frame,
                    payload.data.total_frames,
                    payload.data.frame_score,
                    payload.data.top_label,
                    payload.data.frame_thumb,
                    payload.data.frame_index,
                    payload.data.clip_total,
                    payload.data.model_name,
                    payload.data.ram_usage
                );
                this.updateReclassifyProgress(payload.data.event_id, payload.data.current_frame, payload.data.total_frames);
                return;
            }

            if (payload.type === 'reclassification_completed') {
                if (!payload.data || !payload.data.event_id) {
                    this.deps.logger.warn('SSE invalid reclassification_completed payload', { payload });
                    return;
                }
                if (this.deps.shouldNotify()) {
                    const prior = this.reclassifyProgressByEvent.get(payload.data.event_id);
                    const isBatch = this.activeReclassifyEvents.get(payload.data.event_id)?.strategy === 'auto_video';
                    if (!isBatch) {
                        this.deps.jobProgress.markCompleted({
                            id: `reclassify:${payload.data.event_id}`,
                            kind: 'reclassify',
                            title: this.deps.t('actions.reclassify'),
                            message: this.deps.t('notifications.event_reclassify'),
                            route: `/events?event=${encodeURIComponent(payload.data.event_id)}`,
                            current: prior?.current ?? 0,
                            total: prior?.total ?? 0,
                            source: 'sse'
                        });
                    }
                    this.clearReclassifyProgressNotification(payload.data.event_id);
                }
                this.deps.detectionsStore.completeReclassification(
                    payload.data.event_id,
                    payload.data.results
                );
                const topLabel = Array.isArray(payload.data.results) && payload.data.results.length > 0
                    ? payload.data.results[0]?.label ?? null
                    : null;
                this.addReclassifyNotification(payload.data.event_id, topLabel);
                return;
            }

            if (payload.type === 'backfill_started' || payload.type === 'backfill_progress' || payload.type === 'backfill_complete' || payload.type === 'backfill_failed') {
                this.updateBackfillNotification(payload);
                return;
            }

            if (payload.type === 'settings_updated') {
                const signature = `${payload.type}|${JSON.stringify(payload.data ?? {})}`;
                if (this.deps.shouldNotify() && this.deps.applyNotificationPolicy('settings:updated', signature, 3000)) {
                    this.deps.notificationCenter.upsert({
                        id: 'settings:updated',
                        type: 'update',
                        title: this.deps.t('notifications.settings_updated_title'),
                        message: this.deps.t('notifications.settings_updated_message'),
                        timestamp: Date.now(),
                        read: false,
                        meta: { source: 'sse', route: '/settings' }
                    });
                }
                return;
            }

            console.warn('SSE Unknown message type:', payload.type);
        } catch (handlerError) {
            console.error(`SSE Handler error for type '${payload.type}':`, handlerError, 'Payload:', payload);
            this.deps.diagnostics?.recordError({
                source: 'sse',
                component: 'sse',
                stage: String(payload?.type ?? 'unknown'),
                reasonCode: 'handler_exception',
                message: this.toErrorMessage(handlerError, 'Unhandled SSE handler exception'),
                severity: 'error',
                context: { payload }
            });
        }
    }

    handleDisconnect(err: any, isDocumentHidden: boolean) {
        this.deps.detectionsStore.setConnected(false);
        if (!this.deps.shouldNotify()) return;
        const id = 'system:sse-disconnected';
        const signature = `${String(err?.type ?? 'error')}|${isDocumentHidden ? 'hidden' : 'visible'}`;
        if (!this.deps.applyNotificationPolicy(id, signature, 120000)) return;
        this.deps.notificationCenter.upsert({
            id,
            type: 'update',
            title: this.deps.t('notifications.live_updates_disconnected_title'),
            message: this.deps.t('notifications.live_updates_disconnected_message'),
            timestamp: Date.now(),
            read: false,
            meta: { source: 'sse', route: '/notifications' }
        });
        this.deps.diagnostics?.recordError({
            source: 'sse',
            component: 'sse',
            reasonCode: 'disconnected',
            message: this.toErrorMessage(err, 'Live updates disconnected'),
            severity: 'warning',
            context: {
                hidden: isDocumentHidden,
                signature
            }
        });
    }

    private toErrorMessage(error: unknown, fallback: string): string {
        if (error instanceof Error) {
            return error.message || fallback;
        }
        if (typeof error === 'string' && error.trim().length > 0) {
            return error.trim();
        }
        return fallback;
    }

    private removeNotificationsByPrefix(prefix: string) {
        const ids = this.deps.notificationCenter.items
            .filter((item) => item.id === prefix || item.id.startsWith(`${prefix}:`))
            .map((item) => item.id);
        for (const id of ids) {
            this.deps.notificationCenter.remove(id);
        }
    }

    private isSystemHealthyStatus(status: string): boolean {
        return status === 'healthy' || status === 'ok';
    }

    private settleOrphanProcessNotifications(): void {
        const activeJobs = Array.isArray(this.deps.jobProgress.activeJobs)
            ? this.deps.jobProgress.activeJobs
            : [];
        const activeJobIds = new Set<string>();
        const activeJobKinds = new Set<string>();
        for (const job of activeJobs) {
            if (!job || typeof job !== 'object') continue;
            const id = typeof job.id === 'string' ? job.id.trim() : '';
            if (id) activeJobIds.add(id);
            const kind = typeof job.kind === 'string' ? job.kind.trim().toLowerCase() : '';
            if (kind) activeJobKinds.add(kind);
        }

        const now = Date.now();
        for (const item of [...this.deps.notificationCenter.items]) {
            if (item.type !== 'process' || item.read) continue;
            const itemTs = Number.isFinite(Number(item.timestamp)) ? Number(item.timestamp) : 0;
            if (itemTs > 0 && now - itemTs < ORPHAN_PROCESS_GRACE_MS) continue;
            if (this.hasBackingActiveJob(item, activeJobIds, activeJobKinds)) continue;
            this.deps.notificationCenter.upsert({
                ...item,
                type: 'update',
                read: true,
                timestamp: now,
                message: item.message ? `${item.message} • sync cleared` : 'Process notification cleared after state sync',
                meta: {
                    ...(item.meta ?? {}),
                    stale: true,
                    source: item.meta?.source ?? 'system'
                }
            });
        }
    }

    private hasBackingActiveJob(item: any, activeJobIds: Set<string>, activeJobKinds: Set<string>): boolean {
        const id = typeof item?.id === 'string' ? item.id.trim() : '';
        const metaKind = typeof item?.meta?.kind === 'string' ? item.meta.kind.trim().toLowerCase() : '';
        if (!id) return true;

        if (id === RECLASSIFY_PROGRESS_ID || id.startsWith(`${RECLASSIFY_PROGRESS_ID}:`)) {
            return activeJobIds.has(RECLASSIFY_PROGRESS_ID)
                || activeJobKinds.has('reclassify')
                || activeJobKinds.has('reclassify_batch');
        }
        if (id.startsWith('reclassify:')) {
            return activeJobIds.has(id) || activeJobKinds.has('reclassify');
        }
        if (id.startsWith('backfill:weather:') || metaKind === 'weather') {
            return activeJobIds.has(id) || activeJobKinds.has('weather_backfill');
        }
        if (id.startsWith('backfill:detections:') || metaKind === 'detections') {
            return activeJobIds.has(id) || activeJobKinds.has('backfill');
        }
        return true;
    }

    private pruneStaleReclassifyState() {
        const now = Date.now();
        let removedAny = false;
        for (const [eventId] of this.activeReclassifyEvents) {
            const lastUpdate = this.reclassifyLastUpdateByEvent.get(eventId) ?? 0;
            if (lastUpdate > 0 && now - lastUpdate <= RECLASSIFY_STATE_MAX_IDLE_MS) continue;
            this.activeReclassifyEvents.delete(eventId);
            this.reclassifyProgressByEvent.delete(eventId);
            this.reclassifyLastUpdateByEvent.delete(eventId);
            removedAny = true;
        }
        if (!removedAny) return;
        if (this.activeReclassifyEvents.size <= 0) {
            this.removeNotificationsByPrefix(RECLASSIFY_PROGRESS_ID);
            this.reclassifyStartedCount = 0;
            this.reclassifyCompletedCount = 0;
            this.reclassifyProgressByEvent.clear();
            this.reclassifyLastUpdateByEvent.clear();
        }
    }

    private addDetectionNotification(det: Detection) {
        if (!this.deps.shouldNotify()) return;
        const id = `detection:${det.frigate_event}`;
        const signature = `${det.frigate_event}|${det.display_name}|${det.camera_name}|${det.detection_time}`;
        if (!this.deps.applyNotificationPolicy(id, signature, 4000)) return;
        const title = this.deps.t('notifications.event_detection');
        const message = this.deps.t('notifications.event_detection_desc', {
            species: det.display_name,
            camera: det.camera_name
        });
        this.deps.notificationCenter.upsert({
            id,
            type: 'detection',
            title,
            message,
            timestamp: Date.now(),
            read: false,
            meta: {
                source: 'sse',
                route: `/events?event=${encodeURIComponent(det.frigate_event)}`,
                event_id: det.frigate_event,
                open_label: this.deps.t('notifications.open_action')
            }
        });
    }

    private reconcileAnalysisQueueStatus(status: AnalysisStatus) {
        const pending = Number.isFinite(Number(status.pending)) ? Math.max(0, Math.floor(Number(status.pending))) : 0;
        const active = Number.isFinite(Number(status.active)) ? Math.max(0, Math.floor(Number(status.active))) : 0;
        const remaining = pending + active;
        const existingProgressNotification = this.deps.notificationCenter.items.find((item) => item.id === RECLASSIFY_PROGRESS_ID) ?? null;
        const existingNotificationTotal = Number(existingProgressNotification?.meta?.total ?? 0);
        const existingNotificationCurrent = Number(existingProgressNotification?.meta?.current ?? 0);
        const existingBatchJob = this.deps.jobProgress.activeJobs?.find((job) => job.id === RECLASSIFY_PROGRESS_ID) ?? null;
        const existingJobTotal = Number(existingBatchJob?.total ?? 0);
        const existingJobCurrent = Number(existingBatchJob?.current ?? 0);
        const hasPerEventJobs = (this.deps.jobProgress.activeJobs ?? []).some(
            (job) => job.kind === 'reclassify' && (job.status === 'running' || job.status === 'stale')
        );

        if (remaining > 0) {
            const priorCompleted = Math.max(
                0,
                existingNotificationCurrent,
                existingJobCurrent,
                this.analysisQueueBaselineTotal > 0 ? Math.max(0, this.analysisQueueBaselineTotal - remaining) : 0
            );
            const baseline = Math.max(
                this.analysisQueueBaselineTotal,
                existingNotificationTotal,
                existingJobTotal,
                remaining + priorCompleted
            );
            this.analysisQueueBaselineTotal = baseline;
            const current = Math.max(0, baseline - remaining);
            const circuitOpen = Boolean(status.circuit_open);
            const pendingLabel = this.deps.t('settings.data.batch_analysis_pending', { default: 'Pending' });
            const activeLabel = this.deps.t('settings.data.batch_analysis_active', { default: 'Active' });
            const message = circuitOpen
                ? `${this.deps.t('settings.data.batch_analysis_circuit_open', { default: 'Circuit breaker open' })} • ${pendingLabel}: ${pending.toLocaleString()} • ${activeLabel}: ${active.toLocaleString()}`
                : `${pendingLabel}: ${pending.toLocaleString()} • ${activeLabel}: ${active.toLocaleString()}`;

            const notificationSignature = [
                'running',
                pending,
                active,
                current,
                baseline,
                circuitOpen ? 1 : 0,
                status.open_until ?? '',
                status.failure_count ?? 0
            ].join('|');
            if (this.deps.applyNotificationPolicy('reclassify:progress:sync', notificationSignature, 1000)) {
                this.deps.notificationCenter.upsert({
                    id: RECLASSIFY_PROGRESS_ID,
                    type: 'process',
                    title: this.deps.t('settings.data.batch_analysis_title'),
                    message,
                    timestamp: Date.now(),
                    read: false,
                    meta: {
                        source: 'poll',
                        route: '/settings#data',
                        kind: 'reclassify_batch',
                        current,
                        total: baseline,
                        open_label: this.deps.t('notifications.open_action')
                    }
                });
            }

            if (hasPerEventJobs) {
                this.deps.jobProgress.remove?.(RECLASSIFY_PROGRESS_ID);
            } else {
                this.deps.jobProgress.upsertRunning({
                    id: RECLASSIFY_PROGRESS_ID,
                    kind: 'reclassify_batch',
                    title: this.deps.t('settings.data.batch_analysis_title'),
                    message,
                    route: '/settings#data',
                    current,
                    total: baseline,
                    source: 'poll'
                });
            }
            return;
        }

        this.settleSyntheticBatchAnalysisState();
    }

    private reconcileSyntheticBatchFromHealth(health: any) {
        const videoClassifier = health?.video_classifier;
        if (!videoClassifier || typeof videoClassifier !== 'object') return;
        const pending = Number.isFinite(Number(videoClassifier.pending)) ? Math.max(0, Math.floor(Number(videoClassifier.pending))) : 0;
        const active = Number.isFinite(Number(videoClassifier.active)) ? Math.max(0, Math.floor(Number(videoClassifier.active))) : 0;
        if (pending > 0 || active > 0) return;
        this.settleSyntheticBatchAnalysisState();
    }

    private settleSyntheticBatchAnalysisState() {
        const existingProgressNotification = this.deps.notificationCenter.items.find((item) => item.id === RECLASSIFY_PROGRESS_ID) ?? null;
        const existingNotificationTotal = Number(existingProgressNotification?.meta?.total ?? 0);
        const existingNotificationCurrent = Number(existingProgressNotification?.meta?.current ?? 0);
        const existingBatchJob = this.deps.jobProgress.activeJobs?.find((job) => job.id === RECLASSIFY_PROGRESS_ID) ?? null;
        const existingJobTotal = Number(existingBatchJob?.total ?? 0);
        const existingJobCurrent = Number(existingBatchJob?.current ?? 0);
        const completedTotal = Math.max(
            0,
            this.analysisQueueBaselineTotal,
            existingNotificationTotal,
            existingJobTotal,
            existingNotificationCurrent,
            existingJobCurrent
        );
        const alreadySettled = !existingBatchJob
            && this.analysisQueueBaselineTotal === 0
            && Boolean(existingProgressNotification)
            && existingProgressNotification?.type === 'update'
            && existingProgressNotification?.read === true;
        if (alreadySettled) {
            return;
        }
        const completionMessage = this.deps.t('settings.data.batch_analysis_complete', { default: 'Batch analysis complete' });

        if (existingProgressNotification) {
            this.deps.notificationCenter.upsert({
                ...existingProgressNotification,
                type: 'update',
                title: this.deps.t('settings.data.batch_analysis_title'),
                message: completionMessage,
                timestamp: Date.now(),
                read: true,
                meta: {
                    ...(existingProgressNotification.meta ?? {}),
                    source: 'poll',
                    kind: 'reclassify_batch',
                    current: completedTotal,
                    total: completedTotal,
                    route: '/settings#data',
                    open_label: this.deps.t('notifications.open_action')
                }
            });
        }

        if (existingBatchJob || completedTotal > 0) {
            this.deps.jobProgress.markCompleted({
                id: RECLASSIFY_PROGRESS_ID,
                kind: 'reclassify_batch',
                title: this.deps.t('settings.data.batch_analysis_title'),
                message: completionMessage,
                route: '/settings#data',
                current: completedTotal,
                total: completedTotal,
                source: 'poll'
            });
        } else {
            this.deps.jobProgress.remove?.(RECLASSIFY_PROGRESS_ID);
        }

        this.analysisQueueBaselineTotal = 0;
    }

    private reconcileBackendInstance(startupInstanceId: string) {
        const normalized = typeof startupInstanceId === 'string' ? startupInstanceId.trim() : '';
        if (!normalized) return;
        const prior = this.lastStartupInstanceId;
        this.lastStartupInstanceId = normalized;
        if (!prior || prior === normalized) return;
        this.clearSyntheticBatchAnalysisState();
    }

    private clearSyntheticBatchAnalysisState() {
        this.analysisQueueBaselineTotal = 0;
        this.deps.jobProgress.remove?.(RECLASSIFY_PROGRESS_ID);
        this.deps.notificationCenter.remove(RECLASSIFY_PROGRESS_ID);
    }

    private reconcileReclassifyFromDetectionUpdate(data: any) {
        if (!data || typeof data !== 'object') return;
        const eventId = typeof data.frigate_event === 'string' ? data.frigate_event.trim() : '';
        if (!eventId) return;
        const statusRaw = data.video_classification_status;
        const status = typeof statusRaw === 'string' ? statusRaw.trim().toLowerCase() : '';
        if (!status) return;

        const isTracked = this.activeReclassifyEvents.has(eventId) || this.reclassifyProgressByEvent.has(eventId);
        if (!isTracked) return;

        const prior = this.reclassifyProgressByEvent.get(eventId);
        const current = prior?.current ?? 0;
        const total = prior?.total ?? 0;
        const route = `/events?event=${encodeURIComponent(eventId)}`;
        const title = this.deps.t('actions.reclassify');

        if (status === 'completed') {
            this.deps.jobProgress.markCompleted({
                id: `reclassify:${eventId}`,
                kind: 'reclassify',
                title,
                message: this.deps.t('notifications.event_reclassify'),
                route,
                current,
                total,
                source: 'sse'
            });
            this.clearReclassifyProgressNotification(eventId);
            return;
        }

        if (status === 'failed' || status === 'error') {
            const errorMessage = typeof data.video_classification_error === 'string' && data.video_classification_error.trim().length > 0
                ? data.video_classification_error.trim()
                : 'Unknown error';
            this.deps.jobProgress.markFailed({
                id: `reclassify:${eventId}`,
                kind: 'reclassify',
                title,
                message: this.deps.t('notifications.reclassify_failed', { message: errorMessage }),
                route,
                current,
                total,
                source: 'sse'
            });
            this.clearReclassifyProgressNotification(eventId);
            return;
        }

        if (status === 'processing') {
            this.reclassifyLastUpdateByEvent.set(eventId, Date.now());
            this.deps.jobProgress.upsertRunning({
                id: `reclassify:${eventId}`,
                kind: 'reclassify',
                title,
                message: total > 0
                    ? this.deps.t('notifications.event_reclassify_progress', {
                        current: current.toLocaleString(),
                        total: total.toLocaleString()
                    })
                    : undefined,
                route,
                current,
                total,
                source: 'sse'
            });
        }
    }

    private addReclassifyNotification(eventId: string, label: string | null) {
        if (!this.deps.shouldNotify()) return;
        const id = `reclassify:${eventId}`;
        const signature = `${eventId}|${label ?? 'unknown'}`;
        if (!this.deps.applyNotificationPolicy(id, signature, 1500)) return;
        const title = this.deps.t('notifications.event_reclassify');
        const message = this.deps.t('notifications.event_reclassify_desc', {
            species: label ?? 'Unknown'
        });
        this.deps.notificationCenter.upsert({
            id,
            type: 'update',
            title,
            message,
            timestamp: Date.now(),
            read: false,
            meta: {
                source: 'sse',
                route: `/events?event=${encodeURIComponent(eventId)}`,
                event_id: eventId,
                open_label: this.deps.t('notifications.open_action')
            }
        });
    }

    private markReclassifyStarted(eventId: string, totalFrames: number = 0, strategy?: string) {
        if (!eventId) return;
        const normalizedTotal = Number.isFinite(totalFrames) ? Math.max(0, Math.floor(totalFrames)) : 0;
        if (!this.activeReclassifyEvents.has(eventId) && this.activeReclassifyEvents.size === 0) {
            this.reclassifyStartedCount = 0;
            this.reclassifyCompletedCount = 0;
        }
        if (!this.activeReclassifyEvents.has(eventId)) {
            this.reclassifyStartedCount += 1;
        }
        this.activeReclassifyEvents.set(eventId, { strategy });
        this.reclassifyLastUpdateByEvent.set(eventId, Date.now());
        if (!this.reclassifyProgressByEvent.has(eventId)) {
            this.reclassifyProgressByEvent.set(eventId, { current: 0, total: normalizedTotal });
        }
    }

    private markReclassifyCompleted(eventId: string) {
        const wasActive = this.activeReclassifyEvents.delete(eventId);
        this.reclassifyProgressByEvent.delete(eventId);
        this.reclassifyLastUpdateByEvent.delete(eventId);
        if (wasActive) {
            this.reclassifyCompletedCount = Math.min(this.reclassifyStartedCount, this.reclassifyCompletedCount + 1);
        }
    }

    private updateReclassifyProgress(eventId: string, current: number, total: number) {
        if (!this.deps.shouldNotify()) return;
        if (!eventId) return;
        const parsedCurrent = Number.isFinite(current) ? Math.max(0, Math.floor(current)) : 0;
        const parsedTotal = Number.isFinite(total) ? Math.max(0, Math.floor(total)) : 0;
        
        const existingMeta = this.activeReclassifyEvents.get(eventId);
        if (!existingMeta) {
            this.markReclassifyStarted(eventId, parsedTotal);
        }
        this.reclassifyLastUpdateByEvent.set(eventId, Date.now());

        if (parsedCurrent <= 0 && parsedTotal <= 0) return;

        const normalizedTotal = parsedTotal > 0 ? parsedTotal : Math.max(1, parsedCurrent);
        const normalizedCurrent = Math.min(normalizedTotal, parsedCurrent);
        this.reclassifyProgressByEvent.set(eventId, { current: normalizedCurrent, total: normalizedTotal });

        const strategy = this.activeReclassifyEvents.get(eventId)?.strategy;
        const isBatch = strategy === 'auto_video';

        if (isBatch) {
            this.deps.jobProgress.remove?.(`reclassify:${eventId}`);
            return;
        }

        const notificationId = `reclassify:progress:${eventId}`;
        const signature = `single|${eventId}|${normalizedCurrent}|${normalizedTotal}`;
        if (!this.deps.applyNotificationPolicy(notificationId, signature, 1200)) return;

        this.deps.jobProgress.upsertRunning({
            id: `reclassify:${eventId}`,
            kind: 'reclassify',
            title: this.deps.t('actions.reclassify'),
            message: this.deps.t('notifications.event_reclassify_progress', {
                current: normalizedCurrent.toLocaleString(),
                total: normalizedTotal.toLocaleString()
            }),
            route: `/events?event=${encodeURIComponent(eventId)}`,
            current: normalizedCurrent,
            total: normalizedTotal,
            source: 'sse'
        });
        this.deps.notificationCenter.upsert({
            id: notificationId,
            type: 'process',
            title: this.deps.t('actions.reclassify'),
            message: this.deps.t('notifications.event_reclassify_progress', {
                current: normalizedCurrent.toLocaleString(),
                total: normalizedTotal.toLocaleString()
            }),
            timestamp: Date.now(),
            read: false,
            meta: {
                source: 'sse',
                route: `/events?event=${encodeURIComponent(eventId)}`,
                event_id: eventId,
                current: normalizedCurrent,
                total: normalizedTotal,
                open_label: this.deps.t('notifications.open_action')
            }
        });
    }

    private clearReclassifyProgressNotification(eventId: string) {
        const strategy = this.activeReclassifyEvents.get(eventId)?.strategy;
        this.markReclassifyCompleted(eventId);

        if (strategy !== 'auto_video') {
            this.deps.notificationCenter.remove(`reclassify:progress:${eventId}`);
        }

        if (this.activeReclassifyEvents.size <= 0) {
            this.removeNotificationsByPrefix(RECLASSIFY_PROGRESS_ID);
            this.reclassifyStartedCount = 0;
            this.reclassifyCompletedCount = 0;
            this.reclassifyProgressByEvent.clear();
            this.reclassifyLastUpdateByEvent.clear();
        }
    }

    private updateBackfillNotification(payload: any) {
        if (!this.deps.shouldNotify()) return;
        if (!payload || typeof payload !== 'object') return;
        const data = payload.data ?? {};
        const jobId = data.id ?? data.job_id ?? 'unknown';
        const kind = data.kind ?? 'detections';
        const isWeather = kind === 'weather';
        const total = Number.isFinite(Number(data.total)) ? Math.max(0, Math.floor(Number(data.total))) : 0;
        const processed = Number.isFinite(Number(data.processed)) ? Math.max(0, Math.floor(Number(data.processed))) : 0;
        const updated = Number.isFinite(Number(data.updated ?? data.new_detections))
            ? Math.max(0, Math.floor(Number(data.updated ?? data.new_detections)))
            : 0;
        const skipped = Number.isFinite(Number(data.skipped)) ? Math.max(0, Math.floor(Number(data.skipped))) : 0;
        const errors = Number.isFinite(Number(data.errors)) ? Math.max(0, Math.floor(Number(data.errors))) : 0;
        const hasOngoingState = payload.type === 'backfill_progress' || payload.type === 'backfill_started';
        const normalizedTotal = total > 0 ? total : 0;

        let title = isWeather ? this.deps.t('notifications.event_weather_backfill') : this.deps.t('notifications.event_backfill');
        if (payload.type === 'backfill_complete') {
            title = isWeather ? this.deps.t('notifications.event_weather_backfill_done') : this.deps.t('notifications.event_backfill_done');
        }
        if (payload.type === 'backfill_failed') {
            title = isWeather ? this.deps.t('notifications.event_weather_backfill_failed') : this.deps.t('notifications.event_backfill_failed');
        }

        let message = '';
        if (payload.type === 'backfill_progress' || payload.type === 'backfill_started') {
            message = resolveRunningBackfillMessage(
                {
                    status: 'running',
                    message: typeof data.message === 'string' ? data.message : ''
                },
                formatBackfillProgressSummary(processed, normalizedTotal, updated, skipped, errors)
            );
        } else if (payload.type === 'backfill_complete') {
            message = data.message || `${updated.toLocaleString()} updated, ${skipped.toLocaleString()} skipped, ${errors.toLocaleString()} errors`;
        } else if (payload.type === 'backfill_failed') {
            message = data.message || this.deps.t('notifications.event_backfill_failed');
        }

        const id = `backfill:${kind}:${jobId}`;
        const legacyId = `backfill:${jobId}`;
        if (legacyId !== id) {
            this.deps.notificationCenter.remove(legacyId);
        }
        const signature = `${payload.type}|${jobId}|${processed}|${total}|${updated}|${skipped}|${errors}`;
        const throttleMs = payload.type === 'backfill_progress' ? 1200 : 0;
        if (!this.deps.applyNotificationPolicy(id, signature, throttleMs)) return;
        const isTerminal = payload.type === 'backfill_complete' || payload.type === 'backfill_failed';
        const jobTitle = isWeather ? this.deps.t('notifications.event_weather_backfill') : this.deps.t('notifications.event_backfill');
        const progressTotal = total > 0 ? total : (isTerminal ? processed : 0);
        const progressMessage = resolveRunningBackfillMessage(
            {
                status: 'running',
                message: typeof data.message === 'string' ? data.message : ''
            },
            formatBackfillProgressSummary(processed, normalizedTotal, updated, skipped, errors)
        );
        if (payload.type === 'backfill_failed') {
            this.deps.jobProgress.markFailed({
                id,
                kind: isWeather ? 'weather_backfill' : 'backfill',
                title: jobTitle,
                message,
                route: '/settings',
                current: processed,
                total: progressTotal,
                source: 'sse'
            });
        } else if (payload.type === 'backfill_complete') {
            this.deps.jobProgress.markCompleted({
                id,
                kind: isWeather ? 'weather_backfill' : 'backfill',
                title: jobTitle,
                message,
                route: '/settings',
                current: processed,
                total: progressTotal,
                source: 'sse'
            });
        } else {
            this.deps.jobProgress.upsertRunning({
                id,
                kind: isWeather ? 'weather_backfill' : 'backfill',
                title: jobTitle,
                message: progressMessage,
                route: '/settings',
                current: processed,
                total: progressTotal,
                source: 'sse'
            });
        }

        this.deps.notificationCenter.upsert({
            id,
            type: isTerminal ? 'update' : 'process',
            title,
            message,
            timestamp: Date.now(),
            read: isTerminal,
            meta: {
                source: 'sse',
                route: '/settings',
                kind,
                processed,
                total: normalizedTotal
            }
        });
    }
}
