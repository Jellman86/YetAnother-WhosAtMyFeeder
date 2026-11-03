import { describe, expect, it } from 'vitest';
import { gardenBetaSummary, type GardenBetaInput } from './beta-features';
import type { GardenModelRow } from './garden-models';

function row(role: GardenModelRow['role'], requirement: GardenModelRow['requirement'], state: GardenModelRow['state']): GardenModelRow {
    return {
        role,
        install: role === 'motion_detector' ? { kind: 'motion' } : { kind: 'speciesnet', variant: role === 'automatic_check' ? '4.0.3a' : '4.0.3b' },
        requirement,
        state,
        sizeBytes: 1
    };
}

const ready: GardenModelRow[] = [
    row('automatic_check', 'required', 'ready'),
    row('species_suggestions', 'optional', 'missing'),
    row('motion_detector', 'optional', 'missing')
];

const on: GardenBetaInput = {
    enabled: true,
    savedEnabled: true,
    cameras: ['patio', 'front'],
    models: ready,
    country: 'GBR',
    lastProvider: 'intel_npu'
};

describe('gardenBetaSummary', () => {
    it('says only "Off" while the beta is off and saved off, with nothing to do', () => {
        expect(gardenBetaSummary({ ...on, enabled: false, savedEnabled: false })).toEqual({
            parts: [{ kind: 'off' }],
            steps: [],
            attention: false
        });
    });

    it('says a staged switch-off takes effect on Apply, and asks nothing else of the owner', () => {
        const summary = gardenBetaSummary({ ...on, enabled: false, cameras: [] });
        expect(summary.parts).toEqual([{ kind: 'off_after_apply' }]);
        expect(summary.steps).toEqual([]);
        expect(summary.attention).toBe(false);
    });

    it('reads a ready Garden as on, its camera count and the device its last check measured', () => {
        expect(gardenBetaSummary(on)).toEqual({
            parts: [{ kind: 'on' }, { kind: 'cameras', count: 2 }, { kind: 'device', provider: 'intel_npu' }],
            steps: [],
            attention: false
        });
    });

    it('names no device until a check has reported one', () => {
        expect(gardenBetaSummary({ ...on, lastProvider: null }).parts).toEqual([{ kind: 'on' }, { kind: 'cameras', count: 2 }]);
    });

    it('flags a required model that is not downloaded, and only a required one', () => {
        const models = [row('automatic_check', 'required', 'missing'), row('species_suggestions', 'optional', 'missing'), row('motion_detector', 'required', 'missing')];
        const summary = gardenBetaSummary({ ...on, models, lastProvider: null });
        expect(summary.parts).toEqual([{ kind: 'on' }, { kind: 'cameras', count: 2 }, { kind: 'model_missing' }]);
        expect(summary.steps).toEqual([
            { kind: 'download_model', role: 'automatic_check' },
            { kind: 'download_model', role: 'motion_detector' }
        ]);
        expect(summary.attention).toBe(true);
    });

    it('never claims a model is missing while its status is unknown or unavailable', () => {
        const models = [row('automatic_check', 'required', 'unknown'), row('motion_detector', 'required', 'unavailable')];
        const summary = gardenBetaSummary({ ...on, models, country: undefined });
        expect(summary.parts).not.toContainEqual({ kind: 'model_missing' });
        expect(summary.steps).toEqual([]);
    });

    it('asks for a camera when none watches for Garden animals', () => {
        const summary = gardenBetaSummary({ ...on, cameras: [] });
        expect(summary.parts).toEqual([{ kind: 'on' }, { kind: 'cameras', count: 0 }, { kind: 'device', provider: 'intel_npu' }]);
        expect(summary.steps).toEqual([{ kind: 'choose_camera' }]);
        expect(summary.attention).toBe(true);
    });

    it('asks for a location only once Garden has reported that it has no country', () => {
        expect(gardenBetaSummary({ ...on, country: undefined }).steps).toEqual([]);
        const summary = gardenBetaSummary({ ...on, country: null });
        expect(summary.parts).toContainEqual({ kind: 'no_country' });
        expect(summary.steps).toEqual([{ kind: 'set_location' }]);
        expect(summary.attention).toBe(true);
    });

    it('orders next steps as setup runs: camera, models, then location', () => {
        const models = [row('automatic_check', 'required', 'missing')];
        expect(gardenBetaSummary({ ...on, cameras: [], models, country: null }).steps.map(step => step.kind)).toEqual([
            'choose_camera',
            'download_model',
            'set_location'
        ]);
    });

    it('before Apply, asks to apply and ignores model and country readings the server has not made', () => {
        const summary = gardenBetaSummary({ ...on, savedEnabled: false, models: [row('automatic_check', 'required', 'missing')], country: null });
        expect(summary.parts).toEqual([{ kind: 'on_after_apply' }, { kind: 'cameras', count: 2 }]);
        expect(summary.steps).toEqual([{ kind: 'apply' }]);
        // Apply is already called out by the save bar; a pending Apply alone needs no amber.
        expect(summary.attention).toBe(false);
    });

    it('before Apply with no camera, still asks for the camera first', () => {
        const summary = gardenBetaSummary({ ...on, savedEnabled: false, cameras: [] });
        expect(summary.steps).toEqual([{ kind: 'choose_camera' }, { kind: 'apply' }]);
        expect(summary.attention).toBe(true);
    });
});
