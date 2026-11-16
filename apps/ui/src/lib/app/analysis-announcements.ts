/**
 * One spoken account of card analyses for the whole page, through the app's shared polite
 * announcer. Starts that arrive together are said as one ("Analysing 30 visits"); the end is said
 * once, when every run in the batch has finished ("Analysis finished for 30 visits"). One visit is
 * named by its species when it is known, and counted ("1 visit") when it is not. A run is known
 * by its event and when it started, so a repeated completion or a renamed bird is never announced
 * twice, and a fresh run of the same visit is.
 */
export type AnalysisWords = {
    startedOne: (name: string) => string;
    startedMany: (count: number) => string;
    finishedOne: (name: string) => string;
    finishedMany: (count: number) => string;
};

type Options = {
    announce: (text: string) => void;
    /** The visit's species as the reader names it, or null when it is not known here. */
    nameOf: (eventId: string) => string | null;
    words: () => AnalysisWords;
    /** How long to gather starts and finishes that arrive together before speaking. */
    delayMs?: number;
    /** Runs `run` after `ms`, returning a cancel. A test passes its own clock. */
    schedule?: (run: () => void, ms: number) => () => void;
};

export type AnalysisAnnouncements = {
    started: (eventId: string, run: string | number) => void;
    finished: (eventId: string, run: string | number) => void;
};

const browserSchedule = (run: () => void, ms: number): (() => void) => {
    const timer = setTimeout(run, ms);
    return () => clearTimeout(timer);
};

export function createAnalysisAnnouncements({ announce, nameOf, words, delayMs = 400, schedule = browserSchedule }: Options): AnalysisAnnouncements {
    const seen = new Set<string>();
    const running = new Map<string, string>();
    let unannouncedStarts: string[] = [];
    let finishedInBatch: string[] = [];
    let cancel: (() => void) | null = null;

    const key = (eventId: string, run: string | number) => `${eventId}\u0000${run}`;

    function flush(): void {
        cancel = null;
        const say = words();
        if (running.size === 0 && finishedInBatch.length > 0) {
            // Every run in the batch has ended: one line for all of them, and nothing about starts.
            const name = finishedInBatch.length === 1 ? nameOf(finishedInBatch[0]) : null;
            announce(name ? say.finishedOne(name) : say.finishedMany(finishedInBatch.length));
            finishedInBatch = [];
            unannouncedStarts = [];
            return;
        }
        if (unannouncedStarts.length > 0) {
            const name = unannouncedStarts.length === 1 ? nameOf(unannouncedStarts[0]) : null;
            announce(name ? say.startedOne(name) : say.startedMany(unannouncedStarts.length));
            unannouncedStarts = [];
        }
    }

    function later(): void {
        cancel?.();
        cancel = schedule(flush, delayMs);
    }

    return {
        started(eventId, run) {
            const id = key(eventId, run);
            if (seen.has(id)) return;
            seen.add(id);
            running.set(id, eventId);
            unannouncedStarts.push(eventId);
            later();
        },
        finished(eventId, run) {
            const id = key(eventId, run);
            if (!running.has(id)) return;
            running.delete(id);
            finishedInBatch.push(eventId);
            if (running.size === 0) later();
        }
    };
}
