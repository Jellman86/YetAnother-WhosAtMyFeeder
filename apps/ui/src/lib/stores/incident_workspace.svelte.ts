import type { BackendDiagnosticEvent, DiagnosticDismissalEntry, DiagnosticsWorkspacePayload } from '../api/diagnostics';
import { mapGuarded, type Guarded } from '../api/core';
import { clearDiagnosticsWorkspace, dismissDiagnostics, fetchDiagnosticsWorkspace, restoreDiagnostics } from '../api/diagnostics';
import { STATEFUL_INCIDENTS, readSignal } from './incident-signals';
import { INITIAL_READ, readFreshness, settleRead, type ReadSettled } from '../utils/read-freshness';

type IncidentStatus = 'open' | 'recovering' | 'resolved';
type IncidentSeverity = 'warning' | 'error' | 'critical';

interface IncidentJobState {
    id: string;
    kind?: string;
    status?: string;
    message?: string;
}

interface IncidentRecord {
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
    /** Open because a live check says so now, so it can be neither dismissed nor hidden. */
    live: boolean;
    /** Every backend entry it is built from is dismissed, up to the occurrence the owner saw. */
    dismissed: boolean;
}

interface DismissalApi {
    dismiss: typeof dismissDiagnostics;
    restore: typeof restoreDiagnostics;
}

interface IncidentIssueDraft {
    title: string;
    body: string;
    bundleSchemaVersion: number | null;
}

interface LocalDiagnosticGroup {
    fingerprint: string;
    source?: string;
    component: string;
    reasonCode: string;
    severity: 'warning' | 'error' | 'critical';
    message: string;
    firstSeen: number;
    lastSeen: number;
}

interface IncidentDiagnosticGroup {
    fingerprint: string;
    source: 'backend' | 'local';
    component: string;
    reasonCode: string;
    severity: IncidentSeverity;
    message: string;
    count: number;
    firstSeen: number;
    lastSeen: number;
}

