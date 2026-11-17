type Counts = Record<string, Record<string, number>>;

/** Every count in `next` above `allowed`, as "rule scope: before -> after". */
export function raisedCounts(allowed: Counts, next: Counts): string[];

/** Every count in `next` below `allowed`, as "rule scope: before -> after". */
export function loweredCounts(allowed: Counts, next: Counts): string[];

/** The measured counts when none rose above the baseline; otherwise no baseline and the rises. */
export function lowerBaseline(baseline: Counts, measured: Counts): { next: Counts | null; raised: string[] };

/** The sum of each rule's counts. */
export function ruleTotals(counts: Counts): Record<string, number>;
