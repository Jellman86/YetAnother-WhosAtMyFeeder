import { API_BASE, apiFetch, handleResponse } from './core';

export interface BackendDiagnosticEvent {
    id: string;
    source?: string;
    component: string;
    stage?: string | null;
    reason_code: string;
    message: string;
    severity: 'warning' | 'error' | 'critical';
    event_id?: string | null;
    context?: Record<string, unknown> | null;
    timestamp: string;
    correlation_key?: string | null;
    job_id?: string | null;
    worker_pool?: string | null;
    runtime_recovery?: Record<string, unknown> | null;
    snapshot_ref?: string | null;
}

export interface VideoClassifierFocusedDiagnostics {
    circuit_open: boolean;
    open_until?: string | null;
    failure_count: number;
    pending: number;
    active: number;
    latest_circuit_opened?: BackendDiagnosticEvent | null;
    likely_last_error?: string | null;
    candidate_failure_events?: BackendDiagnosticEvent[];
    recent_events?: BackendDiagnosticEvent[];
}

export interface DiagnosticsWorkspacePayload {
    workspace_schema_version: string;
    backend_diagnostics: {
        captured_at: string;
        capacity: number;
        total_events: number;
        filtered_events: number;
        returned_events: number;
        severity_counts: Record<string, number>;
        component_counts: Record<string, number>;
        events: BackendDiagnosticEvent[];
    };
    focused_diagnostics?: {
        video_classifier?: VideoClassifierFocusedDiagnostics;
    };
    health: Record<string, unknown>;
    classifier?: Record<string, unknown>;
    startup_warnings: Array<Record<string, unknown>>;
}

export interface DiagnosticsBundlePayload {
    schema_version: string;
    generated_at: string;
    summary: Record<string, unknown>;
    server: Record<string, unknown>;
    workspace: DiagnosticsWorkspacePayload;
    health: Record<string, unknown>;
    classifier: Record<string, unknown>;
    startup_warnings: Array<Record<string, unknown>>;
    backend_diagnostics: DiagnosticsWorkspacePayload['backend_diagnostics'];
    focused_diagnostics?: DiagnosticsWorkspacePayload['focused_diagnostics'];
}

export async function fetchDiagnosticsWorkspace(limit = 200): Promise<DiagnosticsWorkspacePayload> {
    const response = await apiFetch(`${API_BASE}/diagnostics/workspace?limit=${Math.max(1, Math.floor(limit))}`);
    return handleResponse<DiagnosticsWorkspacePayload>(response);
}

export interface ClearDiagnosticsWorkspaceResponse {
    cleared_events: number;
    remaining_events: number;
}

export async function clearDiagnosticsWorkspace(): Promise<ClearDiagnosticsWorkspaceResponse> {
    const response = await apiFetch(`${API_BASE}/diagnostics/clear`, {
        method: 'POST'
    });
    return handleResponse<ClearDiagnosticsWorkspaceResponse>(response);
}

export async function fetchDiagnosticsBundle(limit = 200): Promise<DiagnosticsBundlePayload> {
    const response = await apiFetch(`${API_BASE}/diagnostics/bundle?limit=${Math.max(1, Math.floor(limit))}`);
    return handleResponse<DiagnosticsBundlePayload>(response);
}
