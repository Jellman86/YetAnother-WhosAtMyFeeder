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

class IncidentWorkspaceStore {
    currentIssues = $state<IncidentRecord[]>([]);
    recentIncidents = $state<IncidentRecord[]>([]);
    workspacePayload = $state<DiagnosticsWorkspacePayload | null>(null);
    backendEvents = $state<BackendDiagnosticEvent[]>([]);

    private jobs = new Map<string, IncidentJobState>();

    ingestWorkspacePayload(payload: DiagnosticsWorkspacePayload): void {
        this.workspacePayload = payload;
        this.ingestBackendDiagnostics(payload.backend_diagnostics?.events ?? []);
    }

    async refresh(limit = 200): Promise<void> {
        const payload = await fetchDiagnosticsWorkspace(limit);
        this.ingestWorkspacePayload(payload);
    }

    ingestBackendDiagnostics(events: BackendDiagnosticEvent[]): void {
        this.backendEvents = Array.isArray(events) ? [...events] : [];
        this.recompute();
    }

    ingestJobState(job: IncidentJobState): void {
        const id = normalizeString(job.id);
        if (!id) return;
        this.jobs.set(id, { ...job, id });
        this.recompute();
    }

    private recompute(): void {
        const grouped = new Map<string, IncidentRecord>();

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
                    status: deriveStatus(job),
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

            existing.status = deriveStatus(job);
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
        this.currentIssues = incidents.filter((incident) => incident.status !== 'resolved');
        this.recentIncidents = incidents.filter((incident) => incident.status === 'resolved').slice(0, 20);
    }
}

export function createIncidentWorkspaceStore(): IncidentWorkspaceStore {
    return new IncidentWorkspaceStore();
}

export const incidentWorkspaceStore = createIncidentWorkspaceStore();
