import type { Detection } from '../api';
import { notificationPolicy } from '../notifications/policy';

const STALE_PROCESS_MAX_AGE_MS = 45 * 60 * 1000;
const RECLASSIFY_PROGRESS_ID = 'reclassify:progress';
const LEGACY_RECLASSIFY_PROGRESS_PREFIX = 'reclassify:progress:';
const RECLASSIFY_STATE_MAX_IDLE_MS = 5 * 60 * 1000;

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
        modelName: string
    ): void;
    completeReclassification(eventId: string, results: any): void;
}

interface SettingsStoreLike {
    liveAnnouncements: boolean;
}

interface JobProgressLike {
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
}

interface LoggerLike {
    warn(message: string, payload?: any): void;
    error(message: string, error?: any, payload?: any): void;
    sseEvent(event: string, payload?: any): void;
}

interface LiveUpdateDeps {
    t: TranslateFn;
    shouldNotify: () => boolean;
    applyNotificationPolicy: (id: string, signature: string, throttleMs?: number) => boolean;
    notificationCenter: NotificationCenterLike;
    jobProgress: JobProgressLike;
    detectionsStore: DetectionsStoreLike;
    settingsStore: SettingsStoreLike;
    announcer: { announce(message: string): void };
    logger: LoggerLike;
    checkHealth: () => Promise<any>;
    fetchCacheStats: () => Promise<any>;
    onConnected?: () => void;
}

function toDetection(data: any): Detection {
    return {
        frigate_event: data.frigate_event,
        display_name: data.display_name,
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
        video_classification_timestamp: data.video_classification_timestamp
    };
}

export class LiveUpdateCoordinator {
    private deps: LiveUpdateDeps;
    private activeReclassifyEvents = new Set<string>();
    private reclassifyProgressByEvent = new Map<string, { current: number; total: number }>();
    private reclassifyLastUpdateByEvent = new Map<string, number>();
    private reclassifyStartedCount = 0;
    private reclassifyCompletedCount = 0;

    constructor(deps: LiveUpdateDeps) {
        this.deps = deps;
    }

    pruneStaleProcessNotifications() {
        const stale = notificationPolicy.settleStale(this.deps.notificationCenter.items, STALE_PROCESS_MAX_AGE_MS);
        for (const item of stale) {
            this.deps.notificationCenter.upsert(item);
        }
        this.deps.jobProgress.markStale(RECLASSIFY_STATE_MAX_IDLE_MS);
        this.pruneStaleReclassifyState();
    }

    async runOwnerSystemChecks() {
        if (!this.deps.shouldNotify()) return;
        let startupInstanceId = 'unknown';

        try {
            const health: any = await this.deps.checkHealth();
            startupInstanceId = String(health?.startup_instance_id ?? 'unknown');
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
        }
    }

