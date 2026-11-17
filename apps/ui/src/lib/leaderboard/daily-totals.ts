import type { components } from '../api/generated/openapi';

type DailyTotalsCoverage = components['schemas']['DailyTotalsCoverage'];

/**
 * What a chart should say about the days it counted from sealed daily totals (#949).
 *
 * `firstStoredDay` is the first day counted from stored captures, so the note can read
 * "Counts before {day} come from daily totals". `partialBefore` is set when some totals were
 * sealed after older captures had already gone: the first day whose total is whole, or
 * `firstStoredDay` when none of them is.
 */
export interface DailyTotalsNote {
    firstStoredDay: string;
    partialBefore: string | null;
}

function nextDay(isoDay: string): string {
    const [year, month, day] = isoDay.split('-').map(Number);
    return new Date(Date.UTC(year, month - 1, day + 1)).toISOString().slice(0, 10);
}

export function dailyTotalsNote(coverage: DailyTotalsCoverage | null | undefined): DailyTotalsNote | null {
    const through = coverage?.totals_through;
    if (!through) return null;
    const firstStoredDay = nextDay(through);
    if (!coverage.partial) return { firstStoredDay, partialBefore: null };
    return { firstStoredDay, partialBefore: coverage.complete_from ?? firstStoredDay };
}
