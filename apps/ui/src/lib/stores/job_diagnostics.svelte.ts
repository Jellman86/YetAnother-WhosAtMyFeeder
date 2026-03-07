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

function sumCounterMap(counters: unknown): number {
    if (!counters || typeof counters !== 'object') return 0;
    const values = Object.values(counters as Record<string, unknown>);
    let total = 0;
    for (const value of values) {
        total += Math.max(0, Math.floor(asFiniteNumber(value)));
    }
    return total;
}

function createHealthSignature(health: any): string {
    const status = normalizeString(health?.status, 'unknown').toLowerCase();
    const startupInstanceId = normalizeString(health?.startup_instance_id, 'unknown');
    const eventPipeline = health?.event_pipeline ?? {};
    const mqtt = health?.mqtt ?? {};
    const notificationDispatcher = health?.notification_dispatcher ?? {};
    const dbPool = health?.db_pool ?? {};
    const startupWarningCount = Array.isArray(health?.startup_warnings) ? health.startup_warnings.length : 0;
    const videoClassifier = health?.video_classifier ?? {};

    const eventCritical = Math.max(0, Math.floor(asFiniteNumber(eventPipeline?.critical_failures)));
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

    return [
        status,
        startupInstanceId,
        eventCritical,
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
        startupWarningCount
    ].join('|');
}

function sanitizeHealthSnapshotPayload(health: any): Record<string, unknown> {
    const eventPipeline = health?.event_pipeline ?? {};
    const mqtt = health?.mqtt ?? {};
    const notificationDispatcher = health?.notification_dispatcher ?? {};
    const dbPool = health?.db_pool ?? {};
    const ml = health?.ml ?? {};
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
            status: normalizeString(ml?.status, 'unknown')
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
        if (criticalFailures > 0) {
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

    exportJson(): Record<string, unknown> {
        return this.buildExportPayload(this.groups, this.healthSnapshots);
    }

    captureBundle(label?: string): JobDiagnosticBundle | null {
        if (this.groups.length <= 0 && this.healthSnapshots.length <= 0) return null;
        const id = `bundle:${Date.now()}:${this.bundleCounter++}`;
        const fallbackLabel = `Bundle ${this.bundles.length + 1}`;
        const resolvedLabel = normalizeString(label, fallbackLabel);
        const payload = this.buildExportPayload(
            this.groups,
            this.healthSnapshots.slice(0, MAX_BUNDLE_HEALTH_SNAPSHOTS)
        );
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
        healthSnapshots: JobDiagnosticHealthSnapshot[]
    ): Record<string, unknown> {
        const totalEvents = groups.reduce((sum, group) => sum + group.count, 0);
        const firstSeen = groups.reduce((min, group) => Math.min(min, group.firstSeen), Number.POSITIVE_INFINITY);
        const lastSeen = groups.reduce((max, group) => Math.max(max, group.lastSeen), 0);
        return {
            schema_version: 1,
            generated_at: new Date().toISOString(),
            app: {
                version: typeof __APP_VERSION__ === 'string' ? __APP_VERSION__ : 'unknown',
                git_hash: typeof __GIT_HASH__ === 'string' ? __GIT_HASH__ : 'unknown',
                branch: typeof __APP_BRANCH__ === 'string' ? __APP_BRANCH__ : 'unknown'
            },
            summary: {
                error_groups: groups.length,
                total_events: totalEvents,
                health_snapshots: healthSnapshots.length,
                first_seen: Number.isFinite(firstSeen) ? new Date(firstSeen).toISOString() : null,
                last_seen: lastSeen > 0 ? new Date(lastSeen).toISOString() : null
            },
            error_groups: groups.map((group) => ({
                ...group,
                firstSeenISO: new Date(group.firstSeen).toISOString(),
                lastSeenISO: new Date(group.lastSeen).toISOString()
            })),
            health_snapshots: healthSnapshots.map((snapshot) => ({
                ...snapshot,
                timestampISO: new Date(snapshot.timestamp).toISOString()
            }))
        };
    }

    downloadJson(filename = `yawamf-job-diagnostics-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.json`): void {
        const payload = this.exportJson();
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
