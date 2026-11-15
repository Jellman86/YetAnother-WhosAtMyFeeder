/**
 * Garden thresholds are stored from 0 to 1 and shown as percentages. Twelve significant digits
 * absorb binary rounding (0.63 * 100 is 63.00000000000001) while keeping a calibrated value such
 * as 0.6385722 exactly as saved.
 */
const SIGNIFICANT_DIGITS = 12;

function clean(value: number): number {
    return Number(value.toPrecision(SIGNIFICANT_DIGITS));
}

/** The percentage as shown beside a threshold; empty for a value that is not a number. */
export function thresholdPercentText(value: number): string {
    return Number.isFinite(value) ? String(clean(value * 100)) : '';
}
