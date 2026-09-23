import { describe, expect, it } from 'vitest';
import type { ClassifierStatus } from '../api/classifier';
import { classifierRuntimeState } from './classifier-runtime-state';

const status: ClassifierStatus = { loaded: true, error: null, labels_count: 10, enabled: true };

describe('classifier runtime presentation', () => {
    it('uses the current runtime even when saved settings still request in-process', () => {
        expect(classifierRuntimeState({ ...status, image_execution_mode: 'subprocess' }, 'in_process').executionMode)
            .toBe('subprocess');
    });
    it('does not present unsaved settings as the running runtime', () => {
        expect(classifierRuntimeState({ ...status, image_execution_mode: 'in_process' }, 'subprocess').executionMode)
            .toBe('in_process');
    });
    it('retains the restart advice after worker recovery', () => {
        expect(classifierRuntimeState({ ...status, native_runtime_quarantine: { status: 'recovered', restart_recommended: true } }, 'subprocess'))
            .toEqual({ executionMode: 'subprocess', restartRecommended: true, recovering: false });
    });
    it('distinguishes waiting for recovery from resumed classification', () => {
        expect(classifierRuntimeState({ ...status, native_runtime_quarantine: { status: 'recovering', restart_recommended: true } }, 'subprocess').recovering)
            .toBe(true);
    });
    it('supports older servers without claiming a recovery', () => {
        expect(classifierRuntimeState(null, 'in_process'))
            .toEqual({ executionMode: 'in_process', restartRecommended: false, recovering: false });
    });
});
