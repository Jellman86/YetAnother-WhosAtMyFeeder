import { describe, expect, it } from 'vitest';
import { GARDEN_CHECK_MODEL, modelActivityStore } from './model_activity.svelte';

describe('work this app has started on a model, shared by every surface', () => {
    it('has no phase for a model nothing is being done to', () => {
        expect(modelActivityStore.phase('small_birds')).toBeNull();
        expect(modelActivityStore.phase(null)).toBeNull();
    });

    it('records the phase for one model without touching another, and forgets it when the work ends', () => {
        modelActivityStore.set('small_birds', 'downloading');
        modelActivityStore.set(GARDEN_CHECK_MODEL, 'downloading');
        expect(modelActivityStore.phase('small_birds')).toBe('downloading');
        modelActivityStore.set('small_birds', 'validating');
        expect(modelActivityStore.phase('small_birds')).toBe('validating');
        expect(modelActivityStore.phase(GARDEN_CHECK_MODEL)).toBe('downloading');
        modelActivityStore.set('small_birds', null);
        modelActivityStore.set(GARDEN_CHECK_MODEL, null);
        expect(modelActivityStore.phase('small_birds')).toBeNull();
        expect(modelActivityStore.phase(GARDEN_CHECK_MODEL)).toBeNull();
    });
});
