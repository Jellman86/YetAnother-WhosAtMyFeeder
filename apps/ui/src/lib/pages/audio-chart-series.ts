/**
 * The series Audio history's charts draw, shared by each canvas and its "Show the numbers" table so
 * the two can never disagree. The server counts calls per calendar day as a plain date, so a day is
 * labelled from that date as it stands, never from an instant shifted into the browser's zone; the
 * hour chart always has all 24 hours, with an hour nothing was heard in shown as zero. The page
 * passes the app's own day and hour labels, so a chart follows the owner's date format and clock.
 */
export interface ChartPoint {
    label: string;
    count: number;
}

export function dailySeries(points: ReadonlyArray<{ date: string; count: number }>, dayLabel: (day: string) => string): ChartPoint[] {
    return points.map((point) => ({ label: dayLabel(point.date), count: point.count }));
}

export function hourlySeries(
    buckets: ReadonlyArray<{ hour: number; count: number }>,
    hourLabel: (hour: number) => string
): Array<ChartPoint & { hour: number }> {
    const counts = new Array<number>(24).fill(0);
    for (const bucket of buckets) {
        if (Number.isInteger(bucket.hour) && bucket.hour >= 0 && bucket.hour < 24) counts[bucket.hour] = bucket.count;
    }
    return counts.map((count, hour) => ({ hour, label: hourLabel(hour), count }));
}
