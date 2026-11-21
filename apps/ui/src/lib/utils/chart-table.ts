/** One series as a chart draws it: its name, a value per label, and whether the reader hid it. */
export interface ChartSeries {
    label: string;
    data: readonly (number | null)[];
    hidden?: boolean;
    /** The series' own format, where its values carry a unit the others do not (°C, km/h). */
    format?: (value: number) => string;
}

/**
 * A chart as a table: a row per label, a column per series still shown, in the chart's own names and
 * formats, so the table says what the canvas draws (WCAG 1.1.1, the equivalent record). A gap in the
 * data is a dash, never a zero.
 */
export function chartTable(
    labelHeading: string,
    labels: readonly string[],
    series: readonly ChartSeries[],
    format: (value: number) => string
): { columns: string[]; rows: string[][] } {
    const shown = series.filter((item) => !item.hidden);
    return {
        columns: [labelHeading, ...shown.map((item) => item.label)],
        rows: labels.map((label, index) => [
            label,
            ...shown.map((item) => {
                const value = item.data[index];
                return typeof value === 'number' && Number.isFinite(value) ? (item.format ?? format)(value) : '—';
            })
        ])
    };
}

/**
 * A ring chart (donut) as a table: its visible slices with their values and shares. The share is of
 * the slices still shown, as the ring draws it once the reader hides one, so the two never disagree.
 */
export function shareTable(
    columns: [label: string, value: string, share: string],
    labels: readonly string[],
    values: readonly number[],
    hidden: readonly number[],
    format: (value: number) => string
): { columns: string[]; rows: string[][] } {
    const shown = labels.map((label, index) => ({ label, value: values[index] ?? 0, index })).filter((slice) => !hidden.includes(slice.index));
    const total = shown.reduce((sum, slice) => sum + slice.value, 0);
    return {
        columns: [...columns],
        rows: shown.map((slice) => [slice.label, format(slice.value), total > 0 ? `${Math.round((slice.value / total) * 100)}%` : '—'])
    };
}

/** A bucket's precipitation in mm, as the timeline's rain bands measure it: rain and snow together, or the reported total if larger. */
export function bucketPrecipitation(rain: number | null, snow: number | null, total: number | null): number {
    return Math.max(Math.max(0, rain ?? 0) + Math.max(0, snow ?? 0), Math.max(0, total ?? 0));
}
