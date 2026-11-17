import { describe, expect, it, vi } from 'vitest';
import { createRoutePrefetch, pointerMayPrefetch, prefersLessData } from './route-prefetch';

const media = (matching: string[]) => (query: string) => ({ matches: matching.includes(query) });

describe('createRoutePrefetch', () => {
    const plenty = () => false;

    it('starts loading the page a path leads to, settings tabs included', () => {
        const settings = vi.fn(() => Promise.resolve());
        const species = vi.fn(() => Promise.resolve());
        const prefetch = createRoutePrefetch({ settings, leaderboard: species }, { prefersLessData: plenty });
        prefetch('/species');
        prefetch('/settings/models');
        expect(species).toHaveBeenCalledTimes(1);
        expect(settings).toHaveBeenCalledTimes(1);
    });

    it('does nothing for a path with no page of its own', () => {
        const dashboard = vi.fn(() => Promise.resolve());
        createRoutePrefetch({ dashboard }, { prefersLessData: plenty })('/no-such-page');
        expect(dashboard).not.toHaveBeenCalled();
    });

    it('lets a failed prefetch go quietly: opening the page reads it again', async () => {
        const failing = vi.fn(() => Promise.reject(new Error('chunk failed')));
        await expect(createRoutePrefetch({ about: failing }, { prefersLessData: plenty })('/about')).resolves.toBeUndefined();
        expect(failing).toHaveBeenCalledTimes(1);
    });

    it('loads nothing ahead of time when the browser asks for less data', () => {
        const dashboard = vi.fn(() => Promise.resolve());
        createRoutePrefetch({ dashboard }, { prefersLessData: () => true })('/');
        expect(dashboard).not.toHaveBeenCalled();
    });
});

describe('prefersLessData', () => {
    it('is true under Save-Data', () => {
        expect(prefersLessData({ connection: { saveData: true }, matchMedia: media([]) })).toBe(true);
    });

    it('is true when the person prefers reduced data', () => {
        expect(prefersLessData({ matchMedia: media(['(prefers-reduced-data: reduce)']) })).toBe(true);
    });

    it('is false when neither is set, or the browser says nothing', () => {
        expect(prefersLessData({ connection: { saveData: false }, matchMedia: media([]) })).toBe(false);
        expect(prefersLessData({})).toBe(false);
    });
});

describe('pointerMayPrefetch', () => {
    const hovering = media(['(hover: hover)']);

    it('lets a mouse or pen that can hover prefetch', () => {
        expect(pointerMayPrefetch('mouse', hovering)).toBe(true);
        expect(pointerMayPrefetch('pen', hovering)).toBe(true);
    });

    it('never lets touch prefetch: a finger passing over a link while scrolling is not a choice', () => {
        expect(pointerMayPrefetch('touch', hovering)).toBe(false);
    });

    it('does not prefetch for a pointer on a device that cannot hover', () => {
        expect(pointerMayPrefetch('mouse', media([]))).toBe(false);
    });
});
