import { expect, it, vi } from 'vitest';
import { createEventMetadataRefresh } from './event-metadata-refresh';
import type { EventFilters } from '../api';

const filters = (camera: string): EventFilters => ({ species: [{ value: camera, display_name: camera }], cameras: [camera] } as EventFilters);

it('replaces guest choices with newly unhidden species and cameras using a fresh request', async () => {
    let state = filters('Old species');
    const fetch = vi.fn().mockResolvedValue(filters('New species'));
    const loader = createEventMetadataRefresh({ fetch, apply: (value) => { state = value; }, clear: () => { state = filters(''); }, isGuest: () => true });
    await loader.load(true);
    expect(fetch).toHaveBeenCalledWith({ forceRefresh: true });
    expect(state.species[0].value).toBe('New species');
    expect(state.cameras).toEqual(['New species']);
});

it('clears invalidated guest choices on failure and rejects a late earlier response', async () => {
    let state: EventFilters | null = filters('Private camera');
    let release: (value: EventFilters) => void = () => undefined;
    const fetch = vi.fn().mockImplementationOnce(() => new Promise((resolve) => { release = resolve; }))
        .mockRejectedValueOnce(new Error('503'));
    const loader = createEventMetadataRefresh({ fetch, apply: (value) => { state = value; }, clear: () => { state = null; }, isGuest: () => true });
    const oldRequest = loader.load(false);
    await loader.load(true);
    expect(state).toBeNull();
    release(filters('Private camera'));
    await oldRequest;
    expect(state).toBeNull();
});

it('preserves owner options during a transient metadata failure', async () => {
    const apply = vi.fn();
    const clear = vi.fn();
    const loader = createEventMetadataRefresh({ fetch: vi.fn().mockRejectedValue(new Error('503')), apply, clear, isGuest: () => false });
    await loader.load(true);
    expect(clear).not.toHaveBeenCalled();
    expect(apply).not.toHaveBeenCalled();
});
