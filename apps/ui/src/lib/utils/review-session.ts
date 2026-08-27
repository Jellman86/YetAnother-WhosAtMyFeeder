import type { Detection } from '../api';

/**
 * Working through the review queue one detection at a time. Immutable: each step
 * returns a new session, so the modal can render from a single piece of state.
 */
export interface ReviewSession {
    readonly items: readonly Detection[];
    readonly index: number;
    readonly resolved: number;
    readonly skipped: number;
    readonly current: Detection | null;
    /** One-based, for "3 of 7". */
    readonly position: number;
    readonly total: number;
    readonly done: boolean;
}

export type ReviewOutcome = 'resolved' | 'skipped';

function build(
    items: readonly Detection[],
    index: number,
    resolved: number,
    skipped: number
): ReviewSession {
    return {
        items,
        index,
        resolved,
        skipped,
        current: items[index] ?? null,
        position: Math.min(index + 1, items.length),
        total: items.length,
        done: index >= items.length
    };
}

export function createReviewSession(items: readonly Detection[]): ReviewSession {
    return build([...items], 0, 0, 0);
}

export function advance(session: ReviewSession, outcome: ReviewOutcome): ReviewSession {
    return build(
        session.items,
        session.index + 1,
        session.resolved + (outcome === 'resolved' ? 1 : 0),
        session.skipped + (outcome === 'skipped' ? 1 : 0)
    );
}

export function remaining(session: ReviewSession): number {
    return Math.max(session.total - session.index, 0);
}
