import type { BackendDiagnosticEvent, DiagnosticsWorkspacePayload } from '../api/diagnostics';
import { fetchDiagnosticsWorkspace } from '../api/diagnostics';

export type IncidentStatus = 'open' | 'recovering' | 'resolved';
export type IncidentSeverity = 'warning' | 'error' | 'critical';

export interface IncidentJobState {
    id: string;
    kind?: string;
    status?: string;
    message?: string;
}

export interface IncidentRecord {
    id: string;
    status: IncidentStatus;
    severity: IncidentSeverity;
    title: string;
    summary: string;
    affected_area: string;
    startedAt: number;
    lastSeenAt: number;
    evidenceRefs: string[];
    primaryReasonCode: string;
}

export interface IncidentIssueDraft {
    title: string;
    body: string;
    bundleSchemaVersion: number | null;
}

export interface LocalDiagnosticGroup {
    fingerprint: string;
    source?: string;
    component: string;
    reasonCode: string;
    severity: 'warning' | 'error' | 'critical';
    message: string;
    firstSeen: number;
    lastSeen: number;
}

function localGroupsEqual(a: LocalDiagnosticGroup[], b: LocalDiagnosticGroup[]): boolean {
    if (a === b) return true;
    if (a.length !== b.length) return false;
    for (let index = 0; index < a.length; index += 1) {
        const left = a[index];
        const right = b[index];
        if (
            left.fingerprint !== right.fingerprint
            || normalizeString(left.source) !== normalizeString(right.source)
            || left.component !== right.component
            || left.reasonCode !== right.reasonCode
            || left.severity !== right.severity
            || left.message !== right.message
            || left.firstSeen !== right.firstSeen
            || left.lastSeen !== right.lastSeen
        ) {
            return false;
        }
    }
    return true;
}

function backendEventsEqual(a: BackendDiagnosticEvent[], b: BackendDiagnosticEvent[]): boolean {
    if (a === b) return true;
    if (a.length !== b.length) return false;
    for (let index = 0; index < a.length; index += 1) {
        const left = a[index];
        const right = b[index];
        if (
            left.id !== right.id
            || left.timestamp !== right.timestamp
            || left.component !== right.component
            || left.reason_code !== right.reason_code
            || left.severity !== right.severity
            || left.message !== right.message
            || normalizeString(left.job_id) !== normalizeString(right.job_id)
            || normalizeString(left.correlation_key) !== normalizeString(right.correlation_key)
        ) {
            return false;
        }
    }
    return true;
}

function toTimestamp(value: string | number | undefined | null): number {
    if (typeof value === 'number' && Number.isFinite(value)) return value;
    if (typeof value === 'string') {
        const parsed = Date.parse(value);
        if (Number.isFinite(parsed)) return parsed;
    }
    return Date.now();
}

function normalizeString(value: unknown, fallback = ''): string {
    if (typeof value !== 'string') return fallback;
    const trimmed = value.trim();
    return trimmed.length > 0 ? trimmed : fallback;
}

function normalizeSeverity(value: unknown): IncidentSeverity {
    const severity = normalizeString(value, 'warning').toLowerCase();
    if (severity === 'critical' || severity === 'error' || severity === 'warning') {
        return severity;
    }
    return 'warning';
}

function severityRank(value: IncidentSeverity): number {
    if (value === 'critical') return 3;
    if (value === 'error') return 2;
    return 1;
}

function inferAffectedArea(event: BackendDiagnosticEvent, job?: IncidentJobState): string {
    const jobKind = normalizeString(job?.kind).toLowerCase();
    if (jobKind.includes('backfill')) return 'backfill';
    if (jobKind.includes('video')) return 'video';
    const component = normalizeString(event.component).toLowerCase();
    if (component.includes('frontend')) return 'frontend';
    if (component.includes('notification')) return 'notifications';
    if (component.includes('video')) return 'video';
    if (component.includes('classifier') || component.includes('event_processor')) return 'live_detection';
    return component || 'system';
}

function buildIncidentKey(event: BackendDiagnosticEvent): string {
    const jobId = normalizeString(event.job_id);
    if (jobId) return `job:${jobId}`;
    const correlationKey = normalizeString(event.correlation_key);
    if (correlationKey) return correlationKey;
    return `${normalizeString(event.component, 'unknown')}:${normalizeString(event.reason_code, 'unknown_reason')}`;
}

function deriveStatus(job?: IncidentJobState): IncidentStatus {
    const status = normalizeString(job?.status).toLowerCase();
    if (status === 'completed' || status === 'succeeded' || status === 'success') return 'resolved';
    if (status === 'running' || status === 'processing') return 'recovering';
    return 'open';
}

