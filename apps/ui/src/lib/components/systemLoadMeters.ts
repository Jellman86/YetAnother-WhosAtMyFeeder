import type { SystemTelemetry } from '../api/system';
import { CPU_STYLE, PRIMARY_ACCELERATOR_STYLE } from '../utils/system-history';

export interface TelemetryPoint {
    cpu: number | null;
    accelerator: number | null;
    acceleratorLabel: string | null;
}

const HISTORY_LIMIT = 25;

function finitePercent(value: number | null | undefined): number | null {
    return typeof value === 'number' && Number.isFinite(value)
        ? Math.max(0, Math.min(100, value))
        : null;
}

export function appendTelemetrySample(
    history: TelemetryPoint[],
    sample: SystemTelemetry,
    limit = HISTORY_LIMIT
): TelemetryPoint[] {
    const cpu = finitePercent(sample.cpu_percent);
    const accelerator = finitePercent(sample.accelerator?.utilization_percent);
    if (cpu === null && accelerator === null) return history;

    return [
        ...history,
        {
            cpu,
            accelerator,
            acceleratorLabel: sample.accelerator?.label ?? null
        }
    ].slice(-Math.max(1, limit));
}

/** One reading in the sidebar: a labelled meter in the same colour as its line on the Health chart. */
export interface LoadMeter {
    id: 'cpu' | 'accelerator';
    label: string;
    /** The reading, 0 to 100, for the meter's fill. */
    percent: number;
    /** The reading as the card says it, in whole percent. */
    shown: string;
    /** The meter's fill class, shared with the Health chart's series. */
    fill: string;
}

/**
 * The latest sample as meters: the CPU, then the accelerator the server names as primary. A reading
 * that was not taken has no meter, so an unmeasured device is never drawn as an empty one.
 */
export function loadMeters(point: TelemetryPoint | undefined, cpuLabel: string): LoadMeter[] {
    if (!point) return [];
    const meters: LoadMeter[] = [];
    if (point.cpu !== null) {
        meters.push({ id: 'cpu', label: cpuLabel, percent: point.cpu, shown: `${Math.round(point.cpu)}%`, fill: CPU_STYLE.fill });
    }
    if (point.accelerator !== null && point.acceleratorLabel) {
        meters.push({
            id: 'accelerator',
            label: point.acceleratorLabel,
            percent: point.accelerator,
            shown: `${Math.round(point.accelerator)}%`,
            fill: PRIMARY_ACCELERATOR_STYLE.fill
        });
    }
    return meters;
}