function asRecord(value: unknown): Record<string, unknown> {
    return value && typeof value === 'object' ? value as Record<string, unknown> : {};
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
            || left.dismissed !== right.dismissed
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

function isIncidentSeverity(value: unknown): boolean {
    const severity = normalizeString(value).toLowerCase();
    return severity === 'critical' || severity === 'error' || severity === 'warning';
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

function isStatefulIncidentOpen(
    component: string,
    reasonCode: string,
    health: Record<string, unknown> | null
): boolean | null {
    const normalizedComponent = normalizeString(component).toLowerCase();
    const normalizedReason = normalizeString(reasonCode).toLowerCase();
    const incident = STATEFUL_INCIDENTS.find(
        (candidate) => candidate.component === normalizedComponent && candidate.reasons.includes(normalizedReason)
    );
    return incident ? incident.isOpen((path) => readSignal(health, path)) : null;
}

function deriveEventStatus(
    component: string,
    reasonCode: string,
    health: Record<string, unknown> | null,
    job?: IncidentJobState
): IncidentStatus {
    const statefulOpen = isStatefulIncidentOpen(component, reasonCode, health);
    if (statefulOpen === true) return 'open';
    if (statefulOpen === false) return 'resolved';
    return deriveStatus(job);
}

class IncidentWorkspaceStore {
    /** Open and not dismissed: what Health and the sidebar count. */
    currentIssues = $state<IncidentRecord[]>([]);
    /** Resolved and not dismissed. */
    recentIncidents = $state<IncidentRecord[]>([]);
    /** Hidden by the owner, open or resolved, newest first; kept for Show dismissed and the export. */
    dismissedIncidents = $state<IncidentRecord[]>([]);
    workspacePayload = $state<DiagnosticsWorkspacePayload | null>(null);
    /** How current the workspace is, changed only when a read settles (whoever started it). */
    readSettled = $state<ReadSettled>(INITIAL_READ);
    readFreshness = $derived(readFreshness(this.workspacePayload !== null, this.readSettled));
    backendEvents = $state<BackendDiagnosticEvent[]>([]);
    localGroups = $state<LocalDiagnosticGroup[]>([]);

    private jobs = new Map<string, IncidentJobState>();
    private refreshGeneration = 0;
    /** Reads up to this generation were made before the last clear. */
    private clearedThrough = 0;

    constructor(
        private readonly fetchWorkspace: typeof fetchDiagnosticsWorkspace = fetchDiagnosticsWorkspace,
        private readonly dismissals: DismissalApi = { dismiss: dismissDiagnostics, restore: restoreDiagnostics }
    ) {}

    ingestWorkspacePayload(payload: DiagnosticsWorkspacePayload): void {
        this.workspacePayload = payload;
        const nextEvents = payload.backend_diagnostics?.events ?? [];
        const eventsChanged = !backendEventsEqual(this.backendEvents, nextEvents);
        this.ingestBackendDiagnostics(nextEvents);
        if (!eventsChanged) {
            this.recompute();
        }
    }

    /**
     * Read the workspace. Resolves true when this reading was applied and false when a newer read
     * started meanwhile, so a slow, older answer never replaces a newer one.
     */
    refresh(limit = 200, signal?: AbortSignal): Guarded<boolean> {
        const generation = ++this.refreshGeneration;
        return mapGuarded(
            this.fetchWorkspace(limit, signal),
            (payload) => {
                if (generation !== this.refreshGeneration) return false;
                this.ingestWorkspacePayload(payload);
                this.readSettled = settleRead(this.readSettled, generation, { ok: true, at: Date.now() });
                return true;
            },
            (error) => {
                // A read made before the workspace was cleared (another session's) says nothing now.
                if (generation <= this.clearedThrough) return false;
                const message = error instanceof Error && error.message ? error.message : String(error);
                this.readSettled = settleRead(this.readSettled, generation, { ok: false, error: message });
                throw error;
            }
        );
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

    clear(): void {
        // A read still in flight was made for whoever was signed in before; it must not land now.
        this.clearedThrough = this.refreshGeneration;
        this.refreshGeneration += 1;
        this.workspacePayload = null;
        // Nothing is read now, so nothing is failed either; late answers to older reads stay ignored.
        this.readSettled = { ...INITIAL_READ, token: this.readSettled.token };
        this.backendEvents = [];
        this.localGroups = [];
        this.jobs.clear();
        this.currentIssues = [];
        this.recentIncidents = [];
        this.dismissedIncidents = [];
    }

    async clearRemote(): Promise<void> {
        await clearDiagnosticsWorkspace();
        this.clear();
    }

    /** Hide entries for everyone on this install, then read the workspace that now says so. */
    async dismissRemote(entries: DiagnosticDismissalEntry[]): Promise<void> {
        if (entries.length === 0) return;
        await this.dismissals.dismiss(entries);
        await this.refresh();
    }

    async restoreRemote(ids: string[]): Promise<void> {
        if (ids.length === 0) return;
        await this.dismissals.restore(ids);
        await this.refresh();
    }

    /** The backend entries an incident is built from, each with the newest occurrence the page showed. */
    dismissalEntries(incident: IncidentRecord): DiagnosticDismissalEntry[] {
        const refs = new Set(incident.evidenceRefs);
        return this.backendEvents
            .filter((event) => refs.has(normalizeString(event.id)))
            .map((event) => ({ id: event.id, last_seen: event.last_seen ?? event.timestamp }));
    }

    /** Every incident for a diagnostics bundle, dismissed ones included and marked. */
    exportIncidents(): { current: IncidentRecord[]; recent: IncidentRecord[] } {
        const dismissedOpen = this.dismissedIncidents.filter((incident) => incident.status !== 'resolved');
        const dismissedResolved = this.dismissedIncidents.filter((incident) => incident.status === 'resolved');
        return {
            current: [...this.currentIssues, ...dismissedOpen],
            recent: [...this.recentIncidents, ...dismissedResolved]
        };
    }

    getDiagnosticGroups(incident: IncidentRecord | null | undefined): IncidentDiagnosticGroup[] {
        if (!incident) return [];
        const evidenceRefs = new Set(incident.evidenceRefs);
        const grouped = new Map<string, IncidentDiagnosticGroup>();

        for (const event of this.backendEvents) {
            if (!evidenceRefs.has(normalizeString(event.id))) continue;
            const key = `backend:${normalizeString(event.component, 'unknown')}:${normalizeString(event.reason_code, 'unknown_reason')}`;
            const timestamp = toTimestamp(event.timestamp);
            const severity = normalizeSeverity(event.severity);
            const message = normalizeString(event.message, normalizeString(event.reason_code, 'Incident'));
            const existing = grouped.get(key);
            if (!existing) {
                grouped.set(key, {
                    fingerprint: key,
                    source: 'backend',
                    component: normalizeString(event.component, 'unknown'),
                    reasonCode: normalizeString(event.reason_code, 'unknown_reason'),
                    severity,
                    message,
                    count: 1,
                    firstSeen: timestamp,
                    lastSeen: timestamp
                });
                continue;
            }
            existing.count += 1;
            existing.firstSeen = Math.min(existing.firstSeen, timestamp);
            existing.lastSeen = Math.max(existing.lastSeen, timestamp);
            existing.message = message;
            if (severityRank(severity) > severityRank(existing.severity)) {
                existing.severity = severity;
            }
        }

        for (const group of this.localGroups) {
            const key = `local:${normalizeString(group.fingerprint, 'unknown')}`;
            if (!evidenceRefs.has(key)) continue;
        }

        return [...grouped.values()].sort((left, right) => {
            const severityDiff = severityRank(right.severity) - severityRank(left.severity);
            if (severityDiff !== 0) return severityDiff;
            return right.lastSeen - left.lastSeen;
        });
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
        // An incident is hidden only while every entry it is built from is dismissed.
        const everyEntryDismissed = new Map<string, boolean>();
        const currentHealth = this.workspacePayload?.health && typeof this.workspacePayload.health === 'object'
            ? (this.workspacePayload.health as Record<string, unknown>)
            : null;

        for (const event of this.backendEvents) {
            if (!isIncidentSeverity(event.severity)) continue;
            const key = buildIncidentKey(event);
            const jobId = normalizeString(event.job_id);
            const job = jobId ? this.jobs.get(jobId) : undefined;
            const timestamp = toTimestamp(event.timestamp);
            const severity = normalizeSeverity(event.severity);
            const title = normalizeString(event.message, normalizeString(event.reason_code, 'Incident'));
            const summary = normalizeString(job?.message, normalizeString(event.message, 'Incident detected'));
            const evidenceRefs = [normalizeString(event.id)].filter(Boolean);
            if (jobId) evidenceRefs.push(`job:${jobId}`);
            everyEntryDismissed.set(key, (everyEntryDismissed.get(key) ?? true) && event.dismissed === true);
            const live = isStatefulIncidentOpen(event.component, event.reason_code, currentHealth) === true;
            const existing = grouped.get(key);
            if (!existing) {
                grouped.set(key, {
                    id: key,
                    live,
                    dismissed: false,
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
            existing.live = live;
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
        for (const incident of incidents) {
            // Dismissing never hides what a live check shows open now.
            incident.dismissed = !incident.live && everyEntryDismissed.get(incident.id) === true;
        }
        const shown = incidents.filter((incident) => !incident.dismissed);
        this.currentIssues = shown.filter((incident) => incident.status !== 'resolved');
        this.recentIncidents = shown.filter((incident) => incident.status === 'resolved').slice(0, 20);
        this.dismissedIncidents = incidents.filter((incident) => incident.dismissed);
    }
}

export function createIncidentWorkspaceStore(
    fetchWorkspace?: typeof fetchDiagnosticsWorkspace,
    dismissals?: DismissalApi
): IncidentWorkspaceStore {
    return new IncidentWorkspaceStore(fetchWorkspace, dismissals);
}

export const incidentWorkspaceStore = createIncidentWorkspaceStore();
