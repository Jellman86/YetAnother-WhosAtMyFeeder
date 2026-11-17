import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { DeviceMatrix } from '../api/model_eval';

const api = vi.hoisted(() => ({
    startModelEvalRun: vi.fn(),
    listModelEvalRuns: vi.fn(),
    getModelEvalRun: vi.fn(),
    getModelEvalDeviceMatrix: vi.fn()
}));
vi.mock('../api/model_eval', () => api);

const { DeviceCheck, deviceCheckProblemText } = await import('./device-check.svelte');

const MATRIX = { devices: ['CPU'], providers: ['cpu', 'intel_gpu'], models: {}, crop_detectors: {} } as unknown as DeviceMatrix;

/** Lets the check's first poll run and every promise it awaits settle. */
async function poll(): Promise<void> {
    await vi.advanceTimersByTimeAsync(2000);
}

describe('the device check shared by the model list and Hardware', () => {
    beforeEach(() => {
        vi.useFakeTimers();
        // The check pauses while the page is hidden; here it is always shown.
        vi.stubGlobal('document', { hidden: false });
        api.startModelEvalRun.mockResolvedValue({ run_id: 'run-1' });
        api.listModelEvalRuns.mockResolvedValue({ active: null });
        api.getModelEvalRun.mockResolvedValue({ finished_at: '2026-11-17T12:00:00Z', error_code: null });
        api.getModelEvalDeviceMatrix.mockResolvedValue(MATRIX);
    });

    afterEach(() => {
        vi.unstubAllGlobals();
        vi.useRealTimers();
        vi.clearAllMocks();
    });

    it('opens its dialog and reports running from the moment it starts, whichever control started it', async () => {
        const check = new DeviceCheck();
        const done = check.run(['yolox_tiny']);
        expect(check.running).toBe(true);
        expect(check.dialogOpen).toBe(true);
        // A finder check covers that model only, and never every model.
        await vi.waitFor(() => expect(api.startModelEvalRun).toHaveBeenCalledWith({ sweep_devices: true, compat_only: true, sweep_all_models: false, model_ids: ['yolox_tiny'] }));
        await poll();
        await done;
        expect(check.running).toBe(false);
        expect(check.matrix).toEqual(MATRIX);
        expect(check.problem).toBeNull();
    });

    it('reads the runtime back afterwards, and says so when it could not', async () => {
        const refresh = vi.fn().mockResolvedValue(false);
        const check = new DeviceCheck(refresh);
        const done = check.run();
        await poll();
        await done;
        expect(refresh).toHaveBeenCalledTimes(1);
        expect(check.runtimeRefreshFailed).toBe(true);
    });

    it('tests every model only when asked to, for a check of every installed model', async () => {
        const check = new DeviceCheck();
        check.allModels = true;
        const done = check.run();
        await vi.waitFor(() => expect(api.startModelEvalRun).toHaveBeenCalledWith(expect.objectContaining({ sweep_all_models: true, model_ids: [] })));
        await poll();
        await done;
    });

    it('names why a finished check has no results, rather than showing an empty one', async () => {
        api.getModelEvalDeviceMatrix.mockResolvedValue(null);
        const check = new DeviceCheck();
        const done = check.run();
        await poll();
        await done;
        expect(check.matrix).toBeNull();
        expect(check.problem).toEqual({ kind: 'results_unavailable' });
        const translate = (key: string, options?: { default?: string }) => options?.default ?? key;
        expect(deviceCheckProblemText(check.problem ?? { kind: 'results_unavailable' }, translate)).toBe('Compatibility results could not be loaded. Please retry.');
    });

    it('repeats the same models on Retry', async () => {
        const check = new DeviceCheck();
        const first = check.run(['yolox_tiny']);
        await poll();
        await first;
        const again = check.retry();
        await vi.waitFor(() => expect(api.startModelEvalRun).toHaveBeenLastCalledWith(expect.objectContaining({ model_ids: ['yolox_tiny'] })));
        await poll();
        await again;
    });

    it('stops listening when the section goes away, so a late answer changes nothing', async () => {
        const check = new DeviceCheck();
        void check.run();
        await vi.waitFor(() => expect(api.startModelEvalRun).toHaveBeenCalled());
        check.dispose();
        await poll();
        expect(api.listModelEvalRuns).not.toHaveBeenCalled();
        expect(check.matrix).toBeNull();
    });
});
