import { describe, expect, it } from 'vitest';
import { BIRD_FINDER_MODEL_IDS, birdFinderDevice, finderDeviceOptions, finderRunsOn, parseBirdFinder } from './bird-finder';

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

describe('finderRunsOn', () => {
    const finder = 'bird_crop_detector_accurate_rfdetr_nano';
    const base = {
        installed: true,
        evidence: [] as string[],
        accelerators: ['intel_gpu', 'intel_npu'],
        savedProvider: 'auto',
        check: null,
        modelId: finder,
        checkRunning: false,
    };
    const check = (state: string, extra: Record<string, unknown> = {}) => ({
        state, model_id: finder, providers: ['intel_npu'], reason: null, checked_at: '2026-11-12T08:30:00Z', ...extra,
    });

    it('says a finder that is not downloaded runs nowhere yet', () => {
        expect(finderRunsOn({ ...base, installed: false, evidence: ['intel_npu', 'cpu'] })).toEqual({ kind: 'not_downloaded' });
    });

    it('runs on the saved accelerator once it has passed, dated only by a check that measured it', () => {
        expect(finderRunsOn({ ...base, evidence: ['intel_gpu', 'intel_npu', 'cpu'], savedProvider: 'intel_npu' }))
            .toEqual({ kind: 'passed', provider: 'intel_npu', checkedAt: null });
        expect(finderRunsOn({ ...base, evidence: ['intel_npu', 'cpu'], savedProvider: 'intel_npu', check: check('succeeded') }))
            .toEqual({ kind: 'passed', provider: 'intel_npu', checkedAt: '2026-11-12T08:30:00Z' });
        // A startup check of another device says nothing about when this one passed.
        expect(finderRunsOn({ ...base, evidence: ['intel_gpu', 'cpu'], check: check('succeeded') }))
            .toEqual({ kind: 'passed', provider: 'intel_gpu', checkedAt: null });
    });

    it('on Automatic RF-DETR prefers a passing NPU before the GPU', () => {
        expect(finderRunsOn({ ...base, evidence: ['intel_gpu', 'intel_npu', 'cpu'] }))
            .toEqual({ kind: 'passed', provider: 'intel_npu', checkedAt: null });
    });

    it('mirrors the remaining backend recovery order and leaves other finders measured by latency', () => {
        expect(finderRunsOn({ ...base, evidence: ['cuda', 'cpu'] }))
            .toEqual({ kind: 'passed', provider: 'cuda', checkedAt: null });
        expect(finderRunsOn({ ...base, modelId: BIRD_FINDER_MODEL_IDS.yolox_tiny, evidence: ['intel_gpu', 'intel_npu', 'cpu'] }))
            .toEqual({ kind: 'passed', provider: 'intel_gpu', checkedAt: null });
    });

    it('names the failed check, its date and its measured cause when the finder fell back to the CPU', () => {
        const reason = 'The accelerators did not match the CPU on saved bird photos, so the finder stays on the CPU.';
        expect(finderRunsOn({ ...base, savedProvider: 'intel_npu', check: check('failed', { reason }) }))
            .toEqual({ kind: 'failed', devices: ['intel_npu'], checkedAt: '2026-11-12T08:30:00Z', cause: 'mismatch' });
        expect(finderRunsOn({ ...base, check: check('failed', { reason: 'The automatic finder check could not finish. Check devices for this finder to retry.' }) }))
            .toMatchObject({ kind: 'failed', cause: 'unfinished' });
    });

    it('gives no cause when the backend reports one it does not recognise', () => {
        expect(finderRunsOn({ ...base, check: check('failed', { reason: 'Something new.' }) })).toMatchObject({ kind: 'failed', cause: null });
        expect(finderRunsOn({ ...base, check: check('failed') })).toMatchObject({ kind: 'failed', cause: null });
    });

    it('falls back to the saved device, then the offered accelerators, when a failed check names no device', () => {
        expect(finderRunsOn({ ...base, savedProvider: 'intel_npu', check: check('failed', { providers: [] }) }))
            .toMatchObject({ kind: 'failed', devices: ['intel_npu'] });
        expect(finderRunsOn({ ...base, check: check('failed', { providers: [] }) }))
            .toMatchObject({ kind: 'failed', devices: ['intel_gpu', 'intel_npu'] });
    });

    it('lets passing evidence outrank an older failed startup check', () => {
        expect(finderRunsOn({ ...base, evidence: ['intel_npu', 'cpu'], savedProvider: 'intel_npu', check: check('failed') }))
            .toEqual({ kind: 'passed', provider: 'intel_npu', checkedAt: null });
    });

    it("ignores another finder's check", () => {
        expect(finderRunsOn({ ...base, check: check('failed', { model_id: 'bird_crop_detector_accurate_yolox_tiny' }) }))
            .toEqual({ kind: 'never_checked' });
    });

    it('reports a running check, started automatically or by the owner', () => {
        expect(finderRunsOn({ ...base, check: check('running', { providers: ['intel_gpu', 'intel_npu'] }) }))
            .toEqual({ kind: 'checking', devices: ['intel_gpu', 'intel_npu'] });
        expect(finderRunsOn({ ...base, checkRunning: true })).toEqual({ kind: 'checking', devices: ['intel_gpu', 'intel_npu'] });
    });

    it('reports a check that is waiting for photos or was interrupted', () => {
        expect(finderRunsOn({ ...base, check: check('waiting') })).toEqual({ kind: 'waiting', devices: ['intel_npu'] });
        expect(finderRunsOn({ ...base, check: check('interrupted') }))
            .toEqual({ kind: 'interrupted', devices: ['intel_npu'], checkedAt: '2026-11-12T08:30:00Z' });
    });

    it('says the CPU is the saved choice, never a fallback', () => {
        expect(finderRunsOn({ ...base, evidence: ['intel_npu', 'cpu'], savedProvider: 'cpu', check: check('failed') })).toEqual({ kind: 'cpu_chosen' });
    });

    it('says no accelerator has passed when none has, and that a host without one is CPU only', () => {
        expect(finderRunsOn(base)).toEqual({ kind: 'never_checked' });
        expect(finderRunsOn({ ...base, evidence: ['cpu'] })).toEqual({ kind: 'never_checked' });
        expect(finderRunsOn({ ...base, check: check('superseded') })).toEqual({ kind: 'never_checked' });
        expect(finderRunsOn({ ...base, accelerators: [] })).toEqual({ kind: 'cpu_only' });
        // A saved accelerator this host does not offer is still an unpassed choice, not "CPU only".
        expect(finderRunsOn({ ...base, accelerators: [], savedProvider: 'cuda' })).toEqual({ kind: 'never_checked' });
    });

    it('prefers stable reason codes over legacy sentences and does not invent a mismatch for inconclusive checks', () => {
        expect(finderRunsOn({ ...base, check: check('failed', { reason_code: 'unfinished', reason: 'did not match the CPU' }) }))
            .toMatchObject({ kind: 'failed', cause: 'unfinished' });
        expect(finderRunsOn({ ...base, check: check('failed', { reason_code: 'no_positive_baseline', reason: 'did not match the CPU' }) }))
            .toMatchObject({ kind: 'failed', cause: null });
    });
    it('mirrors RF-DETR NPU to verified GPU recovery while keeping the saved preference', () => {
        expect(finderRunsOn({ ...base, savedProvider: 'intel_npu', evidence: ['intel_gpu', 'cpu'], check: check('failed') }))
            .toEqual({ kind: 'passed', provider: 'intel_gpu', checkedAt: null });
    });
    it('uses actual execution evidence before the planned device', () => {
        expect(finderRunsOn({ ...base, savedProvider: 'intel_npu', evidence: ['intel_npu', 'intel_gpu', 'cpu'],
            execution: { model_id: finder, provider: 'intel_gpu', devices: ['GPU'], checked_at: '2026-11-15T00:00:00Z' } }))
            .toEqual({ kind: 'active', provider: 'intel_gpu', checkedAt: '2026-11-15T00:00:00Z' });
    });
    it("states the backend's own device choice for the running finder before deriving one", () => {
        const evidence = ['intel_npu', 'intel_gpu', 'cpu'];
        expect(finderRunsOn({ ...base, savedProvider: 'intel_npu', evidence, planned: { model_id: finder, provider: 'intel_gpu' } }))
            .toEqual({ kind: 'passed', provider: 'intel_gpu', checkedAt: null });
        expect(finderRunsOn({ ...base, savedProvider: 'intel_npu', evidence, check: check('failed'), planned: { model_id: finder, provider: 'cpu' } }))
            .toMatchObject({ kind: 'failed' });
        // A plan for the other, still-running finder says nothing about the one being chosen.
        expect(finderRunsOn({ ...base, savedProvider: 'intel_npu', evidence, planned: { model_id: 'other', provider: 'cpu' } }))
            .toEqual({ kind: 'passed', provider: 'intel_npu', checkedAt: null });
    });
    it('does not date current evidence using a passing check from an older runtime', () => {
        expect(finderRunsOn({ ...base, savedProvider: 'intel_npu', evidence: ['intel_npu'], check: check('succeeded', { runtime_current: false }) }))
            .toMatchObject({ kind: 'passed', checkedAt: null });
    });
});

