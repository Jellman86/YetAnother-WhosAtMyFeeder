import { settingsStore } from '../stores/settings.svelte';
import { authStore } from '../stores/auth.svelte';

type DateFormat = 'locale' | 'mdy' | 'dmy' | 'ymd';
type TimeFormat = 'locale' | '12h' | '24h';

type DateInput = string | number | Date | null | undefined;

function getDateFormat(): DateFormat {
    const format = settingsStore.settings?.date_format ?? authStore.dateFormat ?? 'locale';
    return normalizeDateFormat(format);
}

export function normalizeDateFormat(format: unknown): DateFormat {
    if (format === 'mdy' || format === 'dmy' || format === 'ymd' || format === 'locale') {
        return format;
    }
    return 'locale';
}

function getTimeFormat(): TimeFormat {
    const format = settingsStore.settings?.time_format ?? authStore.timeFormat ?? 'locale';
    return normalizeTimeFormat(format);
}

export function normalizeTimeFormat(format: unknown): TimeFormat {
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
            return localeDate(date);
    }
}

// `toLocale*String` builds a formatter on every call, which a wall of photographs or a long list pays
// dozens of times per load. One formatter per set of options says exactly the same thing.
const formatters = new Map<string, Intl.DateTimeFormat>();
function formatterFor(options: Intl.DateTimeFormatOptions): Intl.DateTimeFormat {
    const key = JSON.stringify(options);
    let formatter = formatters.get(key);
    if (!formatter) {
        formatter = new Intl.DateTimeFormat(undefined, options);
        formatters.set(key, formatter);
    }
    return formatter;
}

/** The locale's own short date, as `toLocaleDateString()` gives it. */
function localeDate(date: Date): string {
    return formatterFor({}).format(date);
}

const CLOCK_FIELDS = ['hour', 'minute', 'second', 'dayPeriod', 'fractionalSecondDigits', 'timeStyle'] as const;

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

/**
 * A YYYY-MM-DD day, as a date input holds it, read as that local day rather than UTC midnight.
 * Under the locale format it is short ("1 Oct"), with the year only when it is not this year.
 */
export function formatCalendarDay(day: string, now: Date = new Date()): string {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(day);
    if (!match) return day;
    const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
    if (Number.isNaN(date.getTime())) return day;
    return formatShortDay(date, now);
}

/**
 * A day where space is short (a chart label, a strip of days): "1 Oct" under the locale format,
 * with the year only when it is not this year. A pinned format is used as it stands.
 */
export function formatShortDay(value: DateInput, now: Date = new Date()): string {
    const date = toDate(value);
    if (!date) return '';
    const format = getDateFormat();
    if (format !== 'locale') return formatDateParts(date, format);
    return date.toLocaleDateString(undefined, {
        day: 'numeric',
        month: 'short',
        ...(date.getFullYear() === now.getFullYear() ? {} : { year: 'numeric' })
    });
}

/**
 * A day as a record states it: "14 Mar 2025" under the locale format, with the year always, so a
 * first and a last sighting years apart read plainly. A pinned format is used as it stands.
 */
export function formatDay(value: DateInput): string {
    const date = toDate(value);
    if (!date) return '';
    const format = getDateFormat();
    if (format !== 'locale') return formatDateParts(date, format);
    return date.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
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
        return `${localeDate(date)} ${time}`;
    }

    return `${formatDateParts(date, format)} ${time}`;
}

export function formatTime(value: DateInput, options?: Intl.DateTimeFormatOptions): string {
    const date = toDate(value);
    if (!date) return typeof value === 'string' ? value : '';
    const resolved: Intl.DateTimeFormatOptions = {
        ...(options ?? { hour: '2-digit', minute: '2-digit' }),
        ...hourCycleOptions(),
    };
    // Without a clock field `toLocaleTimeString` adds its own, which a plain formatter would not.
    if (!CLOCK_FIELDS.some((field) => field in resolved)) return date.toLocaleTimeString([], resolved);
    return formatterFor(resolved).format(date);
}

/**
 * A whole hour of the day on the app's clock, so a chart axis never shows "5 PM" beside a log
 * that says 17:26. `axis` is the short form for a crowded axis: "17" on the 24 hour clock, and
 * "5 PM" with a non-breaking space on the 12 hour one, so a label never wraps.
 */
export function formatHour(hour: number, style: 'full' | 'axis' = 'full'): string {
    const clamped = Math.max(0, Math.min(23, Math.trunc(hour)));
    const date = new Date(2000, 0, 1, clamped, 0, 0);
    if (style === 'full') return formatTime(date);
    if (getTimeFormat() === '24h') return pad2(clamped);
    return date.toLocaleTimeString([], { hour: 'numeric', ...hourCycleOptions() }).replace(/\s/g, '\u00a0');
}
