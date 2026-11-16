import { describe, expect, it, vi } from 'vitest';
import { followRevisions } from './revision-follower';
import { READ_RETRY_MS } from './retrying-reader';

function deferred(): { promise: Promise<boolean>; resolve: () => void } {
    let resolve: () => void = () => undefined;
    const promise = new Promise<boolean>((done) => { resolve = () => done(true); });
    return { promise, resolve };
}

describe('followRevisions', () => {
    it('reads on entry even when the current revision is already known', async () => {
        const read = vi.fn(async () => true);
        const follower = followRevisions(read, 'rev-1');
        follower.start();
        follower.observe('rev-1');
        await Promise.resolve();
        expect(read).toHaveBeenCalledTimes(1);
    });

    it('reads again for a new revision, and not for one already seen', async () => {
        const read = vi.fn(async () => true);
        const follower = followRevisions(read, 'rev-1');
        follower.start();
        await vi.waitFor(() => expect(read).toHaveBeenCalledTimes(1));
        follower.observe('rev-1');
        follower.observe('rev-2');
        await vi.waitFor(() => expect(read).toHaveBeenCalledTimes(2));
        follower.observe('rev-2');
        await Promise.resolve();
        expect(read).toHaveBeenCalledTimes(2);
    });

    it('queues one follow-up read for revisions that arrive while a read is in flight', async () => {
        const first = deferred();
        const read = vi.fn().mockReturnValueOnce(first.promise).mockResolvedValue(true);
        const follower = followRevisions(read, null);
        follower.start();
        follower.observe('rev-2');
        follower.observe('rev-3');
        expect(read).toHaveBeenCalledTimes(1);
        first.resolve();
        await vi.waitFor(() => expect(read).toHaveBeenCalledTimes(2));
        await Promise.resolve();
        expect(read).toHaveBeenCalledTimes(2);
    });

    it('stops reading once stopped, even for a queued follow-up', async () => {
        const first = deferred();
        const read = vi.fn().mockReturnValueOnce(first.promise).mockResolvedValue(true);
        const follower = followRevisions(read, null);
        follower.start();
        follower.observe('rev-2');
        follower.stop();
        first.resolve();
        await Promise.resolve();
        await Promise.resolve();
        expect(read).toHaveBeenCalledTimes(1);
    });

    it('retries a failed read with the shared backoff, and stops retrying once stopped', async () => {
        vi.useFakeTimers();
        try {
            const read = vi.fn(async () => false);
            const follower = followRevisions(read, 'rev-1');
            follower.observe('rev-2');
            await vi.advanceTimersByTimeAsync(0);
            expect(read).toHaveBeenCalledTimes(1);
            await vi.advanceTimersByTimeAsync(READ_RETRY_MS[0]);
            expect(read).toHaveBeenCalledTimes(2);
            follower.stop();
            await vi.advanceTimersByTimeAsync(10 * READ_RETRY_MS[READ_RETRY_MS.length - 1]);
            expect(read).toHaveBeenCalledTimes(2);
        } finally {
            vi.useRealTimers();
        }
    });
});
