import { describe, expect, it } from 'vitest';
import { birdFinderDevice, birdFinderDeviceNote, parseBirdFinder } from './bird-finder';

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
            .toEqual({ provider: 'intel_gpu', checked: true, accelerators: [] });
    });

    it('reports CPU, unchecked, when this host has no current device evidence', () => {
        expect(birdFinderDevice({ provider_preference_order: [] })).toEqual({ provider: 'cpu', checked: false, accelerators: [] });
        expect(birdFinderDevice({})).toEqual({ provider: 'cpu', checked: false, accelerators: [] });
        expect(birdFinderDevice(undefined)).toEqual({ provider: 'cpu', checked: false, accelerators: [] });
    });

    it('does not read the evidence-free preferred provider field as a passed check', () => {
        expect(birdFinderDevice({ provider_preference_order: [], preferred_inference_provider: 'cuda' }))
            .toEqual({ provider: 'cpu', checked: false, accelerators: [] });
    });

    it('names the graphics and NPU devices the finder declares and this host offers', () => {
        const finder = {
            provider_preference_order: [],
            metadata: {
                supported_inference_providers: ['cpu', 'intel_cpu', 'intel_gpu', 'intel_npu'],
                candidate_inference_providers: ['cpu', 'intel_cpu', 'cuda', 'intel_gpu', 'intel_npu'],
            },
        };
        expect(birdFinderDevice(finder, ['intel_npu', 'cpu', 'intel_cpu', 'intel_gpu']).accelerators)
            .toEqual(['intel_gpu', 'intel_npu']);
        expect(birdFinderDevice(finder, ['cpu', 'cuda']).accelerators).toEqual(['cuda']);
        expect(birdFinderDevice(finder, ['cpu']).accelerators).toEqual([]);
        expect(birdFinderDevice(finder).accelerators).toEqual([]);
    });

    it("reads the finder's devices from the registry when the installed record carries none", () => {
        const registry = { supported_inference_providers: ['cpu', 'intel_gpu', 'intel_npu'], candidate_inference_providers: null };
        expect(birdFinderDevice({ provider_preference_order: [] }, ['cpu', 'intel_gpu', 'intel_npu'], registry).accelerators)
            .toEqual(['intel_gpu', 'intel_npu']);
    });
});

describe('birdFinderDeviceNote', () => {
    const finder = 'bird_crop_detector_accurate_yolox_tiny';
    const unchecked = { provider: 'cpu', checked: false, accelerators: ['intel_gpu', 'intel_npu'] };

    it('states a passed check before anything else', () => {
        expect(birdFinderDeviceNote({ provider: 'intel_npu', checked: true, accelerators: ['intel_npu'] }, null, finder))
            .toBe('checked');
    });

    it('says the CPU is the only choice when the host offers no device the finder declares', () => {
        expect(birdFinderDeviceNote({ provider: 'cpu', checked: false, accelerators: [] }, null, finder)).toBe('cpu_only');
    });

    it("reports the automatic re-check only for the finder it ran on", () => {
        expect(birdFinderDeviceNote(unchecked, { state: 'running', model_id: finder }, finder)).toBe('check_running');
        expect(birdFinderDeviceNote(unchecked, { state: 'failed', model_id: finder }, finder)).toBe('check_failed');
        expect(birdFinderDeviceNote(unchecked, { state: 'waiting', model_id: finder }, finder)).toBe('check_waiting');
        expect(birdFinderDeviceNote(unchecked, { state: 'running', model_id: 'other' }, finder)).toBe('until_checked');
        expect(birdFinderDeviceNote(unchecked, { state: 'idle', model_id: null }, finder)).toBe('until_checked');
    });
});
