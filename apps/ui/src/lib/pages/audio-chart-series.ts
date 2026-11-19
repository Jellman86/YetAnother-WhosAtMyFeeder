/**
 * The series Audio history's day chart draws, shared by the canvas and its "Show the numbers" table
 * so the two can never disagree. The server counts calls per calendar day as a plain date, so a day
 * is labelled from that date as it stands, never from an instant shifted into the browser's zone.
 * The page passes the app's own day label, so the chart follows the owner's date format.
 */
export interface ChartPoint {
    label: string;
    count: number;
}

export function dailySeries(points: ReadonlyArray<{ date: string; count: number }>, dayLabel: (day: string) => string): ChartPoint[] {
    return points.map((point) => ({ label: dayLabel(point.date), count: point.count }));
}
