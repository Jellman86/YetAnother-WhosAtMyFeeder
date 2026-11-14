/**
 * A value Settings could not save, attached to the field that holds it.
 *
 * The message is an i18n key with its values and an English default, resolved when shown, so the
 * text follows the reader's language. Each message says what to enter, never the validator's code.
 */
export interface SettingsFieldError {
    field: string;
    key: string;
    values?: Record<string, string | number>;
    fallback: string;
}

interface ValidationDetail {
    type?: unknown;
    loc?: unknown;
    msg?: unknown;
    ctx?: unknown;
}

// Fields whose rejection has one cause worth naming in its own words.
const FIELD_MESSAGES: Readonly<Record<string, { key: string; fallback: string }>> = {
    frigate_url: {
        key: 'settings.field_errors.frigate_url',
        fallback: 'Start the address with http:// or https://, for example http://frigate:5000.'
    },
    birdnet_url: {
        key: 'settings.field_errors.birdnet_url',
        fallback: 'Start the address with http:// or https://, for example http://birdnet-go:8080.'
    },
    notifications_instance_url: {
        key: 'settings.field_errors.instance_url',
        fallback: 'Start the address with http:// or https://, for example https://feeder.example.com.'
    },
    auth_password: {
        key: 'settings.field_errors.auth_password_required',
        fallback: 'Set a password before turning on sign-in.'
    },
    auth_username: {
        key: 'settings.field_errors.auth_username',
        fallback: 'Use only letters, numbers, underscores, hyphens and full stops.'
    }
};

function fieldOf(loc: unknown): string | null {
    if (!Array.isArray(loc)) return null;
    const parts = loc.filter((part): part is string => typeof part === 'string' && part !== 'body');
    return parts[0] ?? null;
}

function numberIn(ctx: unknown, name: string): number | null {
    if (!ctx || typeof ctx !== 'object') return null;
    const value = (ctx as Record<string, unknown>)[name];
    return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function serverText(msg: unknown): string {
    return typeof msg === 'string' ? msg.replace(/^Value error,\s*/i, '').trim() : '';
}

function describe(field: string, detail: ValidationDetail): SettingsFieldError {
    const type = typeof detail.type === 'string' ? detail.type : '';
    const upper = numberIn(detail.ctx, 'le') ?? numberIn(detail.ctx, 'lt');
    const lower = numberIn(detail.ctx, 'ge') ?? numberIn(detail.ctx, 'gt');
    if ((type === 'less_than_equal' || type === 'less_than') && upper !== null) {
        return { field, key: 'settings.field_errors.too_large', values: { limit: upper }, fallback: 'Enter {limit} or less.' };
    }
    if ((type === 'greater_than_equal' || type === 'greater_than') && lower !== null) {
        return { field, key: 'settings.field_errors.too_small', values: { limit: lower }, fallback: 'Enter {limit} or more.' };
    }
    if (type === 'int_parsing' || type === 'int_from_float' || type === 'int_type') {
        return { field, key: 'settings.field_errors.whole_number', fallback: 'Enter a whole number.' };
    }
    if (type === 'float_parsing' || type === 'float_type') {
        return { field, key: 'settings.field_errors.number', fallback: 'Enter a number.' };
    }
    const known = FIELD_MESSAGES[field];
    if (known) return { field, ...known };
    const text = serverText(detail.msg);
    return {
        field,
        key: 'settings.field_errors.refused',
        values: { reason: text || type },
        fallback: 'Not accepted: {reason}. Change the value and save again.'
    };
}

/**
 * The field errors in a rejected save's `detail`, one per field (the first reason wins).
 * Anything that does not name a field is left to the caller's general message.
 */
export function settingsFieldErrors(detail: unknown): SettingsFieldError[] {
    if (!Array.isArray(detail)) return [];
    const errors = new Map<string, SettingsFieldError>();
    for (const entry of detail as ValidationDetail[]) {
        if (!entry || typeof entry !== 'object') continue;
        const field = fieldOf(entry.loc);
        if (!field || errors.has(field)) continue;
        errors.set(field, describe(field, entry));
    }
    return [...errors.values()];
}

/** A value checked here before saving, outside the range the server accepts. */
export function rangeFieldError(field: string, min: number, max: number, unit: '' | '%' = ''): SettingsFieldError {
    return {
        field,
        key: unit === '%' ? 'settings.field_errors.out_of_range_percent' : 'settings.field_errors.out_of_range',
        values: { min, max },
        fallback: unit === '%' ? 'Enter a value from {min}% to {max}%.' : 'Enter a value from {min} to {max}.'
    };
}

/**
 * The errors still worth showing: a field's error is withdrawn once its value is no longer the one
 * that was refused, so a corrected field stops claiming to be wrong before the next save.
 */
export function standingFieldErrors(
    errors: readonly SettingsFieldError[],
    refused: Readonly<Record<string, unknown>>,
    current: Readonly<Record<string, unknown>>
): SettingsFieldError[] {
    return errors.filter((error) => JSON.stringify(refused[error.field]) === JSON.stringify(current[error.field]));
}