    handlePayload(payload: any) {
        if (!payload || typeof payload !== 'object') {
            this.deps.logger.error('SSE Invalid payload structure', undefined, { payload });
            return;
        }
        if (!payload.type) {
            this.deps.logger.error('SSE Missing payload type', undefined, { payload });
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
                this.markReclassifyStarted(payload.data.event_id, payload.data.total_frames ?? 0);
                this.deps.jobProgress.upsertRunning({
                    id: `reclassify:${payload.data.event_id}`,
                    kind: 'reclassify',
                    title: this.deps.t('actions.reclassify'),
                    route: `/events?event=${encodeURIComponent(payload.data.event_id)}`,
                    current: 0,
                    total: Number(payload.data.total_frames ?? 0),
                    source: 'sse'
                });
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
                this.deps.detectionsStore.updateReclassificationProgress(
                    payload.data.event_id,
                    payload.data.current_frame,
                    payload.data.total_frames,
                    payload.data.frame_score,
                    payload.data.top_label,
                    payload.data.frame_thumb,
                    payload.data.frame_index,
                    payload.data.clip_total,
                    payload.data.model_name
                );
                this.updateReclassifyProgress(payload.data.event_id, payload.data.current_frame, payload.data.total_frames);
                return;
            }

            if (payload.type === 'reclassification_completed') {
                if (!payload.data || !payload.data.event_id) {
                    this.deps.logger.warn('SSE invalid reclassification_completed payload', { payload });
                    return;
                }
                const prior = this.reclassifyProgressByEvent.get(payload.data.event_id);
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
                this.clearReclassifyProgressNotification(payload.data.event_id);
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

    private pruneStaleReclassifyState() {
        const now = Date.now();
        let removedAny = false;
        for (const eventId of this.activeReclassifyEvents) {
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

    private markReclassifyStarted(eventId: string, totalFrames: number = 0) {
        if (!eventId) return;
        const normalizedTotal = Number.isFinite(totalFrames) ? Math.max(0, Math.floor(totalFrames)) : 0;
        if (!this.activeReclassifyEvents.has(eventId) && this.activeReclassifyEvents.size === 0) {
            this.reclassifyStartedCount = 0;
            this.reclassifyCompletedCount = 0;
        }
        if (!this.activeReclassifyEvents.has(eventId)) {
            this.reclassifyStartedCount += 1;
        }
        this.activeReclassifyEvents.add(eventId);
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
        if (!this.activeReclassifyEvents.has(eventId)) {
            this.markReclassifyStarted(eventId, parsedTotal);
        }
        this.reclassifyLastUpdateByEvent.set(eventId, Date.now());
        const activeCount = this.activeReclassifyEvents.size;
        const isBatch = this.reclassifyStartedCount > 1 || activeCount > 1;

        if (!isBatch && parsedCurrent <= 0 && parsedTotal <= 0) return;

        const normalizedTotal = parsedTotal > 0 ? parsedTotal : Math.max(1, parsedCurrent);
        const normalizedCurrent = Math.min(normalizedTotal, parsedCurrent);
        this.reclassifyProgressByEvent.set(eventId, { current: normalizedCurrent, total: normalizedTotal });

        const startedTotal = Math.max(this.reclassifyStartedCount, this.reclassifyCompletedCount + activeCount);
        const batchCurrent = Math.min(startedTotal, this.reclassifyCompletedCount + (activeCount > 0 ? 1 : 0));
        const batchTotal = Math.max(1, startedTotal);
        const signature = isBatch
            ? `batch|${this.reclassifyCompletedCount}|${startedTotal}|${activeCount}`
            : `single|${eventId}|${normalizedCurrent}|${normalizedTotal}`;
        if (!this.deps.applyNotificationPolicy(RECLASSIFY_PROGRESS_ID, signature, 1200)) return;

        this.removeNotificationsByPrefix(LEGACY_RECLASSIFY_PROGRESS_PREFIX);

        const title = isBatch
            ? this.deps.t('settings.data.batch_analysis_title')
            : this.deps.t('actions.reclassify');
        const message = isBatch
            ? `${this.deps.t('settings.data.batch_analysis_active')}: ${activeCount.toLocaleString()} • ${this.reclassifyCompletedCount.toLocaleString()}/${startedTotal.toLocaleString()}`
            : this.deps.t('notifications.event_reclassify_progress', {
                current: normalizedCurrent.toLocaleString(),
                total: normalizedTotal.toLocaleString()
            });
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
            id: RECLASSIFY_PROGRESS_ID,
            type: 'process',
            title,
            message,
            timestamp: Date.now(),
            read: false,
            meta: {
                source: 'sse',
                route: isBatch ? '/settings#data' : `/events?event=${encodeURIComponent(eventId)}`,
                event_id: isBatch ? undefined : eventId,
                current: isBatch ? batchCurrent : normalizedCurrent,
                total: isBatch ? batchTotal : normalizedTotal,
                open_label: this.deps.t('notifications.open_action')
            }
        });
    }

    private clearReclassifyProgressNotification(eventId: string) {
        this.markReclassifyCompleted(eventId);
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
        const normalizedTotal = total > 0 ? total : (hasOngoingState ? Math.max(1, processed) : 0);

        let title = isWeather ? this.deps.t('notifications.event_weather_backfill') : this.deps.t('notifications.event_backfill');
        if (payload.type === 'backfill_complete') {
            title = isWeather ? this.deps.t('notifications.event_weather_backfill_done') : this.deps.t('notifications.event_backfill_done');
        }
        if (payload.type === 'backfill_failed') {
            title = isWeather ? this.deps.t('notifications.event_weather_backfill_failed') : this.deps.t('notifications.event_backfill_failed');
        }

        let message = '';
        if (payload.type === 'backfill_progress' || payload.type === 'backfill_started') {
            message = `${processed.toLocaleString()}/${normalizedTotal.toLocaleString()} • ${updated.toLocaleString()} upd • ${skipped.toLocaleString()} skip • ${errors.toLocaleString()} err`;
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
        const progressTotal = total > 0 ? total : (isTerminal ? processed : normalizedTotal);
        const progressMessage = `${processed.toLocaleString()}/${normalizedTotal.toLocaleString()} • ${updated.toLocaleString()} upd • ${skipped.toLocaleString()} skip • ${errors.toLocaleString()} err`;
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
