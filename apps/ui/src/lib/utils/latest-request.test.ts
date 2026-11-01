import { describe, expect, it } from 'vitest';
import { createLatestRequest } from './latest-request';

function deferred<T>(): { promise: Promise<T>; resolve: (value: T) => void; reject: (reason: unknown) => void } {
    let resolve: (value: T) => void = () => undefined;
    let reject: (reason: unknown) => void = () => undefined;
    const promise = new Promise<T>((done, fail) => { resolve = done; reject = fail; });
    return { promise, resolve, reject };
}

/** The shape every page load follows: claim a ticket, read, apply only while current. */
function page() {
    const latest = createLatestRequest();
    const state = { rows: [] as string[], loading: false, error: null as string | null };
    async function load(read: Promise<string[]>): Promise<void> {
        const ticket = latest.begin();
        state.loading = true;
        state.error = null;
        try {
            const rows = await read;
            if (!ticket.isCurrent()) return;
            state.rows = rows;
        } catch (failure) {
            if (!ticket.isCurrent()) return;
            state.error = failure instanceof Error ? failure.message : String(failure);
        } finally {
            if (ticket.isCurrent()) state.loading = false;
        }
    }
    /** What the page does when a visitor's public history changes under it. */
    function forgetForVisitor(): void {
        latest.supersede();
        state.rows = [];
        state.loading = true;
    }
    return { state, load, forgetForVisitor };
}

describe('createLatestRequest', () => {
    it('keeps the newer read when an older one resolves after it', async () => {
        const subject = page();
        const older = deferred<string[]>();
        const newer = deferred<string[]>();
        const first = subject.load(older.promise);
        const second = subject.load(newer.promise);

        newer.resolve(['page 2']);
        await second;
        expect(subject.state).toMatchObject({ rows: ['page 2'], loading: false });

        older.resolve(['page 1']);
        await first;
        expect(subject.state).toMatchObject({ rows: ['page 2'], loading: false });
    });

    it('does not end the newer read\'s loading state when the older read settles first', async () => {
        const subject = page();
        const older = deferred<string[]>();
        const newer = deferred<string[]>();
        const first = subject.load(older.promise);
        const second = subject.load(newer.promise);

        older.resolve(['page 1']);
        await first;
        expect(subject.state).toMatchObject({ rows: [], loading: true });

        newer.resolve(['page 2']);
        await second;
        expect(subject.state).toMatchObject({ rows: ['page 2'], loading: false });
    });

    it('does not report a superseded read\'s failure over the current page', async () => {
        const subject = page();
        const older = deferred<string[]>();
        const first = subject.load(older.promise);
        await subject.load(Promise.resolve(['current']));

        older.reject(new Error('offline'));
        await first;
        expect(subject.state).toEqual({ rows: ['current'], loading: false, error: null });
    });

    it('drops owner rows still in flight when access changes to a visitor before the new read starts', async () => {
        const subject = page();
        const ownerRead = deferred<string[]>();
        const owner = subject.load(ownerRead.promise);

        subject.forgetForVisitor();
        ownerRead.resolve(['private owner row']);
        await owner;
        expect(subject.state).toMatchObject({ rows: [], loading: true });

        await subject.load(Promise.resolve(['public row']));
        expect(subject.state).toMatchObject({ rows: ['public row'], loading: false });
    });

    it('treats each ticket independently of the others', () => {
        const latest = createLatestRequest();
        const first = latest.begin();
        expect(first.isCurrent()).toBe(true);
        const second = latest.begin();
        expect([first.isCurrent(), second.isCurrent()]).toEqual([false, true]);
        latest.supersede();
        expect(second.isCurrent()).toBe(false);
    });
});
