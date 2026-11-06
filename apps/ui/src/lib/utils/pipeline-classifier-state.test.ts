import { describe, expect, it } from 'vitest';
import type { ClassifierStatus } from '../api/classifier';
import { pipelineClassifierState } from './pipeline-classifier-state';

// What /api/classifier/status sends on a default install: image work runs in
// worker processes, so there is no top-level `loaded` and `models` is empty.
const subprocessStatus = {
    image_execution_mode: 'subprocess',
    runtime_source: 'worker',
    labels_count: 965,
    active_model_id: 'rope_vit_b14_inat21',
    effective_model_id: 'rope_vit_b14_inat21',
    inference_health: { status: 'ok' },
    models: {}
} satisfies ClassifierStatus & { models: Record<string, never> };

describe('pipelineClassifierState', () => {
    it('reads a classifying subprocess install as loaded without a loaded flag', () => {
        expect(pipelineClassifierState(subprocessStatus)).toBe('loaded');
    });

    it('falls back to the configured model id when no effective model is reported', () => {
        expect(pipelineClassifierState({ ...subprocessStatus, effective_model_id: null })).toBe('loaded');
    });

    it('says the worker loads on first detection when the pool has not started', () => {
        expect(pipelineClassifierState({ ...subprocessStatus, runtime_source: 'planned' })).toBe('standby');
    });

    it('asks for a check when inference health is degraded or unhealthy', () => {
        expect(pipelineClassifierState({ ...subprocessStatus, inference_health: { status: 'degraded' } })).toBe('check');
        expect(pipelineClassifierState({ ...subprocessStatus, inference_health: { status: 'unhealthy' } })).toBe('check');
    });

    it('trusts an explicit loaded flag from an in-process install', () => {
        const inProcess = { loaded: true, error: null, labels_count: 10, enabled: true, image_execution_mode: 'in_process' } as ClassifierStatus;
        expect(pipelineClassifierState(inProcess)).toBe('loaded');
        expect(pipelineClassifierState({ ...inProcess, loaded: false })).toBe('check');
    });

    it('never reads an idle subprocess model flag as a failure', () => {
        expect(pipelineClassifierState({ ...subprocessStatus, loaded: false })).toBe('loaded');
    });

    it('reports a load error even when the health window is clean', () => {
        expect(pipelineClassifierState({ ...subprocessStatus, error: 'Model not found' })).toBe('check');
    });

    it('stays unknown when the status carries no signal at all', () => {
        expect(pipelineClassifierState(null)).toBe('unknown');
        expect(pipelineClassifierState({} as ClassifierStatus)).toBe('unknown');
        expect(pipelineClassifierState({ ...subprocessStatus, inference_health: undefined })).toBe('unknown');
        expect(pipelineClassifierState({ ...subprocessStatus, active_model_id: null, effective_model_id: null })).toBe('unknown');
    });
});
