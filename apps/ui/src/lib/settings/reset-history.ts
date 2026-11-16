/**
 * "Delete all history" deletes the number its confirmation stated, or nothing.
 *
 * The count is read over the reset's own scope and sent back with the request. If detections
 * arrived (or went) while the question was open, the server refuses and reports the new count, and
 * the owner is asked again with that number. Nothing is deleted on a number nobody confirmed.
 */

/** The server refused the reset: this is how many detections there are now. */
export class ResetCountChanged extends Error {
    readonly count: number;

    constructor(count: number) {
        super('The number of detections changed before the reset.');
        this.name = 'ResetCountChanged';
        this.count = count;
    }
}

export type ResetQuestion =
    /** The first question: the dialog reads the count itself, so it cannot be confirmed before then. */
    | { kind: 'count'; read: () => Promise<number | null> }
    /** Asked after a refusal, with the count the server reported. */
    | { kind: 'changed'; count: number };

interface ResetSteps<T> {
    /** How many detections a reset would delete now, or null when the answer holds no number. */
    readCount: () => Promise<number | null>;
    ask: (question: ResetQuestion) => Promise<boolean>;
    /** Runs the reset for the count shown; null when the question stated no number. */
    reset: (expectedCount: number | null) => Promise<T>;
}

/** The reset's result, or null when the owner kept their history. */
export async function resetWithConfirmedCount<T>(steps: ResetSteps<T>): Promise<T | null> {
    let shown: number | null = null;
    let confirmed = await steps.ask({
        kind: 'count',
        read: async () => {
            shown = await steps.readCount();
            return shown;
        }
    });
    while (confirmed) {
        try {
            return await steps.reset(shown);
        } catch (error) {
            if (!(error instanceof ResetCountChanged)) throw error;
            shown = error.count;
            confirmed = await steps.ask({ kind: 'changed', count: error.count });
        }
    }
    return null;
}
