import { API_BASE, apiFetch, handleResponse } from './core';
import type { paths } from './generated/openapi';

export type DiagnosticsWorkspacePayload = paths['/api/diagnostics/workspace']['get']['response'];

export type BackendDiagnosticEvent = DiagnosticsWorkspacePayload['backend_diagnostics']['events'][number];

export type VideoClassifierFocusedDiagnostics = NonNullable<
    DiagnosticsWorkspacePayload['focused_diagnostics']['video_classifier']
>;

export type DiagnosticsBundlePayload = paths['/api/diagnostics/bundle']['get']['response'];

export async function fetchDiagnosticsWorkspace(limit = 200): Promise<DiagnosticsWorkspacePayload> {
    const response = await apiFetch(`${API_BASE}/diagnostics/workspace?limit=${Math.max(1, Math.floor(limit))}`, {
        timeoutMs: 15_000
    });
    return handleResponse<DiagnosticsWorkspacePayload>(response);
}

export type ClearDiagnosticsWorkspaceResponse = paths['/api/diagnostics/clear']['post']['response'];

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
