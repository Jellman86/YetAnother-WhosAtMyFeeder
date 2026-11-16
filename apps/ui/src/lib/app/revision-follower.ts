import { createRetryingReader } from './retrying-reader';

interface RevisionFollower {
    /** Read now, whatever revision is already known: a view that just opened has read nothing. */
    start(): void;
    /** A revision was pushed; read again if it is new, after any read already in flight. */
    observe(revision: string): void;
    /** The view closed: no more reads, and no pending retry. */
    stop(): void;
}

/**
 * Keeps a detail reading in step with a pushed revision. A revision that arrives while a read is
 * in flight is not marked seen and dropped: one follow-up read is queued for it, since the read in
 * flight may have started before the change it names. A failed read is retried with the shared
 * capped backoff until one succeeds or the view stops following.
 */
export function followRevisions(read: () => Promise<boolean>, knownRevision: string | null): RevisionFollower {
    let seen = knownRevision;
    let stopped = false;
    const reader = createRetryingReader({ read, active: () => !stopped });

    return {
        start(): void {
            if (!stopped) reader.request();
        },
        observe(revision: string): void {
            if (stopped || revision === seen) return;
            seen = revision;
            reader.request();
        },
        stop(): void {
            stopped = true;
            reader.cancel();
        }
    };
}
