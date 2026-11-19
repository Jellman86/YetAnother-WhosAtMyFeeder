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
    /** Whether the latest sample read this device. A meter that was not is kept, said not measured. */
    measured: boolean;
    /** The reading, 0 to 100, for the meter's fill: 0 when the latest sample did not read it. */
    percent: number;
    /** The reading as the card says it, in whole percent, or the words for a reading not taken. */
    shown: string;
    /** The meter's fill class, shared with the Health chart's series. */
    fill: string;
}

/**
 * The meters for the recent samples: the CPU, then the accelerator the server names as primary. A
 * device gets a meter once any sample in the window has read it, and keeps it while the window
 * remembers that reading, so one missed sample says "not measured" in its row instead of making the
 * row vanish and the card below it jump. A device no sample has read has no meter, so an unmeasured
 * device is never drawn as an empty one.
 */
export function loadMeters(history: readonly TelemetryPoint[], cpuLabel: string, notMeasured: string): LoadMeter[] {
    const latest = history.at(-1);
    if (!latest) return [];
    const meters: LoadMeter[] = [];
    const reading = (value: number | null) =>
        value === null ? { measured: false, percent: 0, shown: notMeasured } : { measured: true, percent: value, shown: `${Math.round(value)}%` };

    if (history.some((point) => point.cpu !== null)) {
        meters.push({ id: 'cpu', label: cpuLabel, ...reading(latest.cpu), fill: CPU_STYLE.fill });
    }
    const acceleratorLabel = latest.acceleratorLabel ?? history.findLast((point) => point.acceleratorLabel)?.acceleratorLabel ?? null;
    if (acceleratorLabel && history.some((point) => point.accelerator !== null)) {
        meters.push({ id: 'accelerator', label: acceleratorLabel, ...reading(latest.accelerator), fill: PRIMARY_ACCELERATOR_STYLE.fill });
    }
    return meters;
}
