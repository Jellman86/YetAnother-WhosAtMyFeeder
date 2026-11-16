import type { ActivityPhase } from './model-readiness';

/** Work this page started, kept only until the server has had time to report it. */
export interface ActivityHint {
    phase: ActivityPhase;
    at: number;
}

/** How long a hint stands unconfirmed: long enough for the request that starts the work to land. */
export const HINT_GRACE_MS = 6000;

/**
 * What is in progress on each model, from the server's report and this page's hints.
 *
 * The server is where downloads and hardware checks run, so its report is the answer: what it lists
 * is in progress, whichever page or tab started it, and what it stops listing has ended. A hint
 * only covers the moment between pressing a button and the server knowing. It is dropped as soon as
 * the server reports that model, or when the server has not confirmed it in time.
 */
export function reconcileActivity(
    server: Readonly<Record<string, ActivityPhase>>,
    hints: Readonly<Record<string, ActivityHint>>,
    now: number
): { phases: Record<string, ActivityPhase>; hints: Record<string, ActivityHint> } {
    const kept: Record<string, ActivityHint> = {};
    for (const [modelId, hint] of Object.entries(hints)) {
        if (!(modelId in server) && now - hint.at <= HINT_GRACE_MS) kept[modelId] = hint;
    }
    const hinted = Object.fromEntries(Object.entries(kept).map(([modelId, hint]) => [modelId, hint.phase]));
    return { phases: { ...hinted, ...server }, hints: kept };
}
