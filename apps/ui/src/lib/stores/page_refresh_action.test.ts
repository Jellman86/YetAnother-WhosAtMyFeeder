import { beforeEach, describe, expect, it, vi } from 'vitest';

describe('PageRefreshAction', () => {
    beforeEach(() => {
        vi.resetModules();
    });

    it('exposes only the latest registered page refresh action', async () => {
        const { pageRefreshAction } = await import('./page_refresh_action.svelte');
        const first = vi.fn();
        const second = vi.fn();

        const unregisterFirst = pageRefreshAction.register(first);
        const unregisterSecond = pageRefreshAction.register(second);

        await pageRefreshAction.run();
        expect(first).not.toHaveBeenCalled();
        expect(second).toHaveBeenCalledTimes(1);

        unregisterFirst();
        expect(pageRefreshAction.available).toBe(true);

        unregisterSecond();
        expect(pageRefreshAction.available).toBe(false);
    });

    it('sets refreshing while an action is running', async () => {
        const { pageRefreshAction } = await import('./page_refresh_action.svelte');
        let release!: () => void;
        const pending = new Promise<void>((resolve) => {
            release = resolve;
        });

        pageRefreshAction.register(() => pending);
        const runPromise = pageRefreshAction.run();

        expect(pageRefreshAction.refreshing).toBe(true);
        release();
        await runPromise;
        expect(pageRefreshAction.refreshing).toBe(false);
    });
});
