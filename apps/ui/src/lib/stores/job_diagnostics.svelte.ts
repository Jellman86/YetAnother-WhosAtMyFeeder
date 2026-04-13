import type { DiagnosticsWorkspacePayload } from '../api/diagnostics';

export type JobDiagnosticSeverity = 'warning' | 'error' | 'critical';
export type JobDiagnosticSource = 'health' | 'sse' | 'runtime' | 'job' | 'system';

export interface JobDiagnosticRecordInput {
    source: JobDiagnosticSource;
    component: string;
    stage?: string;
    reasonCode: string;
    message: string;
    severity?: JobDiagnosticSeverity;
    eventId?: string;
    context?: Record<string, unknown>;
    timestamp?: number;
    healthSnapshotId?: string;
    healthSnapshot?: any;
}

export interface JobDiagnosticGroup {
    fingerprint: string;
    source: JobDiagnosticSource;
    component: string;
    stage?: string;
    reasonCode: string;
    severity: JobDiagnosticSeverity;
    message: string;
    count: number;
    firstSeen: number;
    lastSeen: number;
    sampleEventIds: string[];
    latestContext?: Record<string, unknown>;
    latestHealthSnapshotId?: string;
}

export interface JobDiagnosticHealthSnapshot {
    id: string;
    timestamp: number;
    status: string;
    signature: string;
    payload: any;
}

export interface JobDiagnosticBundle {
    id: string;
    label: string;
    createdAt: number;
    summary: {
        error_groups: number;
        total_events: number;
        health_snapshots: number;
    };
    payload: Record<string, unknown>;
}

export interface DiagnosticsExportOptions {
    workspacePayload?: DiagnosticsWorkspacePayload | null;
    currentIssues?: unknown[];
    recentIncidents?: unknown[];
    reportNotes?: string;
}

const MAX_GROUPS = 200;
const MAX_HEALTH_SNAPSHOTS = 80;
const MAX_BUNDLE_HEALTH_SNAPSHOTS = 25;
const MAX_BUNDLES = 20;
const MAX_SAMPLE_EVENT_IDS = 5;
const STORAGE_KEY = 'yawamf_job_diagnostics_v1';

function asFiniteNumber(value: unknown, fallback = 0): number {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return fallback;
    return parsed;
}

function normalizeSeverity(value: unknown): JobDiagnosticSeverity {
    const parsed = typeof value === 'string' ? value.trim().toLowerCase() : '';
    if (parsed === 'critical' || parsed === 'error' || parsed === 'warning') {
        return parsed;
    }
    return 'warning';
}

function severityRank(value: JobDiagnosticSeverity): number {
    if (value === 'critical') return 3;
    if (value === 'error') return 2;
    return 1;
}

function normalizeString(value: unknown, fallback = ''): string {
    if (typeof value !== 'string') return fallback;
    const trimmed = value.trim();
    return trimmed.length > 0 ? trimmed : fallback;
}

function normalizeEventId(value: unknown): string | null {
    const normalized = normalizeString(value);
    return normalized.length > 0 ? normalized : null;
}

function cloneJson<T>(value: T): T {
    return JSON.parse(JSON.stringify(value)) as T;
}

function collectClientContext(): Record<string, unknown> {
    if (typeof window === 'undefined') {
        return {
            timezone: 'unknown',
            language: 'unknown',
            online: null,
            route: null,
            href: null,
            viewport: null,
            screen: null,
            user_agent: null,
        };
    }

    const nav = typeof navigator !== 'undefined' ? navigator : null;
    const screenInfo = typeof screen !== 'undefined' ? screen : null;
    return {
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'unknown',
        language: nav?.language ?? 'unknown',
        languages: Array.isArray(nav?.languages) ? nav?.languages : [],
        online: typeof nav?.onLine === 'boolean' ? nav.onLine : null,
        user_agent: nav?.userAgent ?? null,
        route: window.location?.pathname ?? null,
        href: window.location?.href ?? null,
        viewport: typeof window.innerWidth === 'number' && typeof window.innerHeight === 'number'
            ? { width: window.innerWidth, height: window.innerHeight }
            : null,
        screen: screenInfo
            ? { width: screenInfo.width, height: screenInfo.height }
            : null,
    };
}

function sumCounterMap(counters: unknown): number {
    if (!counters || typeof counters !== 'object') return 0;
    const values = Object.values(counters as Record<string, unknown>);
    let total = 0;
    for (const value of values) {
        total += Math.max(0, Math.floor(asFiniteNumber(value)));
    }
    return total;
}

function normalizeWorkerPoolState(pool: unknown): Record<string, unknown> {
    const value = pool && typeof pool === 'object' ? (pool as Record<string, unknown>) : {};
    return {
        workers: Math.max(0, Math.floor(asFiniteNumber(value.workers))),
        restarts: Math.max(0, Math.floor(asFiniteNumber(value.restarts))),
        last_exit_reason: normalizeString(value.last_exit_reason, ''),
        circuit_open: Boolean(value.circuit_open),
        last_runtime_recovery: value.last_runtime_recovery && typeof value.last_runtime_recovery === 'object'
            ? value.last_runtime_recovery
            : null,
        last_stderr_excerpt: normalizeString(value.last_stderr_excerpt, ''),
        last_stderr_truncated_bytes: Math.max(0, Math.floor(asFiniteNumber(value.last_stderr_truncated_bytes)))
    };
}

