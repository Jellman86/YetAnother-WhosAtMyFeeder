import { describe, expect, it, vi } from 'vitest';

import { lazyComponent } from './lazy-component';

describe('lazyComponent', () => {
    it('shares one in-flight and resolved import', async () => {
        const pageModule = { default: vi.fn() };
        const importer = vi.fn().mockResolvedValue(pageModule);
        const load = lazyComponent(importer);

        const first = load();
        const second = load();

        expect(first).toBe(second);
        await expect(first).resolves.toBe(pageModule);
        await expect(load()).resolves.toBe(pageModule);
        expect(importer).toHaveBeenCalledTimes(1);
    });

    it('forgets a rejected import so an explicit retry can recover', async () => {
        const failure = new Error('temporary chunk fetch failure');
        const pageModule = { default: vi.fn() };
        const importer = vi.fn()
            .mockRejectedValueOnce(failure)
            .mockResolvedValueOnce(pageModule);
        const load = lazyComponent(importer);

        await expect(load()).rejects.toBe(failure);
        await expect(load()).resolves.toBe(pageModule);
        expect(importer).toHaveBeenCalledTimes(2);
    });
});
