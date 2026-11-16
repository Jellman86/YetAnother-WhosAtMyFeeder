import type { PollDocument } from './visible-poll';

interface LiveReadingOptions {
    /**
     * One reading. `announced` says it answers a change the stream announced (or one that may have
     * gone unannounced), so the reader can also read what that change concerns. Resolve `false`, or
     * throw, when nothing was read: the reading is then not taken as fresh. Reporting the failure is
     * the reader's.
     */
    read: (reason: { announced: boolean }) => Promise<unknown> | unknown;
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

/** A reconnect reads again no sooner than this after the last read, however often the stream flaps. */
export const RECONNECT_MIN_MS = 10_000;

export interface LiveReading {
    /** The live stream announced a change to this reading. */
    changed(): void;
    /**
     * The view read this itself (a first read, a read after an edit): count it, so a failure is
     * retried and a success restarts the quiet interval. Ignored while a read of its own is running.
     */
    report(fresh: boolean): void;
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
    let reconnected = false;
    // Reads that failed in a row; each one doubles the wait before the next, up to the quiet interval.
    let failures = 0;
    let wasLive = live();
    // A first connect follows the first read; only a reconnect can have missed an announcement.
    let everLive = wasLive;
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
        let wait: number;
        if (failures > 0) wait = Math.min(gap * 2 ** (failures - 1), quietMs);
        else if (!live()) wait = gap;
        else if (reconnected) wait = Math.min(RECONNECT_MIN_MS, gap);
        else wait = announced ? gap : quietMs;
        const due = lastReadAt + wait;
        timer = setTimeout(() => void readNow(), Math.max(0, due - now()));
    }

    async function readNow(): Promise<void> {
        cancelTimer();
        if (stopped || reading || tab.hidden) return;
        reading = true;
        const answersAnnouncement = announced || reconnected;
        announced = false;
        reconnected = false;
        lastReadAt = now();
        let fresh = false;
        try {
            fresh = (await read({ announced: answersAnnouncement })) !== false;
        } catch {
            // The reader reports its own failures; here a failed read only means it is not fresh.
        } finally {
            settle(fresh);
            reading = false;
            plan();
        }
    }

    /** A failed read is not fresh: it is retried after a backoff, not after the quiet interval. */
    function settle(fresh: boolean): void {
        if (fresh) {
            failures = 0;
        } else {
            failures += 1;
            announced = true;
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
            if (!isLive) {
                // Losing the stream may have lost an announcement with it.
                announced = true;
            } else if (everLive) {
                // Back after a gap that announcements did not cover: read again, but no sooner than
                // the minimum interval after the last read, so a flapping stream cannot cause a storm.
                reconnected = true;
            }
            everLive ||= isLive;
            plan();
        },
        report(fresh: boolean): void {
            if (stopped || reading) return;
            lastReadAt = now();
            reconnected = false;
            if (fresh) announced = false;
            settle(fresh);
            plan();
        },
        stop(): void {
            stopped = true;
            cancelTimer();
            tab.removeEventListener('visibilitychange', followVisibility);
        }
    };
}