function createHealthSignature(health: any): string {
    const status = normalizeString(health?.status, 'unknown').toLowerCase();
    const startupInstanceId = normalizeString(health?.startup_instance_id, 'unknown');
    const eventPipeline = health?.event_pipeline ?? {};
    const mqtt = health?.mqtt ?? {};
    const notificationDispatcher = health?.notification_dispatcher ?? {};
    const dbPool = health?.db_pool ?? {};
    const ml = health?.ml ?? {};
    const liveImage = ml?.live_image ?? {};
    const backgroundImage = ml?.background_image ?? {};
    const executionMode = normalizeString(ml?.execution_mode ?? health?.execution_mode, 'in_process').toLowerCase();
    const workerPools = ml?.worker_pools ?? health?.worker_pools ?? {};
    const liveWorkerPool = normalizeWorkerPoolState(workerPools?.live);
    const backgroundWorkerPool = normalizeWorkerPoolState(workerPools?.background);
    const videoWorkerPool = normalizeWorkerPoolState(workerPools?.video);
    const lateResultsIgnored = Math.max(0, Math.floor(asFiniteNumber(workerPools?.late_results_ignored)));
    const startupWarningCount = Array.isArray(health?.startup_warnings) ? health.startup_warnings.length : 0;
    const videoClassifier = health?.video_classifier ?? {};

    const eventCritical = Math.max(0, Math.floor(asFiniteNumber(eventPipeline?.critical_failures)));
    const eventCriticalActive = eventPipeline?.critical_failure_active === true;
    const stageTimeoutTotal = sumCounterMap(eventPipeline?.stage_timeouts);
    const stageFailureTotal = sumCounterMap(eventPipeline?.stage_failures);
    const lastTimeout = eventPipeline?.last_stage_timeout ?? {};
    const lastFailure = eventPipeline?.last_stage_failure ?? {};
    const lastDrop = eventPipeline?.last_drop ?? {};
    const mqttPressure = normalizeString(mqtt?.pressure_level, 'unknown').toLowerCase();
    const droppedJobs = Math.max(0, Math.floor(asFiniteNumber(notificationDispatcher?.dropped_jobs)));
    const dbWaitMax = Math.max(0, Math.floor(asFiniteNumber(dbPool?.acquire_wait_max_ms)));
    const videoCircuitOpen = !!videoClassifier?.circuit_open;
    const videoCircuitUntil = normalizeString(videoClassifier?.open_until, '-');
    const videoFailureCount = Math.max(0, Math.floor(asFiniteNumber(videoClassifier?.failure_count)));
    const liveImageStatus = normalizeString(liveImage?.status, 'unknown').toLowerCase();
    const liveImagePressure = normalizeString(liveImage?.pressure_level, 'unknown').toLowerCase();
    const liveImageQueued = Math.max(0, Math.floor(asFiniteNumber(liveImage?.queued)));
    const liveImageInFlight = Math.max(0, Math.floor(asFiniteNumber(liveImage?.in_flight)));
    const liveImageAbandoned = Math.max(0, Math.floor(asFiniteNumber(liveImage?.abandoned)));
    const liveImageRecoveryActive = !!liveImage?.recovery_active;
    const liveImageRecoveryReason = normalizeString(liveImage?.recovery_reason, '-');
    const backgroundQueued = Math.max(0, Math.floor(asFiniteNumber(backgroundImage?.queued)));
    const backgroundThrottled = !!(backgroundImage?.background_throttled ?? ml?.background_throttled);

    return [
        status,
        startupInstanceId,
        eventCritical,
        eventCriticalActive,
        stageTimeoutTotal,
        stageFailureTotal,
        normalizeString(lastTimeout?.stage, '-'),
        normalizeString(lastTimeout?.event_id, '-'),
        normalizeString(lastFailure?.stage, '-'),
        normalizeString(lastFailure?.event_id, '-'),
        normalizeString(lastDrop?.reason, '-'),
        normalizeString(lastDrop?.event_id, '-'),
        mqttPressure,
        droppedJobs,
        dbWaitMax,
        videoCircuitOpen ? 'circuit_open' : 'circuit_closed',
        videoCircuitUntil,
        videoFailureCount,
        executionMode,
        liveImageStatus,
        liveImagePressure,
        liveImageQueued,
        liveImageInFlight,
        liveImageAbandoned,
        liveImageRecoveryActive ? 'recovery_active' : 'recovery_idle',
        liveImageRecoveryReason,
        backgroundQueued,
        backgroundThrottled ? 'background_throttled' : 'background_clear',
        Math.floor(asFiniteNumber(liveWorkerPool.workers)),
        Math.floor(asFiniteNumber(liveWorkerPool.restarts)),
        normalizeString(liveWorkerPool.last_exit_reason, '-'),
        Boolean(liveWorkerPool.circuit_open) ? 'live_worker_circuit_open' : 'live_worker_circuit_closed',
        Math.floor(asFiniteNumber(backgroundWorkerPool.workers)),
        Math.floor(asFiniteNumber(backgroundWorkerPool.restarts)),
        normalizeString(backgroundWorkerPool.last_exit_reason, '-'),
        Boolean(backgroundWorkerPool.circuit_open) ? 'background_worker_circuit_open' : 'background_worker_circuit_closed',
        Math.floor(asFiniteNumber(videoWorkerPool.workers)),
        Math.floor(asFiniteNumber(videoWorkerPool.restarts)),
        normalizeString(videoWorkerPool.last_exit_reason, '-'),
        Boolean(videoWorkerPool.circuit_open) ? 'video_worker_circuit_open' : 'video_worker_circuit_closed',
        lateResultsIgnored,
        startupWarningCount
    ].join('|');
}

