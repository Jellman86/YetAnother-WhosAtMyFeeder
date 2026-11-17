import { describe, expect, it, vi } from 'vitest';
import { createRoutePrefetch } from './route-prefetch';

describe('createRoutePrefetch', () => {
    it("starts loading the page a path leads to, settings tabs included", () => {
        const settings = vi.fn(() => Promise.resolve());
        const species = vi.fn(() => Promise.resolve());
        const prefetch = createRoutePrefetch({ settings, leaderboard: species });
        prefetch('/species');
        prefetch('/settings/models');
        expect(species).toHaveBeenCalledTimes(1);
        expect(settings).toHaveBeenCalledTimes(1);
    });

    it('does nothing for a path with no page of its own', () => {
        const dashboard = vi.fn(() => Promise.resolve());
        createRoutePrefetch({ dashboard })('/no-such-page');
        expect(dashboard).not.toHaveBeenCalled();
    });

    it('lets a failed prefetch go quietly: opening the page reads it again', async () => {
        const failing = vi.fn(() => Promise.reject(new Error('chunk failed')));
        await expect(createRoutePrefetch({ about: failing })('/about')).resolves.toBeUndefined();
        expect(failing).toHaveBeenCalledTimes(1);
    });

    it('loads nothing ahead of time when the browser asks to save data', () => {
        const dashboard = vi.fn(() => Promise.resolve());
        createRoutePrefetch({ dashboard }, { saveData: () => true })('/');
        expect(dashboard).not.toHaveBeenCalled();
    });
});
