import { API_BASE, apiFetchJson } from './core';
import type { components, paths } from './generated/openapi';

/** The one status reading every owner screen shows; the live stream pushes it as a `status` event. */
export type SystemStatus = paths['/api/status']['get']['response'];
export type SubsystemVerdict = components['schemas']['SubsystemVerdict'];
export type SubsystemKey = SubsystemVerdict['key'];
export type StatusTelemetry = components['schemas']['TelemetrySummary'];

/** The timeout and a cancel cover the whole read, body included: a stalled body never holds a read open. */
export function fetchSystemStatus(signal?: AbortSignal): Promise<SystemStatus> {
    return apiFetchJson<SystemStatus>(`${API_BASE}/status`, { cache: 'no-store', timeoutMs: 10_000, signal });
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