function isStatefulIncidentOpen(component: string, reasonCode: string, health: Record<string, any> | null): boolean | null {
    const normalizedComponent = normalizeString(component).toLowerCase();
    const normalizedReason = normalizeString(reasonCode).toLowerCase();
    const currentHealth = health ?? {};
    const ml = currentHealth.ml ?? {};
    const workerPools = ml.worker_pools ?? currentHealth.worker_pools ?? {};

    if (
        (normalizedComponent === 'video_classifier' && normalizedReason === 'circuit_open')
        || (normalizedComponent === 'auto_video_classifier'
            && (normalizedReason === 'video_circuit_open' || normalizedReason === 'video_circuit_opened'))
    ) {
        return Boolean(currentHealth.video_classifier?.circuit_open);
    }

    if (normalizedComponent === 'ml_live_image' && normalizedReason === 'recovery_active') {
        return Boolean(ml.live_image?.recovery_active);
    }

    if (normalizedComponent === 'ml_background_image' && normalizedReason === 'throttled_by_live_pressure') {
        return Boolean(ml.background_image?.background_throttled)
            && Number(ml.background_image?.queued ?? 0) > 0;
    }

    if (normalizedComponent === 'ml_worker_live' && normalizedReason === 'circuit_open') {
        return Boolean(workerPools.live?.circuit_open);
    }

    if (normalizedComponent === 'ml_worker_background' && normalizedReason === 'circuit_open') {
        return Boolean(workerPools.background?.circuit_open);
    }

    return null;
}

function deriveEventStatus(
    component: string,
    reasonCode: string,
    health: Record<string, any> | null,
    job?: IncidentJobState
): IncidentStatus {
    const statefulOpen = isStatefulIncidentOpen(component, reasonCode, health);
    if (statefulOpen === true) return 'open';
    if (statefulOpen === false) return 'resolved';
    return deriveStatus(job);
}

class IncidentWorkspaceStore {
    currentIssues = $state<IncidentRecord[]>([]);
    recentIncidents = $state<IncidentRecord[]>([]);
    workspacePayload = $state<DiagnosticsWorkspacePayload | null>(null);
    backendEvents = $state<BackendDiagnosticEvent[]>([]);
    localGroups = $state<LocalDiagnosticGroup[]>([]);

    private jobs = new Map<string, IncidentJobState>();

    ingestWorkspacePayload(payload: DiagnosticsWorkspacePayload): void {
        this.workspacePayload = payload;
        const nextEvents = payload.backend_diagnostics?.events ?? [];
        const eventsChanged = !backendEventsEqual(this.backendEvents, nextEvents);
        this.ingestBackendDiagnostics(nextEvents);
        if (!eventsChanged) {
            this.recompute();
        }
    }

    async refresh(limit = 200): Promise<void> {
        const payload = await fetchDiagnosticsWorkspace(limit);
        this.ingestWorkspacePayload(payload);
    }

    ingestBackendDiagnostics(events: BackendDiagnosticEvent[]): void {
        const nextEvents = Array.isArray(events) ? [...events] : [];
        if (backendEventsEqual(this.backendEvents, nextEvents)) {
            return;
        }
        this.backendEvents = nextEvents;
        this.recompute();
    }

    ingestJobState(job: IncidentJobState): void {
        const id = normalizeString(job.id);
        if (!id) return;
        this.jobs.set(id, { ...job, id });
        this.recompute();
    }

    ingestLocalDiagnosticGroups(groups: LocalDiagnosticGroup[]): void {
        const nextGroups = Array.isArray(groups) ? [...groups] : [];
        if (localGroupsEqual(this.localGroups, nextGroups)) {
            return;
        }
        this.localGroups = nextGroups;
        this.recompute();
    }

