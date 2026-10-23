import { describe, expect, it } from 'vitest';
import { birdFinderDevice, parseBirdFinder } from './bird-finder';

describe('parseBirdFinder', () => {
    it('keeps the two saved finders', () => {
        expect(parseBirdFinder('yolox_tiny')).toBe('yolox_tiny');
        expect(parseBirdFinder('rfdetr_nano')).toBe('rfdetr_nano');
    });

    it('reads a missing or unknown value as the YOLOX-Tiny default, like the backend', () => {
        expect(parseBirdFinder(undefined)).toBe('yolox_tiny');
        expect(parseBirdFinder(null)).toBe('yolox_tiny');
        expect(parseBirdFinder('RFDETR_NANO')).toBe('yolox_tiny');
    });
});

describe('birdFinderDevice', () => {
    // Mirrors bird_crop_service: the first provider in the host's current
    // preference order, otherwise CPU.
    it('reports the first provider in the current host preference order', () => {
        expect(birdFinderDevice({ provider_preference_order: ['intel_gpu', 'cpu'] }))
            .toEqual({ provider: 'intel_gpu', checked: true });
    });

    it('reports CPU, unchecked, when this host has no current device evidence', () => {
        expect(birdFinderDevice({ provider_preference_order: [] })).toEqual({ provider: 'cpu', checked: false });
        expect(birdFinderDevice({})).toEqual({ provider: 'cpu', checked: false });
        expect(birdFinderDevice(undefined)).toEqual({ provider: 'cpu', checked: false });
    });

    it('does not read the evidence-free preferred provider field as a passed check', () => {
        expect(birdFinderDevice({ provider_preference_order: [], preferred_inference_provider: 'cuda' }))
            .toEqual({ provider: 'cpu', checked: false });
    });
});
