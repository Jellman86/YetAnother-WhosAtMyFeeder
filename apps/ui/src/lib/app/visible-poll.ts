/** The part of `document` a poll needs: whether the tab is hidden, and when that changes. */
export interface PollDocument {
    readonly hidden: boolean;
    addEventListener(type: 'visibilitychange', listener: () => void): void;
    removeEventListener(type: 'visibilitychange', listener: () => void): void;
}

interface VisiblePollOptions {
    /** One reading. A failure is the reader's to report; the poll carries on at its cadence. */
    read: () => Promise<unknown> | unknown;
    /** The wait before the next reading, asked after each one so it can follow what was just read. */
    delayMs: () => number;
    /** False when the caller has just read and only wants the repeats. */
    readAtStart?: boolean;
    tab?: PollDocument;
}

/**
 * Keeps one reading current while someone can see it: reads, waits the cadence, reads again. While
 * the tab is hidden it reads nothing and holds no timer; when the tab is shown it reads once
 * straight away and resumes. Reads never overlap: a read still in flight when the tab is shown
 * again is followed by a fresh one as soon as it ends, because the reader may have abandoned it
 * when the tab was hidden. Returns the function that stops it for good.
 */
export function startVisiblePoll({ read, delayMs, readAtStart = true, tab = document }: VisiblePollOptions): () => void {
    let stopped = false;
    let reading = false;
    let readAgainWhenDone = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    function cancelTimer(): void {
        if (timer !== null) clearTimeout(timer);
        timer = null;
    }

    function scheduleNext(): void {
        cancelTimer();
        if (stopped || tab.hidden) return;
        timer = setTimeout(() => void readNow(), delayMs());
    }

    async function readNow(): Promise<void> {
        cancelTimer();
        if (stopped || reading || tab.hidden) return;
        reading = true;
        try {
            await read();
        } catch {
            // The reader reports its own failures; a failed reading must not end the poll.
        } finally {
            reading = false;
            if (readAgainWhenDone && !stopped && !tab.hidden) {
                readAgainWhenDone = false;
                void readNow();
            } else {
                scheduleNext();
            }
        }
    }

    function followVisibility(): void {
        if (tab.hidden) {
            cancelTimer();
            readAgainWhenDone = false;
        } else if (reading) {
            readAgainWhenDone = true;
        } else {
            void readNow();
        }
    }

    tab.addEventListener('visibilitychange', followVisibility);
    if (readAtStart) void readNow();
    else scheduleNext();

    return (): void => {
        stopped = true;
        cancelTimer();
        tab.removeEventListener('visibilitychange', followVisibility);
    };
}