function sanitizeHealthSnapshotPayload(health: any): Record<string, unknown> {
    const eventPipeline = health?.event_pipeline ?? {};
    const mqtt = health?.mqtt ?? {};
    const notificationDispatcher = health?.notification_dispatcher ?? {};
    const dbPool = health?.db_pool ?? {};
    const ml = health?.ml ?? {};
    const liveImage = ml?.live_image ?? {};
    const backgroundImage = ml?.background_image ?? {};
    const executionMode = normalizeString(ml?.execution_mode ?? health?.execution_mode, 'in_process');
    const workerPools = ml?.worker_pools ?? health?.worker_pools ?? {};
    const videoClassifier = health?.video_classifier ?? {};
    const startupWarnings = Array.isArray(health?.startup_warnings) ? health.startup_warnings : [];

    return {
        status: normalizeString(health?.status, 'unknown'),
        service: normalizeString(health?.service, 'unknown'),
        version: normalizeString(health?.version, 'unknown'),
        startup_instance_id: normalizeString(health?.startup_instance_id, 'unknown'),
        startup_started_at: normalizeString(health?.startup_started_at, ''),
        startup_warnings: startupWarnings.slice(0, 20),
        event_pipeline: {
            status: normalizeString(eventPipeline?.status, 'unknown'),
            started_events: Math.floor(asFiniteNumber(eventPipeline?.started_events)),
            completed_events: Math.floor(asFiniteNumber(eventPipeline?.completed_events)),
            dropped_events: Math.floor(asFiniteNumber(eventPipeline?.dropped_events)),
            incomplete_events: Math.floor(asFiniteNumber(eventPipeline?.incomplete_events)),
            critical_failures: Math.floor(asFiniteNumber(eventPipeline?.critical_failures)),
            critical_failure_active: eventPipeline?.critical_failure_active === true,
            stage_timeouts: eventPipeline?.stage_timeouts ?? {},
            stage_failures: eventPipeline?.stage_failures ?? {},
            stage_fallbacks: eventPipeline?.stage_fallbacks ?? {},
            drop_reasons: eventPipeline?.drop_reasons ?? {},
            last_stage_timeout: eventPipeline?.last_stage_timeout ?? null,
            last_stage_failure: eventPipeline?.last_stage_failure ?? null,
            last_drop: eventPipeline?.last_drop ?? null,
            last_completed: eventPipeline?.last_completed ?? null,
            recent_outcomes: Array.isArray(eventPipeline?.recent_outcomes)
                ? eventPipeline.recent_outcomes.slice(0, 25)
                : []
        },
        mqtt: {
            pressure_level: normalizeString(mqtt?.pressure_level, 'unknown'),
            in_flight: Math.floor(asFiniteNumber(mqtt?.in_flight)),
            in_flight_capacity: Math.floor(asFiniteNumber(mqtt?.in_flight_capacity)),
            topic_liveness_reconnects: Math.floor(asFiniteNumber(mqtt?.topic_liveness_reconnects)),
            last_reconnect_reason: normalizeString(mqtt?.last_reconnect_reason, ''),
            topic_last_message_age_seconds: mqtt?.topic_last_message_age_seconds ?? {},
            topic_message_counts: mqtt?.topic_message_counts ?? {}
        },
        notification_dispatcher: {
            dropped_jobs: Math.floor(asFiniteNumber(notificationDispatcher?.dropped_jobs)),
            completed_jobs: Math.floor(asFiniteNumber(notificationDispatcher?.completed_jobs)),
            failed_jobs: Math.floor(asFiniteNumber(notificationDispatcher?.failed_jobs)),
            queue_size: Math.floor(asFiniteNumber(notificationDispatcher?.queue_size)),
            queue_max: Math.floor(asFiniteNumber(notificationDispatcher?.queue_max))
        },
        db_pool: {
            status: normalizeString(dbPool?.status, 'unknown'),
            acquire_wait_max_ms: Math.floor(asFiniteNumber(dbPool?.acquire_wait_max_ms)),
            acquire_timeouts: Math.floor(asFiniteNumber(dbPool?.acquire_timeouts))
        },
        ml: {
            status: normalizeString(ml?.status, 'unknown'),
            execution_mode: executionMode,
            live_image: {
                status: normalizeString(liveImage?.status, 'unknown'),
                pressure_level: normalizeString(liveImage?.pressure_level, 'unknown'),
                max_concurrent: Math.floor(asFiniteNumber(liveImage?.max_concurrent)),
                in_flight: Math.floor(asFiniteNumber(liveImage?.in_flight)),
                queued: Math.floor(asFiniteNumber(liveImage?.queued)),
                admission_timeout_seconds: asFiniteNumber(liveImage?.admission_timeout_seconds),
                admission_timeouts: Math.floor(asFiniteNumber(liveImage?.admission_timeouts)),
                abandoned: Math.floor(asFiniteNumber(liveImage?.abandoned)),
                late_completions_ignored: Math.floor(asFiniteNumber(liveImage?.late_completions_ignored)),
                oldest_running_age_seconds: asFiniteNumber(liveImage?.oldest_running_age_seconds),
                recovery_active: Boolean(liveImage?.recovery_active),
                recovery_reason: normalizeString(liveImage?.recovery_reason, ''),
                recent_abandoned: Math.floor(asFiniteNumber(liveImage?.recent_abandoned)),
                recent_late_completions_ignored: Math.floor(asFiniteNumber(liveImage?.recent_late_completions_ignored))
            },
            background_image: {
                status: normalizeString(backgroundImage?.status, 'unknown'),
                in_flight: Math.floor(asFiniteNumber(backgroundImage?.in_flight)),
                queued: Math.floor(asFiniteNumber(backgroundImage?.queued)),
                abandoned: Math.floor(asFiniteNumber(backgroundImage?.abandoned)),
                background_throttled: Boolean(backgroundImage?.background_throttled ?? ml?.background_throttled)
            },
            worker_pools: {
                late_results_ignored: Math.floor(asFiniteNumber(workerPools?.late_results_ignored)),
                live: normalizeWorkerPoolState(workerPools?.live),
                background: normalizeWorkerPoolState(workerPools?.background),
                video: normalizeWorkerPoolState(workerPools?.video)
            }
        },
        video_classifier: {
            status: normalizeString(videoClassifier?.status, 'unknown'),
            pending: Math.floor(asFiniteNumber(videoClassifier?.pending)),
            active: Math.floor(asFiniteNumber(videoClassifier?.active)),
            completed: Math.floor(asFiniteNumber(videoClassifier?.completed)),
            failed: Math.floor(asFiniteNumber(videoClassifier?.failed)),
            circuit_open: Boolean(videoClassifier?.circuit_open),
            open_until: normalizeString(videoClassifier?.open_until, ''),
            failure_count: Math.floor(asFiniteNumber(videoClassifier?.failure_count))
        }
    };
}

