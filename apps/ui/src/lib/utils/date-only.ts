type DateLike = Date | string | number;

function pad2(value: number): string {
    return String(value).padStart(2, '0');
}

/**
 * Render a local-calendar date as YYYY-MM-DD without UTC conversion.
 * This avoids timezone-boundary drift caused by toISOString().split('T')[0].
 */
export function toLocalYMD(value: DateLike = new Date()): string {
    const date = value instanceof Date ? value : new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    const year = date.getFullYear();
    const month = pad2(date.getMonth() + 1);
    const day = pad2(date.getDate());
    return `${year}-${month}-${day}`;
}
