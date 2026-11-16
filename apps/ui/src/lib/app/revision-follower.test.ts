import { describe, expect, it, vi } from 'vitest';
import { followRevisions } from './revision-follower';

function deferred(): { promise: Promise<void>; resolve: () => void } {
    let resolve: () => void = () => undefined;
    const promise = new Promise<void>((done) => { resolve = done; });
    return { promise, resolve };
}

describe('followRevisions', () => {
    it('reads on entry even when the current revision is already known', async () => {
        const read = vi.fn(async () => undefined);
        const follower = followRevisions(read, 'rev-1');
        follower.start();
        follower.observe('rev-1');
        await Promise.resolve();
        expect(read).toHaveBeenCalledTimes(1);
    });

    it('reads again for a new revision, and not for one already seen', async () => {
        const read = vi.fn(async () => undefined);
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
        const read = vi.fn().mockReturnValueOnce(first.promise).mockResolvedValue(undefined);
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
        const read = vi.fn().mockReturnValueOnce(first.promise).mockResolvedValue(undefined);
        const follower = followRevisions(read, null);
        follower.start();
        follower.observe('rev-2');
        follower.stop();
        first.resolve();
        await Promise.resolve();
        await Promise.resolve();
        expect(read).toHaveBeenCalledTimes(1);
    });
});
