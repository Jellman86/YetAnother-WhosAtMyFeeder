import { settingsStore } from '../stores/settings.svelte';
import { authStore } from '../stores/auth.svelte';

export type DateFormat = 'locale' | 'mdy' | 'dmy' | 'ymd';

type DateInput = string | number | Date | null | undefined;

function getDateFormat(): DateFormat {
    const format = settingsStore.settings?.date_format ?? authStore.dateFormat ?? 'locale';
    if (format === 'mdy' || format === 'dmy' || format === 'ymd' || format === 'locale') {
        return format;
    }
    return 'locale';
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
    if (format === 'locale') {
        return date.toLocaleString();
    }

    return `${formatDateParts(date, format)} ${date.toLocaleTimeString()}`;
}

export function formatTime(value: DateInput, options?: Intl.DateTimeFormatOptions): string {
    const date = toDate(value);
    if (!date) return typeof value === 'string' ? value : '';
    return date.toLocaleTimeString([], options ?? { hour: '2-digit', minute: '2-digit' });
}