class JobDiagnosticsStore {
    groups = $state<JobDiagnosticGroup[]>([]);
    healthSnapshots = $state<JobDiagnosticHealthSnapshot[]>([]);
    bundles = $state<JobDiagnosticBundle[]>([]);
    private snapshotCounter = 0;
    private bundleCounter = 0;
    private persistTimer: number | null = null;

    hydrate(): void {
        if (typeof window === 'undefined') return;
        try {
            const raw = window.localStorage.getItem(STORAGE_KEY);
            if (!raw) return;
            const parsed = JSON.parse(raw) as Partial<{
                groups: JobDiagnosticGroup[];
                healthSnapshots: JobDiagnosticHealthSnapshot[];
                bundles: JobDiagnosticBundle[];
            }>;
            const hydratedGroups = Array.isArray(parsed?.groups) ? parsed.groups : [];
            const hydratedSnapshots = Array.isArray(parsed?.healthSnapshots) ? parsed.healthSnapshots : [];
            const hydratedBundles = Array.isArray(parsed?.bundles) ? parsed.bundles : [];
            this.groups = hydratedGroups.slice(0, MAX_GROUPS);
            this.healthSnapshots = hydratedSnapshots.slice(0, MAX_HEALTH_SNAPSHOTS);
            this.bundles = hydratedBundles.slice(0, MAX_BUNDLES);
            this.snapshotCounter = this.healthSnapshots.length;
            this.bundleCounter = this.bundles.length;
        } catch {
            // Ignore localStorage parse/storage errors.
        }
    }

    recordError(input: JobDiagnosticRecordInput): void {
        const source = input.source;
        const component = normalizeString(input.component, 'unknown_component');
        const stage = normalizeString(input.stage);
        const reasonCode = normalizeString(input.reasonCode, 'unknown_reason');
        const message = normalizeString(input.message, 'Unknown diagnostic event');
        const severity = normalizeSeverity(input.severity);
        const timestamp = Math.max(0, Math.floor(asFiniteNumber(input.timestamp, Date.now())));
        const eventId = normalizeEventId(input.eventId);

        const healthSnapshotId = this.resolveHealthSnapshotId(input, timestamp);
        const fingerprint = [
            source,
            component,
            stage || '-',
            reasonCode
        ].join('|');

        const existingIndex = this.groups.findIndex((group) => group.fingerprint === fingerprint);
        const nextGroups = [...this.groups];
        if (existingIndex >= 0) {
            const existing = nextGroups[existingIndex];
            const mergedSeverity = severityRank(severity) >= severityRank(existing.severity)
                ? severity
                : existing.severity;
            const sampleEventIds = this.mergeSampleEventIds(existing.sampleEventIds, eventId);
            nextGroups[existingIndex] = {
                ...existing,
                severity: mergedSeverity,
                message,
                count: existing.count + 1,
                lastSeen: Math.max(existing.lastSeen, timestamp),
                sampleEventIds,
                latestContext: input.context ?? existing.latestContext,
                latestHealthSnapshotId: healthSnapshotId ?? existing.latestHealthSnapshotId
            };
        } else {
            nextGroups.push({
                fingerprint,
                source,
                component,
                stage: stage || undefined,
                reasonCode,
                severity,
                message,
                count: 1,
                firstSeen: timestamp,
                lastSeen: timestamp,
                sampleEventIds: eventId ? [eventId] : [],
                latestContext: input.context,
                latestHealthSnapshotId: healthSnapshotId ?? undefined
            });
        }

        nextGroups.sort((a, b) => {
            const severityDiff = severityRank(b.severity) - severityRank(a.severity);
            if (severityDiff !== 0) return severityDiff;
            return b.lastSeen - a.lastSeen;
        });
        this.groups = nextGroups.slice(0, MAX_GROUPS);
        this.persist();
    }

