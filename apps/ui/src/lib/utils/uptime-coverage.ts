interface UptimeBucket {
    start: string;
    state: 'up' | 'down' | 'unknown';
}

export interface UptimeCoverage {
    /** Every bucket in the window was recorded, so a claim about the whole window is measured. */
    complete: boolean;
    recordedHours: number;
    recordedSince: string | null;
}

/** How much of an availability window was actually recorded; an unrecorded hour is not an up hour. */
export function uptimeCoverage(buckets: readonly UptimeBucket[], bucketMinutes: number): UptimeCoverage {
    const recorded = buckets.filter((bucket) => bucket.state !== 'unknown');
    return {
        complete: buckets.length > 0 && recorded.length === buckets.length,
        recordedHours: Math.round((recorded.length * bucketMinutes) / 60),
        recordedSince: recorded[0]?.start ?? null
    };
}
