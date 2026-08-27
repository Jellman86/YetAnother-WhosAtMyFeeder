import { settingsStore } from '../stores/settings.svelte';
import { authStore } from '../stores/auth.svelte';

export type DateFormat = 'locale' | 'mdy' | 'dmy' | 'ymd';
export type TimeFormat = 'locale' | '12h' | '24h';

type DateInput = string | number | Date | null | undefined;

function getDateFormat(): DateFormat {
    const format = settingsStore.settings?.date_format ?? authStore.dateFormat ?? 'locale';
    if (format === 'mdy' || format === 'dmy' || format === 'ymd' || format === 'locale') {
        return format;
    }
    return 'locale';
}

function getTimeFormat(): TimeFormat {
    const format = settingsStore.settings?.time_format ?? authStore.timeFormat ?? 'locale';
    if (format === '12h' || format === '24h' || format === 'locale') {
        return format;
    }
    return 'locale';
}

/**
 * `hour12` overrides whatever the browser locale would have chosen. Leaving it
 * undefined is not the same as setting it false: undefined defers to the locale,
 * which is what 'locale' means here.
 */
function hourCycleOptions(): Pick<Intl.DateTimeFormatOptions, 'hour12'> {
    const format = getTimeFormat();
    if (format === '24h') return { hour12: false };
    if (format === '12h') return { hour12: true };
    return {};
}

function pad2(value: number): string {
    return String(value).padStart(2, '0');
}

function formatDateParts(date: Date, format: DateFormat): string {
    const year = date.getFullYear();
    const month = pad2(date.getMonth() + 1);
    const day = pad2(date.getDate());

    switch (format) {
        case 'mdy':
            return `${month}/${day}/${year}`;
        case 'dmy':
            return `${day}/${month}/${year}`;
        case 'ymd':
            return `${year}-${month}-${day}`;
        default:
            return date.toLocaleDateString();
    }
}

function toDate(value: DateInput): Date | null {
    if (!value) return null;
    const date = value instanceof Date ? value : new Date(value);
    if (Number.isNaN(date.getTime())) return null;
    return date;
}

export function formatDate(value: DateInput): string {
    const date = toDate(value);
    if (!date) return typeof value === 'string' ? value : '';
    return formatDateParts(date, getDateFormat());
}

export function formatDateTime(value: DateInput): string {
    const date = toDate(value);
    if (!date) return typeof value === 'string' ? value : '';

    const format = getDateFormat();
    // Minute precision, the same as `formatTime`. Both `toLocaleString` and a
    // bare `toLocaleTimeString` carry seconds by default, so a detection read
    // 07:38 in one place and 07:38:00 in another, and an eBird sighting claimed
    // a precision the observation never had.
    const time = formatTime(date);
    if (format === 'locale') {
        return `${date.toLocaleDateString()} ${time}`;
    }

    return `${formatDateParts(date, format)} ${time}`;
}

export function formatTime(value: DateInput, options?: Intl.DateTimeFormatOptions): string {
    const date = toDate(value);
    if (!date) return typeof value === 'string' ? value : '';
    return date.toLocaleTimeString([], {
        ...(options ?? { hour: '2-digit', minute: '2-digit' }),
        ...hourCycleOptions(),
    });
}
