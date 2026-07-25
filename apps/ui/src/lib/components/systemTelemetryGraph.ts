import type { SystemTelemetry } from '../api/system';

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

function coordinate(value: number): string {
    return Number(value.toFixed(2)).toString();
}

export function telemetryPolyline(
    history: TelemetryPoint[],
    series: 'cpu' | 'accelerator'
): string {
    const denominator = Math.max(1, history.length - 1);
    return history
        .map((point, index) => {
            const value = point[series];
            if (value === null) return null;
            const x = index / denominator * 100;
            const y = 100 - finitePercent(value)!;
            return `${coordinate(x)},${coordinate(y)}`;
        })
        .filter((point): point is string => point !== null)
        .join(' ');
}
