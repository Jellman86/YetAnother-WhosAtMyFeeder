/** The Leaderboard's time spans, as its span bar names them. */
export type RowSpan = 'day' | 'week' | 'month' | 'all';

/** The figure a ranking row showed for a species: its unit, and the window it covers. */
export interface RowFigure {
    unit: 'visits' | 'detections';
    count: number;
    span: RowSpan;
}

interface RankedRow {
    species: string;
    count: number;
    audio_only?: boolean;
}

/**
 * What the row a species dialog was opened from said. Null when no row names the species or the
 * row was only heard, so the dialog never repeats a figure the reader was not shown.
 */
export function rowFigureFor(
    rows: readonly RankedRow[],
    species: string | null,
    view: { countsAreVisits: boolean; span: RowSpan | undefined }
): RowFigure | null {
    const row = species === null ? undefined : rows.find((entry) => entry.species === species);
    // Without a span the figure has no window to name, so it is not repeated.
    if (!row || row.audio_only || !Number.isFinite(row.count) || view.span === undefined) return null;
    return { unit: view.countsAreVisits ? 'visits' : 'detections', count: row.count, span: view.span };
}

/**
 * The species dialog's first figure. Opened from a row that counted visits, it leads with those
 * visits in the row's window, so the dialog and the row agree; its all-time detections follow.
 */
export function speciesStatLead(openedFrom: RowFigure | null | undefined): 'row_visits' | 'detections' {
    return openedFrom?.unit === 'visits' ? 'row_visits' : 'detections';
}
