import { API_BASE, apiFetch, handleResponse } from './core';
import type { components, paths } from './generated/openapi';

/** The one status reading every owner screen shows; the live stream pushes it as a `status` event. */
export type SystemStatus = paths['/api/status']['get']['response'];
export type SubsystemVerdict = components['schemas']['SubsystemVerdict'];
export type SubsystemKey = SubsystemVerdict['key'];
export type StatusTelemetry = components['schemas']['TelemetrySummary'];

export async function fetchSystemStatus(signal?: AbortSignal): Promise<SystemStatus> {
    const response = await apiFetch(`${API_BASE}/status`, { cache: 'no-store', timeoutMs: 10_000, signal });
    return handleResponse<SystemStatus>(response);
}

function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === 'object' && value !== null;
}

/** A pushed payload is untrusted until it has the parts every reader relies on. */
export function isSystemStatus(value: unknown): value is SystemStatus {
    if (!isRecord(value)) return false;
    return (
        typeof value.revision === 'number' &&
        typeof value.startup_instance_id === 'string' &&
        isRecord(value.overall) &&
        Array.isArray(value.subsystems) &&
        isRecord(value.jobs_summary) &&
        isRecord(value.jobs) &&
        Array.isArray(value.jobs.items) &&
        isRecord(value.analysis) &&
        isRecord(value.model) &&
        isRecord(value.connections)
    );
}
