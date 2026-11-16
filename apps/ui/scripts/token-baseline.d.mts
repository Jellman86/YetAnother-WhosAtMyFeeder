type Counts = { palette: number; dark: number; arbitrary: number };
type Baseline = Record<string, Counts>;

/** Every count in `next` that is above `allowed`, as "file: kind before -> after". */
export function raisedCounts(allowed: Baseline, next: Baseline): string[];

/** The measured counts when none rose above the baseline; otherwise no baseline and the rises. */
export function lowerBaseline(baseline: Baseline, measured: Baseline): { next: Baseline | null; raised: string[] };
