interface RevisionFollower {
    /** Read now, whatever revision is already known: a view that just opened has read nothing. */
    start(): void;
    /** A revision was pushed; read again if it is new, after any read already in flight. */
    observe(revision: string): void;
    stop(): void;
}

/**
 * Keeps a detail reading in step with a pushed revision. A revision that arrives while a read is
 * in flight is not marked seen and dropped: one follow-up read is queued for it, since the read in
 * flight may have started before the change it names.
 */
export function followRevisions(read: () => Promise<unknown>, knownRevision: string | null): RevisionFollower {
    let seen = knownRevision;
    let reading = false;
    let again = false;
    let stopped = false;

    async function readNow(): Promise<void> {
        if (stopped) return;
        if (reading) {
            again = true;
            return;
        }
        reading = true;
        try {
            await read();
        } catch {
            // The reader reports its own failure; the next revision reads again.
        } finally {
            reading = false;
            if (again && !stopped) {
                again = false;
                void readNow();
            }
        }
    }

    return {
        start: () => void readNow(),
        observe(revision: string): void {
            if (revision === seen) return;
            seen = revision;
            void readNow();
        },
        stop(): void {
            stopped = true;
            again = false;
        }
    };
}
