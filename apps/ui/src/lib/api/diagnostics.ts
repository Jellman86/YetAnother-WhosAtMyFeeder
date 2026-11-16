import { API_BASE, apiFetch, apiFetchJson, handleResponse, type Guarded } from './core';
import type { paths } from './generated/openapi';

export type DiagnosticsWorkspacePayload = paths['/api/diagnostics/workspace']['get']['response'];

export type BackendDiagnosticEvent = DiagnosticsWorkspacePayload['backend_diagnostics']['events'][number];

/** Timed out after 15 s, body included, so a stalled response never holds the incident readers open. */
export function fetchDiagnosticsWorkspace(limit = 200, signal?: AbortSignal): Guarded<DiagnosticsWorkspacePayload> {
    return apiFetchJson<DiagnosticsWorkspacePayload>(`${API_BASE}/diagnostics/workspace?limit=${Math.max(1, Math.floor(limit))}`, {
        cache: 'no-store',
        timeoutMs: 15_000,
        signal
    });
}

export type ClearDiagnosticsWorkspaceResponse = paths['/api/diagnostics/clear']['post']['response'];

export async function clearDiagnosticsWorkspace(): Promise<ClearDiagnosticsWorkspaceResponse> {
    const response = await apiFetch(`${API_BASE}/diagnostics/clear`, {
        method: 'POST'
    });
    return handleResponse<ClearDiagnosticsWorkspaceResponse>(response);
}

/** The broker session and Frigate's API as the server last measured them (owner only). */
export type ServiceConnections = paths['/api/diagnostics/connections']['get']['response'];
