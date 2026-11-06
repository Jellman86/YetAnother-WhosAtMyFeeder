/**
 * Garden thresholds are stored from 0 to 1 and shown as percentages. Twelve significant digits
 * absorb binary rounding (0.63 * 100 is 63.00000000000001) while keeping a calibrated value such
 * as 0.6385722 exactly as saved.
 */
const SIGNIFICANT_DIGITS = 12;

function clean(value: number): number {
    return Number(value.toPrecision(SIGNIFICANT_DIGITS));
}

function fractionalDigits(value: number | undefined): number {
    if (value === undefined || !Number.isFinite(value) || value < 0.5 || value > 0.95) {
        return 0;
    }
    return String(value).split('.')[1]?.length ?? 0;
}

/** One percentage point, or finer when the value or its saved form was calibrated more precisely. */
export function gardenThresholdPercentStep(value: number | undefined, savedValue?: number): number {
    const digits = Math.max(2, fractionalDigits(value), fractionalDigits(savedValue));
    return 10 ** -(digits - 2);
}

/** The percentage for a number field; empty for a value that is not a number. */
export function thresholdPercentText(value: number): string {
    return Number.isFinite(value) ? String(clean(value * 100)) : '';
}

/** The stored 0 to 1 value for a typed percentage; NaN when nothing usable was typed. */
export function percentToThreshold(text: string): number {
    if (text.trim() === '') return Number.NaN;
    const percent = Number(text);
    return Number.isFinite(percent) ? clean(percent / 100) : Number.NaN;
}
