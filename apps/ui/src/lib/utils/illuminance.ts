import type { components } from '../api/generated/openapi';

export type HaIlluminanceTestReading = components['schemas']['HaIlluminanceTestReading'];
type MissingReason = NonNullable<HaIlluminanceTestReading['reason']>;

const ENTITY_ID_MAX_LENGTH = 255;
const ENTITY_ID_PART = /^[a-z0-9_]+$/;

/** Whether a typed value has the shape of a Home Assistant entity id, such as `sensor.feeder_illuminance`. */
export function isHomeAssistantEntityId(value: string): boolean {
    const id = value.trim();
    if (id.length > ENTITY_ID_MAX_LENGTH) return false;
    const parts = id.split('.');
    return parts.length === 2 && parts.every((part) => ENTITY_ID_PART.test(part));
}

/** A stored light level as text, or null when none was measured. `lx` is the SI symbol and is not translated. */
export function formatIlluminance(lux: number | null | undefined, locale?: string): string | null {
    if (lux === null || lux === undefined || !Number.isFinite(lux) || lux < 0) return null;
    // Below 10 lx the first decimal separates dusk from dark; above it, it is noise.
    const maximumFractionDigits = lux < 9.95 ? 1 : 0;
    return `${lux.toLocaleString(locale, { maximumFractionDigits })} lx`;
}

export interface IlluminanceStepText {
    measured: (values: { reading: string; entity: string }) => string;
    missing: Record<MissingReason, (values: { entity: string }) => string>;
    noAnswer: string;
}

/**
 * The outcome of the live test's illuminance stage. It passes only with a
 * measured value; every other answer fails with its reason in words.
 */
export function illuminanceStepOutcome(
    reading: HaIlluminanceTestReading | null | undefined,
    text: IlluminanceStepText,
    locale?: string
): { status: 'ok' | 'error'; message: string } {
    if (!reading) return { status: 'error', message: text.noAnswer };
    const formatted = reading.status === 'ok' ? formatIlluminance(reading.lux, locale) : null;
    if (formatted !== null) {
        return { status: 'ok', message: text.measured({ reading: formatted, entity: reading.entity_id }) };
    }
    const explain = reading.reason ? text.missing[reading.reason] : undefined;
    return { status: 'error', message: explain ? explain({ entity: reading.entity_id }) : text.noAnswer };
}
