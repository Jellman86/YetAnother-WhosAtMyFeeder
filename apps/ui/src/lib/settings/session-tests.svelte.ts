/**
 * The connection tests run during this visit. YA-WAMF keeps no test result anywhere, so the status
 * column states one only when it was run here, since the page loaded, with the time it ran; a
 * reload forgets it, and the column then says plainly that no result is kept.
 */
import { untrack } from 'svelte';
import type { SubsystemKey } from '../api/status';

/** The parts of the status a test speaks for: the connection test covers Frigate and the broker. */
export type TestedSubsystem = Extract<SubsystemKey, 'frigate' | 'mqtt' | 'audio' | 'notifications'>;

interface SessionTestResult {
    passed: boolean;
    /** Milliseconds since the epoch, when the test finished. */
    at: number;
    /** What was tested when the part has more than one test, such as the channel's name. */
    subject?: string;
    /** The section's unsaved changes the test ran with, as a signature; empty when there were none. */
    draft: string;
}

/** A result as the column may show it: one still describing the values on the page. */
export interface ShownTestResult {
    passed: boolean;
    at: number;
    subject?: string;
    /** Whether it ran with values on the page that are not saved yet. */
    unsaved: boolean;
}

/**
 * The section's unsaved changes for a part, as a signature: empty when there are none. The
 * Settings page provides it, since it holds the draft.
 */
type DraftSignature = (key: TestedSubsystem) => string;

/** Runs a test from the status column, as the section's own button does. */
type SessionTestRunner = () => void | Promise<void>;

/** Whether the status speaks for a part that has a test of its own. */
export function isTestedSubsystem(key: SubsystemKey): key is TestedSubsystem {
    return key === 'frigate' || key === 'mqtt' || key === 'audio' || key === 'notifications';
}

class SessionTests {
    results = $state<Partial<Record<TestedSubsystem, SessionTestResult>>>({});
    runners = $state<Partial<Record<TestedSubsystem, SessionTestRunner>>>({});

    #draft = $state<DraftSignature | null>(null);

    record(key: TestedSubsystem, passed: boolean, subject?: string, at: number = Date.now()): void {
        const draft = untrack(() => this.#draft?.(key) ?? '');
        this.results = { ...untrack(() => this.results), [key]: { passed, at, subject, draft } };
    }

    /** Lets results follow the page's unsaved changes, for as long as the returned function has not run. */
    trackDraft(signature: DraftSignature): () => void {
        this.#draft = signature;
        return () => {
            if (this.#draft === signature) this.#draft = null;
        };
    }

    /**
     * The result to show for a part, or null. A test runs with the values on the page, so a result
     * is shown only while those values stand: an edit, a Discard or a Save after it retires it.
     */
    shown(key: TestedSubsystem): ShownTestResult | null {
        const result = this.results[key];
        if (!result) return null;
        if ((this.#draft?.(key) ?? '') !== result.draft) return null;
        return { passed: result.passed, at: result.at, subject: result.subject, unsaved: result.draft !== '' };
    }

    /**
     * Offers a mounted section's test to the status column, for as long as it is shown; the
     * returned function withdraws it. A part whose test is not on the page is gone to instead.
     */
    provide(keys: readonly TestedSubsystem[], run: SessionTestRunner): () => void {
        // Read untracked: a caller's effect that read the runners it then writes would re-run itself
        // without end.
        const next = { ...untrack(() => this.runners) };
        for (const key of keys) next[key] = run;
        this.runners = next;
        return () => {
            const remaining = { ...untrack(() => this.runners) };
            for (const key of keys) if (remaining[key] === run) delete remaining[key];
            this.runners = remaining;
        };
    }
}

export const sessionTests = new SessionTests();
