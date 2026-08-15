/**
 * Reading the event-pipeline section of `/health`.
 *
 * The backend counts every dropped event in one total, but only some drops are
 * faults. A detection rejected by the confidence threshold or a blocklist is the
 * pipeline working as configured, so it must not be presented as degradation:
 * on a working feeder that counter only ever climbs.
 */

export interface EventPipelineHealth {
    status?: unknown;
    critical_failure_active?: unknown;
    critical_failures?: unknown;
    dropped_events?: unknown;
    expected_drops?: unknown;
    fault_drops?: unknown;
    expected_drop_reasons?: unknown;
    fault_drop_reasons?: unknown;
}

export interface DropReasonCount {
    reason: string;
    count: number;
}

function toCount(value: unknown): number {
    const parsed = Number(value);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
}

function toReasonCounts(value: unknown): DropReasonCount[] {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return [];
    return Object.entries(value as Record<string, unknown>)
        .map(([reason, count]) => ({ reason, count: toCount(count) }))
        .filter(entry => entry.count > 0)
        .sort((a, b) => b.count - a.count || a.reason.localeCompare(b.reason));
}

export function faultDropCount(pipeline: EventPipelineHealth | null | undefined): number {
    return toCount(pipeline?.fault_drops);
}

export function expectedDropCount(pipeline: EventPipelineHealth | null | undefined): number {
    return toCount(pipeline?.expected_drops);
}

export function expectedDropReasons(pipeline: EventPipelineHealth | null | undefined): DropReasonCount[] {
    return toReasonCounts(pipeline?.expected_drop_reasons);
}

export function faultDropReasons(pipeline: EventPipelineHealth | null | undefined): DropReasonCount[] {
    return toReasonCounts(pipeline?.fault_drop_reasons);
}

/**
 * The verdict shown on the Event Pipeline card. `fallback` is used only when the
 * backend sent no status of its own, so the page never invents a healthier or
 * worse state than the API reported.
 */
export function eventPipelineVerdict(
    pipeline: EventPipelineHealth | null | undefined,
    fallback: string
): string {
    if (pipeline?.critical_failure_active === true) return 'critical';
    if (faultDropCount(pipeline) > 0) return 'degraded';
    const reported = pipeline?.status;
    if (typeof reported === 'string' && reported.trim().length > 0) return reported.trim();
    return fallback;
}

/** Whether anything was filtered out by configuration rather than by failure. */
export function hasExpectedDrops(pipeline: EventPipelineHealth | null | undefined): boolean {
    return expectedDropCount(pipeline) > 0;
}