    ingestHealth(health: any, timestamp: number = Date.now()): void {
        const ts = Math.max(0, Math.floor(asFiniteNumber(timestamp, Date.now())));
        const snapshotId = this.recordHealthSnapshot(health, ts);
        const status = normalizeString(health?.status, 'unknown').toLowerCase();
        if (status !== 'ok' && status !== 'healthy') {
            this.recordError({
                source: 'health',
                component: 'system',
                reasonCode: `status_${status}`,
                message: `System health is ${status}`,
                severity: status === 'degraded' ? 'warning' : 'error',
                timestamp: ts,
                healthSnapshotId: snapshotId,
                context: { status }
            });
        }

        const mqtt = health?.mqtt ?? {};
        const pressureLevel = normalizeString(mqtt?.pressure_level, '').toLowerCase();
        if (pressureLevel === 'high' || pressureLevel === 'critical') {
            this.recordError({
                source: 'health',
                component: 'mqtt',
                stage: 'ingest',
                reasonCode: `pressure_${pressureLevel}`,
                message: `MQTT pressure is ${pressureLevel}`,
                severity: pressureLevel === 'critical' ? 'critical' : 'error',
                timestamp: ts,
                healthSnapshotId: snapshotId,
                context: {
                    pressure_level: pressureLevel,
                    in_flight: asFiniteNumber(mqtt?.in_flight),
                    in_flight_capacity: asFiniteNumber(mqtt?.in_flight_capacity)
                }
            });
        }

        const eventPipeline = health?.event_pipeline ?? {};
        const criticalFailures = Math.max(0, Math.floor(asFiniteNumber(eventPipeline?.critical_failures)));
        const criticalFailureActive = eventPipeline?.critical_failure_active === true;
        if (criticalFailureActive && criticalFailures > 0) {
            this.recordError({
                source: 'health',
                component: 'event_pipeline',
                reasonCode: 'critical_failures',
                message: `Event pipeline reports ${criticalFailures} critical failures`,
                severity: 'critical',
                timestamp: ts,
                healthSnapshotId: snapshotId,
                context: { critical_failures: criticalFailures }
            });
        }

        this.recordStageCounters('stage_timeout', eventPipeline?.stage_timeouts, 'error', ts, snapshotId);
        this.recordStageCounters('stage_failure', eventPipeline?.stage_failures, 'critical', ts, snapshotId);
        this.recordLatestPipelineState(eventPipeline, ts, snapshotId);

        const notificationDispatcher = health?.notification_dispatcher ?? {};
        const droppedJobs = Math.max(0, Math.floor(asFiniteNumber(notificationDispatcher?.dropped_jobs)));
        if (droppedJobs > 0) {
            this.recordError({
                source: 'health',
                component: 'notification_dispatcher',
                reasonCode: 'dropped_jobs',
                message: `Notification dispatcher dropped ${droppedJobs} jobs`,
                severity: 'error',
                timestamp: ts,
                healthSnapshotId: snapshotId,
                context: { dropped_jobs: droppedJobs }
            });
        }

        const videoClassifier = health?.video_classifier ?? {};
        if (videoClassifier?.circuit_open) {
            const failureCount = Math.max(0, Math.floor(asFiniteNumber(videoClassifier?.failure_count)));
            const pending = Math.max(0, Math.floor(asFiniteNumber(videoClassifier?.pending)));
            const active = Math.max(0, Math.floor(asFiniteNumber(videoClassifier?.active)));
            const openUntil = normalizeString(videoClassifier?.open_until, '');
            this.recordError({
                source: 'health',
                component: 'video_classifier',
                stage: 'queue',
                reasonCode: 'circuit_open',
                message: 'Video classification queue paused by circuit breaker',
                severity: 'warning',
                timestamp: ts,
                healthSnapshotId: snapshotId,
                context: {
                    open_until: openUntil || null,
                    failure_count: failureCount,
                    pending,
                    active
                }
            });
        }

        const dbPool = health?.db_pool ?? {};
        const waitMaxMs = Math.max(0, Math.floor(asFiniteNumber(dbPool?.acquire_wait_max_ms)));
        if (waitMaxMs >= 5000) {
            this.recordError({
                source: 'health',
                component: 'db_pool',
                reasonCode: 'acquire_wait_high',
                message: `DB acquire wait max is ${waitMaxMs}ms`,
                severity: 'warning',
                timestamp: ts,
                healthSnapshotId: snapshotId,
                context: { acquire_wait_max_ms: waitMaxMs }
            });
        }

        const ml = health?.ml ?? {};
        const liveImage = ml?.live_image ?? {};
        const liveImagePressure = normalizeString(liveImage?.pressure_level, '').toLowerCase();
        if (liveImagePressure === 'high' || liveImagePressure === 'critical') {
            this.recordError({
                source: 'health',
                component: 'ml_live_image',
                stage: 'admission',
                reasonCode: `pressure_${liveImagePressure}`,
                message: `Live image classifier pressure is ${liveImagePressure}`,
                severity: liveImagePressure === 'critical' ? 'critical' : 'error',
                timestamp: ts,
                healthSnapshotId: snapshotId,
                context: {
                    in_flight: Math.floor(asFiniteNumber(liveImage?.in_flight)),
                    queued: Math.floor(asFiniteNumber(liveImage?.queued)),
                    max_concurrent: Math.floor(asFiniteNumber(liveImage?.max_concurrent))
                }
            });
        }

        if (Boolean(liveImage?.recovery_active)) {
            const recoveryReason = normalizeString(liveImage?.recovery_reason, '');
            const recoveryMessage = recoveryReason === 'worker_circuit_open'
                ? 'Live image classifier is recovering worker processes'
                : 'Live image classifier is reclaiming stale work';
            this.recordError({
                source: 'health',
                component: 'ml_live_image',
                stage: 'admission',
                reasonCode: 'recovery_active',
                message: recoveryMessage,
                severity: 'critical',
                timestamp: ts,
                healthSnapshotId: snapshotId,
                context: {
                    recovery_reason: recoveryReason || null,
                    abandoned: Math.floor(asFiniteNumber(liveImage?.abandoned)),
                    recent_abandoned: Math.floor(asFiniteNumber(liveImage?.recent_abandoned)),
                    late_completions_ignored: Math.floor(asFiniteNumber(liveImage?.late_completions_ignored))
                }
            });
        }

        const backgroundImage = ml?.background_image ?? {};
        if (Boolean(backgroundImage?.background_throttled) && Math.floor(asFiniteNumber(backgroundImage?.queued)) > 0) {
            this.recordError({
                source: 'health',
                component: 'ml_background_image',
                stage: 'admission',
                reasonCode: 'throttled_by_live_pressure',
                message: 'Background image classification is throttled by live detections',
                severity: 'warning',
                timestamp: ts,
                healthSnapshotId: snapshotId,
                context: {
                    queued: Math.floor(asFiniteNumber(backgroundImage?.queued)),
                    in_flight: Math.floor(asFiniteNumber(backgroundImage?.in_flight))
                }
            });
        }

        const workerPools = ml?.worker_pools ?? health?.worker_pools ?? {};
        const liveWorkerPool = normalizeWorkerPoolState(workerPools?.live);
        if (Boolean(liveWorkerPool.circuit_open)) {
            this.recordError({
                source: 'health',
                component: 'ml_worker_live',
                stage: 'supervisor',
                reasonCode: 'circuit_open',
                message: 'Live classifier workers are recovering under circuit breaker',
                severity: 'critical',
                timestamp: ts,
                healthSnapshotId: snapshotId,
                context: {
                    workers: Math.floor(asFiniteNumber(liveWorkerPool.workers)),
                    restarts: Math.floor(asFiniteNumber(liveWorkerPool.restarts)),
                    last_exit_reason: normalizeString(liveWorkerPool.last_exit_reason, '') || null
                }
            });
        }

        const backgroundWorkerPool = normalizeWorkerPoolState(workerPools?.background);
        if (Boolean(backgroundWorkerPool.circuit_open)) {
            this.recordError({
                source: 'health',
                component: 'ml_worker_background',
                stage: 'supervisor',
                reasonCode: 'circuit_open',
                message: 'Background classifier workers are paused by circuit breaker',
                severity: 'warning',
                timestamp: ts,
                healthSnapshotId: snapshotId,
                context: {
                    workers: Math.floor(asFiniteNumber(backgroundWorkerPool.workers)),
                    restarts: Math.floor(asFiniteNumber(backgroundWorkerPool.restarts)),
                    last_exit_reason: normalizeString(backgroundWorkerPool.last_exit_reason, '') || null
                }
            });
        }

        const lateResultsIgnored = Math.max(0, Math.floor(asFiniteNumber(workerPools?.late_results_ignored)));
        if (lateResultsIgnored > 0) {
            this.recordError({
                source: 'health',
                component: 'ml_worker_supervisor',
                stage: 'supervisor',
                reasonCode: 'late_results_ignored',
                message: `Classifier supervisor ignored ${lateResultsIgnored} stale worker result(s)`,
                severity: 'warning',
                timestamp: ts,
                healthSnapshotId: snapshotId,
                context: { late_results_ignored: lateResultsIgnored }
            });
        }

        const startupWarnings = Array.isArray(health?.startup_warnings) ? health.startup_warnings : [];
        for (const warning of startupWarnings.slice(0, 20)) {
            const phase = normalizeString(warning?.phase, 'unknown_phase');
            this.recordError({
                source: 'health',
                component: 'startup',
                stage: phase,
                reasonCode: 'startup_warning',
                message: normalizeString(warning?.error, 'Startup warning'),
                severity: 'warning',
                timestamp: ts,
                healthSnapshotId: snapshotId,
                context: { phase }
            });
        }
    }

