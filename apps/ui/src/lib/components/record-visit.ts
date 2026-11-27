/**
 * The visit a record's capture belongs to, as the page that opened it knows it. The record states
 * it beside the capture's own clip and photo options, so one capture's media never reads as the
 * whole visit. A single-capture visit is the capture itself and says nothing more.
 */
export interface RecordVisit {
    /** The capture the record was opened on; the visit is stated only while that record is open. */
    frigateEvent: string;
    captureCount: number;
    startTime: string;
    endTime: string;
}

export function recordVisit(
    frigateEvent: string,
    visit: { captureCount?: number; startTime: string; endTime: string } | null | undefined
): RecordVisit | null {
    const captureCount = visit?.captureCount ?? 0;
    if (!visit || captureCount < 2) return null;
    return { frigateEvent, captureCount, startTime: visit.startTime, endTime: visit.endTime };
}
