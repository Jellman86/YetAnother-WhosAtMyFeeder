// @ts-expect-error -- node:fs resolves at runtime, not in the app tsconfig
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import type { ClassifierStatus } from '../api/classifier';
import { readinessLabel } from '../settings/model-readiness';
import { pipelineClassifierStep } from './pipeline-classifier-state';

const t = (key: string, options?: { default?: string }): string => options?.default ?? key;

// What /api/classifier/status sends on a default install: image work runs in worker processes, so
// there is no top-level `loaded`.
const workers: ClassifierStatus = {
    image_execution_mode: 'subprocess',
    runtime_source: 'worker',
    labels_count: 965,
    active_model_installed: true,
    active_model_id: 'rope_vit_b14_inat21',
    effective_model_id: 'rope_vit_b14_inat21',
    inference_health: { status: 'ok' }
};

describe("About's classifier step reads the model as every other surface does", () => {
    // The cases the server's `identification_readiness`, Settings and the wizard are held to.
    const shared = JSON.parse(
        readFileSync(new URL('../../../../../backend/tests/fixtures/model_readiness_cases.json', import.meta.url), 'utf8')
    ) as { cases: Array<{ name: string; status: ClassifierStatus | null; readiness: string }> };

    it.each(shared.cases)('$name', ({ status, readiness }) => {
        expect(pipelineClassifierStep(status).readiness).toBe(readiness);
    });

    it('says a loading model is loading, not unknown', () => {
        const loading: ClassifierStatus = { ...workers, runtime_source: 'in_process', image_execution_mode: 'in_process' };
        expect(readinessLabel(pipelineClassifierStep(loading).readiness, t)).toBe('Loading');
    });

    it('says a model that failed to load could not load, a failed fallback included, not "Check"', () => {
        for (const runtime_source of ['in_process', 'in_process_fallback'] as const) {
            const failed: ClassifierStatus = { ...workers, runtime_source, loaded: false, error: 'runtime could not open the model' };
            expect(readinessLabel(pipelineClassifierStep(failed).readiness, t)).toBe('Could not load');
        }
    });

    it('says ready or running without any inference-health data, not unknown', () => {
        const unreported = { ...workers, inference_health: undefined };
        expect(pipelineClassifierStep(unreported)).toMatchObject({ readiness: 'running', health: null, tone: 'ok' });
        expect(pipelineClassifierStep({ ...unreported, runtime_source: 'planned' })).toMatchObject({ readiness: 'ready', health: null });
    });

    it('carries work this app started on the model, as the Models page does', () => {
        expect(pipelineClassifierStep({ ...workers, active_model_installed: false }, 'downloading').readiness).toBe('queued');
        expect(pipelineClassifierStep(workers, 'validating').readiness).toBe('validating');
    });
});

describe('inference health is reported beside the model, never as its state', () => {
    it('keeps a running model running while its inferences fail, and stops calling the step working', () => {
        const failing = pipelineClassifierStep({ ...workers, inference_health: { status: 'unhealthy' } });
        expect(failing).toMatchObject({ readiness: 'running', health: 'unhealthy', tone: 'off' });
        expect(pipelineClassifierStep({ ...workers, inference_health: { status: 'degraded' } })).toMatchObject({ readiness: 'running', health: 'degraded', tone: 'off' });
    });

    it('reports no health reading when inference is fine or was not reported', () => {
        expect(pipelineClassifierStep(workers).health).toBeNull();
    });

    it('is lit only on evidence, and neutral for what the app is doing or could not read', () => {
        expect(pipelineClassifierStep(workers).tone).toBe('ok');
        expect(pipelineClassifierStep(null).tone).toBe('unknown');
        expect(pipelineClassifierStep({}).tone).toBe('unknown');
        expect(pipelineClassifierStep({ ...workers, active_model_installed: false }).tone).toBe('off');
    });
});