    clear(): void {
        this.groups = [];
        this.healthSnapshots = [];
        this.snapshotCounter = 0;
        this.persist();
    }

    clearBundles(): void {
        this.bundles = [];
        this.bundleCounter = 0;
        this.persist();
    }

    removeBundle(bundleId: string): void {
        const id = normalizeString(bundleId);
        if (!id) return;
        const next = this.bundles.filter((bundle) => bundle.id !== id);
        if (next.length === this.bundles.length) return;
        this.bundles = next;
        this.persist();
    }

    exportJson(options: DiagnosticsExportOptions = {}): Record<string, unknown> {
        return this.buildExportPayload(this.groups, this.healthSnapshots, options);
    }

    captureBundle(
        label?: string,
        notes?: string,
        options: DiagnosticsExportOptions = {}
    ): JobDiagnosticBundle | null {
        if (this.groups.length <= 0 && this.healthSnapshots.length <= 0) return null;
        const id = `bundle:${Date.now()}:${this.bundleCounter++}`;
        const fallbackLabel = `Bundle ${this.bundles.length + 1}`;
        const resolvedLabel = normalizeString(label, fallbackLabel);
        const payload = this.buildExportPayload(
            this.groups,
            this.healthSnapshots.slice(0, MAX_BUNDLE_HEALTH_SNAPSHOTS),
            {
                ...options,
                reportNotes: normalizeString(notes, '')
            }
        );
        payload.report = {
            label: resolvedLabel,
            notes: normalizeString(notes, ''),
            generated_at: payload.generated_at,
            schema_version: payload.schema_version
        };
        const summary = payload.summary as {
            error_groups: number;
            total_events: number;
            health_snapshots: number;
        };
        const bundle: JobDiagnosticBundle = {
            id,
            label: resolvedLabel,
            createdAt: Date.now(),
            summary,
            payload
        };
        this.bundles = [bundle, ...this.bundles].slice(0, MAX_BUNDLES);
        this.persist();
        return bundle;
    }