    buildIssueDraft(
        incident: IncidentRecord | null | undefined,
        options?: {
            bundleLabel?: string;
            bundleSchemaVersion?: number | null;
            reportNotes?: string;
        }
    ): IncidentIssueDraft {
        const selected = incident ?? this.currentIssues[0] ?? this.recentIncidents[0] ?? null;
        const health = this.workspacePayload?.health ?? {};
        const healthStatus = normalizeString(health.status, 'unknown');
        const service = normalizeString(health.service, 'ya-wamf-backend');
        const version = normalizeString(health.version, 'unknown');
        const bundleLabel = normalizeString(options?.bundleLabel, '');
        const reportNotes = normalizeString(options?.reportNotes, '');
        const title = selected
            ? `[incident] ${selected.title}`
            : '[incident] Diagnostics workspace report';
        const body = [
            'Environment',
            `- Service: ${service}`,
            `- Version: ${version}`,
            `- Health: ${healthStatus}`,
            bundleLabel ? `- Bundle: ${bundleLabel}` : null,
            '',
            'Incident Summary',
            selected ? `- Title: ${selected.title}` : '- Title: Unknown incident',
            selected ? `- Area: ${selected.affected_area}` : '- Area: unknown',
            selected ? `- Status: ${selected.status}` : '- Status: unknown',
            selected ? `- Severity: ${selected.severity}` : '- Severity: unknown',
            selected ? `- Reason: ${selected.primaryReasonCode}` : '- Reason: unknown',
            selected ? `- Evidence: ${selected.evidenceRefs.join(', ') || 'none'}` : '- Evidence: none',
            reportNotes ? `- Notes: ${reportNotes}` : null,
            '',
            selected?.summary ?? 'No incident summary available.'
        ].filter((line): line is string => Boolean(line)).join('\n');

        return {
            title,
            body,
            bundleSchemaVersion: options?.bundleSchemaVersion ?? null
        };
    }

    private recompute(): void {
        const grouped = new Map<string, IncidentRecord>();
        const currentHealth = this.workspacePayload?.health && typeof this.workspacePayload.health === 'object'
            ? (this.workspacePayload.health as Record<string, any>)
            : null;

        for (const event of this.backendEvents) {
            const key = buildIncidentKey(event);
            const jobId = normalizeString(event.job_id);
            const job = jobId ? this.jobs.get(jobId) : undefined;
            const timestamp = toTimestamp(event.timestamp);
            const severity = normalizeSeverity(event.severity);
            const title = normalizeString(event.message, normalizeString(event.reason_code, 'Incident'));
            const summary = normalizeString(job?.message, normalizeString(event.message, 'Incident detected'));
            const evidenceRefs = [normalizeString(event.id)].filter(Boolean);
            if (jobId) evidenceRefs.push(`job:${jobId}`);
            const existing = grouped.get(key);
            if (!existing) {
                grouped.set(key, {
                    id: key,
                    status: deriveEventStatus(event.component, event.reason_code, currentHealth, job),
                    severity,
                    title,
                    summary,
                    affected_area: inferAffectedArea(event, job),
                    startedAt: timestamp,
                    lastSeenAt: timestamp,
                    evidenceRefs,
                    primaryReasonCode: normalizeString(event.reason_code, 'unknown_reason')
                });
                continue;
            }

            existing.status = deriveEventStatus(event.component, event.reason_code, currentHealth, job);
            if (severityRank(severity) > severityRank(existing.severity)) {
                existing.severity = severity;
            }
            existing.summary = summary;
            existing.title = title;
            existing.lastSeenAt = Math.max(existing.lastSeenAt, timestamp);
            existing.startedAt = Math.min(existing.startedAt, timestamp);
            existing.affected_area = inferAffectedArea(event, job);
            existing.primaryReasonCode = normalizeString(event.reason_code, existing.primaryReasonCode);
            for (const ref of evidenceRefs) {
                if (ref && !existing.evidenceRefs.includes(ref)) {
                    existing.evidenceRefs.push(ref);
                }
            }
        }

        const incidents = [...grouped.values()].sort((a, b) => b.lastSeenAt - a.lastSeenAt);
        for (const group of this.localGroups) {
            const key = `local:${normalizeString(group.fingerprint, 'unknown')}`;
            if (grouped.has(key)) continue;
            const statefulOpen = isStatefulIncidentOpen(group.component, group.reasonCode, currentHealth);
            incidents.push({
                id: key,
                status: statefulOpen === false ? 'resolved' : 'open',
                severity: normalizeSeverity(group.severity),
                title: normalizeString(group.message, normalizeString(group.reasonCode, 'Incident')),
                summary: normalizeString(group.message, 'Incident detected'),
                affected_area: normalizeString(group.component, 'system').toLowerCase(),
                startedAt: Math.max(0, Math.floor(group.firstSeen)),
                lastSeenAt: Math.max(0, Math.floor(group.lastSeen)),
                evidenceRefs: [key],
                primaryReasonCode: normalizeString(group.reasonCode, 'unknown_reason')
            });
        }
        incidents.sort((a, b) => b.lastSeenAt - a.lastSeenAt);
        this.currentIssues = incidents.filter((incident) => incident.status !== 'resolved');
        this.recentIncidents = incidents.filter((incident) => incident.status === 'resolved').slice(0, 20);
    }
}

export function createIncidentWorkspaceStore(): IncidentWorkspaceStore {
    return new IncidentWorkspaceStore();
}

export const incidentWorkspaceStore = createIncidentWorkspaceStore();
