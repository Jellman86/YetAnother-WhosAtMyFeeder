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
    const rawLabel = sample.accelerator?.label?.trim() ?? '';
    const acceleratorLabel = rawLabel.length > 0 ? rawLabel : null;

    return [
        ...history,
        {
            cpu,
            accelerator,
            acceleratorLabel
        }
    ].slice(-Math.max(1, limit));
}

/** One reading in the sidebar: a labelled meter in the same colour as its line on the Health chart. */
export interface LoadMeter {
    id: 'cpu' | 'accelerator';
    label: string;
    /** Whether the latest sample read this device. An unmeasured device is kept, said not measured. */
    measured: boolean;
    /** The reading, 0 to 100, for the meter's fill: 0 when the latest sample did not read it. */
    percent: number;
    /** The reading as the card says it, in whole percent, or the words for a reading not taken. */
    shown: string;
    /** The meter's fill class, shared with the Health chart's series. */
    fill: string;
}

/**
 * The meters for the latest sample: the CPU, then the primary accelerator when the server names
 * one. A detected device whose utilisation has not been measured yet (or missed this tick) stays
 * visible with "Not measured" in muted text and an empty track, distinguishable from a measured 0%.
 */
export function loadMeters(history: readonly TelemetryPoint[], cpuLabel: string, notMeasured: string): LoadMeter[] {
    const latest = history.at(-1);
    if (!latest) return [];
    const reading = (value: number | null) =>
        value === null ? { measured: false, percent: 0, shown: notMeasured } : { measured: true, percent: value, shown: `${Math.round(value)}%` };

    const meters: LoadMeter[] = [
        { id: 'cpu', label: cpuLabel, ...reading(latest.cpu), fill: CPU_STYLE.fill }
    ];
    if (latest.acceleratorLabel) {
        meters.push({ id: 'accelerator', label: latest.acceleratorLabel, ...reading(latest.accelerator), fill: PRIMARY_ACCELERATOR_STYLE.fill });
    }
    return meters;
}