    downloadBundle(bundleId: string): void {
        const id = normalizeString(bundleId);
        if (!id || typeof window === 'undefined' || typeof document === 'undefined') return;
        const bundle = this.bundles.find((item) => item.id === id);
        if (!bundle) return;
        const safeLabel = bundle.label
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, '-')
            .replace(/^-+|-+$/g, '')
            .slice(0, 50) || 'bundle';
        const filename = `yawamf-job-diagnostics-${safeLabel}-${new Date(bundle.createdAt).toISOString().slice(0, 19).replace(/[:T]/g, '-')}.json`;
        this.downloadPayload(bundle.payload, filename);
    }

    private buildExportPayload(
        groups: JobDiagnosticGroup[],
        healthSnapshots: JobDiagnosticHealthSnapshot[],
        options: DiagnosticsExportOptions = {}
    ): Record<string, unknown> {
        const workspacePayload = options.workspacePayload;
        const totalEvents = groups.reduce((sum, group) => sum + group.count, 0);
        const firstSeen = groups.reduce((min, group) => Math.min(min, group.firstSeen), Number.POSITIVE_INFINITY);
        const lastSeen = groups.reduce((max, group) => Math.max(max, group.lastSeen), 0);
        const normalizedGroups = groups.map((group) => ({
            ...group,
            firstSeenISO: new Date(group.firstSeen).toISOString(),
            lastSeenISO: new Date(group.lastSeen).toISOString()
        }));
        const normalizedHealthSnapshots = healthSnapshots.map((snapshot) => ({
            ...snapshot,
            timestampISO: new Date(snapshot.timestamp).toISOString()
        }));
        const normalizedBackendDiagnostics = workspacePayload?.backend_diagnostics
            ? {
                ...workspacePayload.backend_diagnostics,
                events: Array.isArray(workspacePayload.backend_diagnostics.events)
                    ? workspacePayload.backend_diagnostics.events.map((event) => ({ ...event }))
                    : []
            }
            : undefined;
        const focusedDiagnostics = workspacePayload?.focused_diagnostics
            ? cloneJson(workspacePayload.focused_diagnostics)
            : undefined;
        const workspaceSnapshot = workspacePayload ? cloneJson(workspacePayload) : null;
        const classifier = workspacePayload?.classifier ? cloneJson(workspacePayload.classifier) : null;
        const startupWarnings = Array.isArray(workspacePayload?.startup_warnings)
            ? cloneJson(workspacePayload.startup_warnings)
            : [];
        const currentIssues = Array.isArray(options.currentIssues) ? cloneJson(options.currentIssues) : [];
        const recentIncidents = Array.isArray(options.recentIncidents) ? cloneJson(options.recentIncidents) : [];
        const clientContext = collectClientContext();
        return {
            schema_version: 3,
            generated_at: new Date().toISOString(),
            workspace_schema_version: workspacePayload?.workspace_schema_version ?? null,
            environment: {
                app_version: typeof __APP_VERSION__ === 'string' ? __APP_VERSION__ : 'unknown',
                git_hash: typeof __GIT_HASH__ === 'string' ? __GIT_HASH__ : 'unknown',
                branch: typeof __APP_BRANCH__ === 'string' ? __APP_BRANCH__ : 'unknown'
            },
            app: {
                version: typeof __APP_VERSION__ === 'string' ? __APP_VERSION__ : 'unknown',
                git_hash: typeof __GIT_HASH__ === 'string' ? __GIT_HASH__ : 'unknown',
                branch: typeof __APP_BRANCH__ === 'string' ? __APP_BRANCH__ : 'unknown'
            },
            client_context: clientContext,
            summary: {
                error_groups: groups.length,
                total_events: totalEvents,
                health_snapshots: healthSnapshots.length,
                first_seen: Number.isFinite(firstSeen) ? new Date(firstSeen).toISOString() : null,
                last_seen: lastSeen > 0 ? new Date(lastSeen).toISOString() : null
            },
            workspace_snapshot: workspaceSnapshot,
            health: workspacePayload?.health ?? normalizedHealthSnapshots[0] ?? null,
            classifier,
            startup_warnings: startupWarnings,
            backend_diagnostics: normalizedBackendDiagnostics ?? null,
            focused_diagnostics: focusedDiagnostics ?? null,
            incidents: {
                current: currentIssues,
                recent: recentIncidents,
            },
            timeline: [],
            raw_evidence: {
                error_groups: normalizedGroups,
                health_snapshots: normalizedHealthSnapshots,
                backend_diagnostics: normalizedBackendDiagnostics,
                workspace_snapshot: workspaceSnapshot,
                classifier,
                startup_warnings: startupWarnings,
                incidents: {
                    current: currentIssues,
                    recent: recentIncidents,
                },
                client_context: clientContext,
            },
            error_groups: normalizedGroups,
            health_snapshots: normalizedHealthSnapshots
        };
    }

    downloadJson(
        filename = `yawamf-job-diagnostics-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.json`,
        options: DiagnosticsExportOptions = {}
    ): void {
        const payload = this.exportJson(options);
        this.downloadPayload(payload, filename);
    }

    private downloadPayload(payload: Record<string, unknown>, filename: string): void {
        if (typeof window === 'undefined' || typeof document === 'undefined') return;
        const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = url;
        anchor.download = filename;
        document.body.appendChild(anchor);
        anchor.click();
        document.body.removeChild(anchor);
        URL.revokeObjectURL(url);
    }

    private persist(): void {
        if (typeof window === 'undefined') return;
        if (this.persistTimer !== null) return;
        this.persistTimer = window.setTimeout(() => {
            this.persistTimer = null;
            try {
                const payload = JSON.stringify({
                    groups: this.groups.slice(0, MAX_GROUPS),
                    healthSnapshots: this.healthSnapshots.slice(0, MAX_HEALTH_SNAPSHOTS),
                    bundles: this.bundles.slice(0, MAX_BUNDLES)
                });
                window.localStorage.setItem(STORAGE_KEY, payload);
            } catch {
                // Ignore localStorage write errors.
            }
        }, 150);
    }

    private resolveHealthSnapshotId(input: JobDiagnosticRecordInput, timestamp: number): string | undefined {
        if (normalizeString(input.healthSnapshotId).length > 0) {
            return input.healthSnapshotId;
        }
        if (input.healthSnapshot !== undefined) {
            return this.recordHealthSnapshot(input.healthSnapshot, timestamp);
        }
        return undefined;
    }

    private recordHealthSnapshot(health: any, timestamp: number): string {
        const status = normalizeString(health?.status, 'unknown').toLowerCase();
        const signature = createHealthSignature(health);
        const latest = this.healthSnapshots[0];
        if (latest && latest.signature === signature) {
            return latest.id;
        }
        const id = `health:${timestamp}:${this.snapshotCounter++}`;
        const next: JobDiagnosticHealthSnapshot = {
            id,
            timestamp,
            status,
            signature,
            payload: sanitizeHealthSnapshotPayload(health)
        };
        this.healthSnapshots = [next, ...this.healthSnapshots].slice(0, MAX_HEALTH_SNAPSHOTS);
        this.persist();
        return id;
    }

    private mergeSampleEventIds(existing: string[], candidate: string | null): string[] {
        if (!candidate) return existing.slice(0, MAX_SAMPLE_EVENT_IDS);
        const next = [candidate, ...existing.filter((eventId) => eventId !== candidate)];
        return next.slice(0, MAX_SAMPLE_EVENT_IDS);
    }

    private recordStageCounters(
        reasonCode: 'stage_timeout' | 'stage_failure',
        counters: unknown,
        severity: JobDiagnosticSeverity,
        timestamp: number,
        healthSnapshotId: string
    ): void {
        if (!counters || typeof counters !== 'object') return;
        for (const [stage, rawCount] of Object.entries(counters as Record<string, unknown>)) {
            const count = Math.max(0, Math.floor(asFiniteNumber(rawCount)));
            if (count <= 0) continue;
            this.recordError({
                source: 'health',
                component: 'event_pipeline',
                stage,
                reasonCode,
                message: `Event pipeline ${stage} ${reasonCode === 'stage_timeout' ? 'timed out' : 'failed'} ${count} times`,
                severity,
                timestamp,
                healthSnapshotId,
                context: { count }
            });
        }
    }

    private recordLatestPipelineState(
        eventPipeline: any,
        timestamp: number,
        healthSnapshotId: string
    ): void {
        const lastTimeout = eventPipeline?.last_stage_timeout;
        if (lastTimeout && typeof lastTimeout === 'object') {
            const stage = normalizeString(lastTimeout.stage, 'unknown_stage');
            const timeoutSeconds = asFiniteNumber(lastTimeout.timeout_seconds);
            this.recordError({
                source: 'health',
                component: 'event_pipeline',
                stage,
                reasonCode: 'last_stage_timeout',
                message: `Latest timeout at ${stage}${timeoutSeconds > 0 ? ` (${timeoutSeconds}s)` : ''}`,
                severity: 'error',
                timestamp,
                eventId: normalizeEventId(lastTimeout.event_id) ?? undefined,
                healthSnapshotId,
                context: { timeout_seconds: timeoutSeconds }
            });
        }

        const lastFailure = eventPipeline?.last_stage_failure;
        if (lastFailure && typeof lastFailure === 'object') {
            const stage = normalizeString(lastFailure.stage, 'unknown_stage');
            const error = normalizeString(lastFailure.error, 'unknown_error');
            this.recordError({
                source: 'health',
                component: 'event_pipeline',
                stage,
                reasonCode: 'last_stage_failure',
                message: `Latest stage failure at ${stage}: ${error}`,
                severity: 'critical',
                timestamp,
                eventId: normalizeEventId(lastFailure.event_id) ?? undefined,
                healthSnapshotId,
                context: { error }
            });
        }

        const lastDrop = eventPipeline?.last_drop;
        if (lastDrop && typeof lastDrop === 'object') {
            const reason = normalizeString(lastDrop.reason, 'unknown_reason');
            const stage = normalizeString(lastDrop.stage);
            this.recordError({
                source: 'health',
                component: 'event_pipeline',
                stage: stage || undefined,
                reasonCode: `last_drop_${reason}`,
                message: `Latest dropped event reason: ${reason}`,
                severity: 'warning',
                timestamp,
                eventId: normalizeEventId(lastDrop.event_id) ?? undefined,
                healthSnapshotId,
                context: { reason }
            });
        }
    }
}

export const jobDiagnosticsStore = new JobDiagnosticsStore();