describe('finderDeviceOptions', () => {
    const host = ['cpu', 'intel_cpu', 'intel_gpu', 'intel_npu'];

    it('lists the devices this host offers the finder and marks the ones without a passing check', () => {
        expect(finderDeviceOptions({ evidence: ['intel_gpu', 'cpu'], accelerators: ['intel_gpu', 'intel_npu'], hostProviders: host, chosen: 'auto', keepable: null }))
            .toEqual([
                { value: 'intel_cpu', passed: false, selectable: false },
                { value: 'intel_gpu', passed: true, selectable: true },
                { value: 'intel_npu', passed: false, selectable: false },
            ]);
    });

    it('keeps the saved device selectable without a passing check, because the server keeps an unchanged choice', () => {
        const options = finderDeviceOptions({ evidence: ['cpu'], accelerators: ['intel_gpu', 'intel_npu'], hostProviders: host, chosen: 'auto', keepable: 'intel_npu' });
        expect(options.find((option) => option.value === 'intel_npu')).toEqual({ value: 'intel_npu', passed: false, selectable: true });
        // The server refuses a newly chosen device that has not passed, so it is not offered as a choice.
        expect(options.find((option) => option.value === 'intel_gpu')).toEqual({ value: 'intel_gpu', passed: false, selectable: false });
    });

    it('keeps a chosen device in the list even when this host does not offer it', () => {
        expect(finderDeviceOptions({ evidence: [], accelerators: [], hostProviders: ['cpu'], chosen: 'cuda', keepable: 'cuda' }))
            .toEqual([{ value: 'cuda', passed: false, selectable: true }]);
        expect(finderDeviceOptions({ evidence: [], accelerators: [], hostProviders: ['cpu'], chosen: 'cpu', keepable: null })).toEqual([]);
    });
});
