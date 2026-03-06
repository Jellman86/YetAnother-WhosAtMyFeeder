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

const MAX_GROUPS = 200;
const MAX_HEALTH_SNAPSHOTS = 80;
const MAX_SAMPLE_EVENT_IDS = 5;

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

function createHealthSignature(health: any): string {
    const status = normalizeString(health?.status, 'unknown').toLowerCase();
    const startupInstanceId = normalizeString(health?.startup_instance_id, 'unknown');
    const eventPipeline = health?.event_pipeline ?? {};
    const mqtt = health?.mqtt ?? {};
    const notificationDispatcher = health?.notification_dispatcher ?? {};
    const dbPool = health?.db_pool ?? {};
    const startupWarningCount = Array.isArray(health?.startup_warnings) ? health.startup_warnings.length : 0;

    const eventCritical = Math.max(0, Math.floor(asFiniteNumber(eventPipeline?.critical_failures)));
    const mqttPressure = normalizeString(mqtt?.pressure_level, 'unknown').toLowerCase();
    const droppedJobs = Math.max(0, Math.floor(asFiniteNumber(notificationDispatcher?.dropped_jobs)));
    const dbWaitMax = Math.max(0, Math.floor(asFiniteNumber(dbPool?.acquire_wait_max_ms)));

    return [
        status,
        startupInstanceId,
        eventCritical,
        mqttPressure,
        droppedJobs,
        dbWaitMax,
        startupWarningCount
    ].join('|');
}

class JobDiagnosticsStore {
    groups = $state<JobDiagnosticGroup[]>([]);
    healthSnapshots = $state<JobDiagnosticHealthSnapshot[]>([]);
    private snapshotCounter = 0;

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

        nextGroups.sort((a, b) => b.lastSeen - a.lastSeen);
        this.groups = nextGroups.slice(0, MAX_GROUPS);
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
    }

    exportJson(): Record<string, unknown> {
        const totalEvents = this.groups.reduce((sum, group) => sum + group.count, 0);
        const firstSeen = this.groups.reduce((min, group) => Math.min(min, group.firstSeen), Number.POSITIVE_INFINITY);
        const lastSeen = this.groups.reduce((max, group) => Math.max(max, group.lastSeen), 0);
        return {
            schema_version: 1,
            generated_at: new Date().toISOString(),
            summary: {
                error_groups: this.groups.length,
                total_events: totalEvents,
                health_snapshots: this.healthSnapshots.length,
                first_seen: Number.isFinite(firstSeen) ? new Date(firstSeen).toISOString() : null,
                last_seen: lastSeen > 0 ? new Date(lastSeen).toISOString() : null
            },
            error_groups: this.groups.map((group) => ({
                ...group,
                firstSeenISO: new Date(group.firstSeen).toISOString(),
                lastSeenISO: new Date(group.lastSeen).toISOString()
            })),
            health_snapshots: this.healthSnapshots.map((snapshot) => ({
                ...snapshot,
                timestampISO: new Date(snapshot.timestamp).toISOString()
            }))
        };
    }

    downloadJson(filename = `yawamf-job-diagnostics-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.json`): void {
        if (typeof window === 'undefined' || typeof document === 'undefined') return;
        const payload = this.exportJson();
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
            payload: health
        };
        this.healthSnapshots = [next, ...this.healthSnapshots].slice(0, MAX_HEALTH_SNAPSHOTS);
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
}

export const jobDiagnosticsStore = new JobDiagnosticsStore();
