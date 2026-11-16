import type { PollDocument } from './visible-poll';

interface LiveReadingOptions {
    /** One reading. A failure is the reader's to report; the reading carries on. */
    read: () => Promise<unknown> | unknown;
    /** Whether the live stream is connected and announces every change to this reading. */
    live: () => boolean;
    /**
     * The reading's own poll while the stream does not cover it. It is also the shortest gap between
     * two reads that announcements cause, so a busy feeder costs no more than polling did.
     */
    pollMs: () => number;
    /**
     * The safety read while the stream covers it, for what no announcement says: a rolling window
     * moving on, or a message lost on the way.
     */
    quietMs: number;
    /** False when the caller has just read and only wants what follows. */
    readAtStart?: boolean;
    tab?: PollDocument;
    now?: () => number;
}

export interface LiveReading {
    /** The live stream announced a change to this reading. */
    changed(): void;
    /** `live()` may have changed: re-plan the next read. */
    liveChanged(): void;
    stop(): void;
}

/**
 * Keeps one reading current from the live stream where it can, and by polling where it cannot.
 *
 * With the stream connected, a reading is taken when the stream announces a change (at once after a
 * quiet spell, at most once per `pollMs` in a burst) and otherwise only every `quietMs`. Without the
 * stream it polls every `pollMs`, and losing the stream reads at once, since a change may have gone
 * unannounced. As with `startVisiblePoll`, nothing is read and no timer is held while the tab is
 * hidden, showing the tab reads once, and reads never overlap.
 */
export function startLiveReading({
    read,
    live,
    pollMs,
    quietMs,
    readAtStart = true,
    tab = document,
    now = () => Date.now()
}: LiveReadingOptions): LiveReading {
    let stopped = false;
    let reading = false;
    let announced = false;
    let wasLive = live();
    let lastReadAt = now();
    let timer: ReturnType<typeof setTimeout> | null = null;

    function cancelTimer(): void {
        if (timer !== null) clearTimeout(timer);
        timer = null;
    }

    function plan(): void {
        cancelTimer();
        if (stopped || reading || tab.hidden) return;
        const gap = pollMs();
        const due = live()
            ? lastReadAt + (announced ? gap : quietMs)
            : lastReadAt + gap;
        timer = setTimeout(() => void readNow(), Math.max(0, due - now()));
    }

    async function readNow(): Promise<void> {
        cancelTimer();
        if (stopped || reading || tab.hidden) return;
        reading = true;
        announced = false;
        lastReadAt = now();
        try {
            await read();
        } catch {
            // The reader reports its own failures; a failed reading must not end the cycle.
        } finally {
            reading = false;
            plan();
        }
    }

    function followVisibility(): void {
        if (tab.hidden) {
            cancelTimer();
        } else {
            lastReadAt = Number.NEGATIVE_INFINITY;
            plan();
        }
    }

    tab.addEventListener('visibilitychange', followVisibility);
    if (readAtStart) void readNow();
    else plan();

    return {
        changed(): void {
            if (stopped) return;
            announced = true;
            plan();
        },
        liveChanged(): void {
            if (stopped) return;
            const isLive = live();
            // Only a real change counts: a view reports the state as it mounts, often unchanged.
            if (isLive === wasLive) return;
            wasLive = isLive;
            // Losing the stream may have lost an announcement with it.
            if (!isLive) announced = true;
            plan();
        },
        stop(): void {
            stopped = true;
            cancelTimer();
            tab.removeEventListener('visibilitychange', followVisibility);
        }
    };
}
