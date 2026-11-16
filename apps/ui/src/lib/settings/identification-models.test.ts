// @ts-expect-error -- node:fs resolves at runtime, not in the app tsconfig
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import type { ClassifierStatus, ModelMetadata } from '../api/classifier';
import {
    identificationModelName,
    identificationStatus,
    modelFactsLine,
    recommendIdentificationModel,
} from './identification-models';

const translate = (key: string, options?: { default?: string; values?: Record<string, unknown> }): string => {
    let text = options?.default ?? key;
    for (const [name, value] of Object.entries(options?.values ?? {})) text = text.replace(`{${name}}`, String(value));
    return text;
};

function status(overrides: Partial<ClassifierStatus> = {}): ClassifierStatus {
    return {
        loaded: true,
        effective_model_id: 'rope_vit_b14_inat21',
        effective_model_name: 'RoPE ViT-B14 (Medium Accuracy)',
        active_model_installed: true,
        active_provider: 'intel_gpu',
        runtime_source: 'worker',
        labels_count: 10000,
        ...overrides,
    } as ClassifierStatus;
}

function model(overrides: Partial<ModelMetadata> = {}): ModelMetadata {
    return {
        id: 'rope_vit_b14_inat21',
        name: 'RoPE ViT-B14 (Medium Accuracy)',
        artifact_kind: 'classifier',
        tier: 'medium',
        taxonomy_scope: 'wildlife_wide',
        advanced_only: false,
        file_size_mb: 344.3,
        estimated_ram_mb: 1100,
        ...overrides,
    } as ModelMetadata;
}

describe('identificationStatus', () => {
    it('says it is still checking before the classifier has answered', () => {
        expect(identificationStatus(null)).toEqual({ kind: 'checking' });
    });

    it('says nothing names birds when the chosen model is not on this install', () => {
        expect(identificationStatus(status({ active_model_installed: false, effective_model_id: 'mobilenet_v2_birds', loaded: false }))).toEqual({
            kind: 'missing',
            modelId: 'mobilenet_v2_birds',
            modelName: 'RoPE ViT-B14 (Medium Accuracy)',
        });
    });

    it('names the model and the device it runs on', () => {
        expect(identificationStatus(status())).toEqual({
            kind: 'running',
            modelId: 'rope_vit_b14_inat21',
            modelName: 'RoPE ViT-B14 (Medium Accuracy)',
            device: 'Intel GPU',
            species: 10000,
            fallback: null,
        });
    });

    it('does not claim a device has run the model before the first detection loads it', () => {
        const result = identificationStatus(status({ runtime_source: 'planned', loaded: false }));
        expect(result).toMatchObject({ kind: 'planned', device: 'Intel GPU' });
    });

    it('says when the chosen device failed and the model fell back', () => {
        expect(identificationStatus(status({ fallback_reason: 'OpenVINO compile failed', active_provider: 'cpu' }))).toMatchObject({
            kind: 'running',
            device: 'CPU',
            fallback: 'device',
        });
    });

    it('says an installed in-process model that failed to load is not naming birds, with a plain cause', () => {
        const failed = status({ runtime_source: 'in_process', loaded: false, error: 'RuntimeError: unsupported opset 21' });
        expect(identificationStatus(failed)).toEqual({
            kind: 'failed',
            modelId: 'rope_vit_b14_inat21',
            modelName: 'RoPE ViT-B14 (Medium Accuracy)',
            cause: 'runtime',
            detail: 'RuntimeError: unsupported opset 21',
        });
    });

    it('names unreadable files as the cause when the runtime could not find them', () => {
        const failed = status({ runtime_source: 'in_process', loaded: false, error: 'Model not found: /data/models/x/model.onnx' });
        expect(identificationStatus(failed)).toMatchObject({ kind: 'failed', cause: 'missing_files' });
    });

    it('says an installed in-process model that is not loaded and reports no error is unavailable', () => {
        expect(identificationStatus(status({ image_execution_mode: 'in_process', runtime_source: 'in_process', loaded: false, error: null }))).toMatchObject({
            kind: 'unavailable',
        });
    });

    it('keeps the worker semantics: workers load on first use, so a not-loaded subprocess model is not a failure', () => {
        expect(identificationStatus(status({ image_execution_mode: 'subprocess', runtime_source: 'planned', loaded: false, error: 'stale in-process note' }))).toMatchObject({ kind: 'planned' });
        expect(identificationStatus(status({ image_execution_mode: 'subprocess', runtime_source: 'worker', loaded: false, error: null }))).toMatchObject({ kind: 'running' });
    });

    it('says when the isolated workers keep stopping and identification runs in the app', () => {
        expect(
            identificationStatus(status({ worker_in_process_fallback: { active: true } } as Partial<ClassifierStatus>))
        ).toMatchObject({ kind: 'running', fallback: 'workers' });
    });
});

describe('identificationModelName', () => {
    it('leads with what the model is for and keeps the code name as the technical name', () => {
        expect(identificationModelName({ id: 'mobilenet_v2_birds', name: 'MobileNet V2 (Fast)' }, translate)).toEqual({
            name: 'Small and quick, birds worldwide',
            technical: 'MobileNet V2',
        });
    });

    it('drops the marketing words in brackets from the technical name', () => {
        expect(identificationModelName({ id: 'eva02_large_inat21', name: 'EVA-02 Large (Elite Accuracy)' }, translate).technical).toBe('EVA-02 Large');
    });

    it('finds the purpose name of a regional variant from its family', () => {
        expect(identificationModelName({ id: 'small_birds/eu', name: 'Small Birds EU' }, translate).name).toBe('Birds of your region, quick');
    });

    it('falls back to the catalogue name for a model it has no purpose name for', () => {
        expect(identificationModelName({ id: 'brand_new', name: 'Brand New Net' }, translate)).toEqual({ name: 'Brand New Net', technical: null });
    });
});

describe('modelFactsLine', () => {
    it('leaves memory out where the card states it in full, so it is said once', () => {
        expect(modelFactsLine(model({ taxonomy_scope: 'birds_only', estimated_ram_mb: 64 }), { installed: true, memory: false }, translate)).toBe(
            'Birds only · on this install'
        );
    });

    it('states coverage, download and memory in sentence case, with one rounded size', () => {
        expect(modelFactsLine(model({ file_size_mb: 102.8, estimated_ram_mb: 1100 }), { installed: false }, translate)).toBe(
            'Birds and other wildlife · 103 MB download · about 1.1 GB memory'
        );
    });

    it('says the model is already here instead of quoting a download', () => {
        expect(modelFactsLine(model({ taxonomy_scope: 'birds_only', estimated_ram_mb: 64 }), { installed: true }, translate)).toBe(
            'Birds only · on this install · about 64 MB memory'
        );
    });

    it('says a model ships with the app only when this install has it built in', () => {
        expect(modelFactsLine(model({ taxonomy_scope: 'birds_only', estimated_ram_mb: null }), { installed: true, bundled: true }, translate)).toBe(
            'Birds only · comes with the app'
        );
    });
});

describe('recommendIdentificationModel', () => {
    const lineup = [
        model({ id: 'mobilenet_v2_birds', name: 'MobileNet V2 (Fast)', tier: 'cpu_only', taxonomy_scope: 'birds_only', advanced_only: true }),
        model({ id: 'small_birds', name: 'Small Birds', tier: 'small', taxonomy_scope: 'birds_only' }),
        model({ id: 'rope_vit_b14_inat21' }),
    ];

    it('recommends the regional quick model to an install that runs the small starter model', () => {
        expect(recommendIdentificationModel(lineup, { currentId: 'mobilenet_v2_birds', currentInUse: true })?.id).toBe('small_birds');
    });

    it('recommends a model when nothing can name birds yet', () => {
        expect(recommendIdentificationModel(lineup, { currentId: null, currentInUse: false })?.id).toBe('small_birds');
    });

    it('recommends nothing once a fuller model is in use, so a deliberate choice is not second-guessed', () => {
        expect(recommendIdentificationModel(lineup, { currentId: 'rope_vit_b14_inat21', currentInUse: true })).toBeNull();
    });

    it('never recommends the model that is already in use', () => {
        expect(recommendIdentificationModel(lineup, { currentId: 'small_birds', currentInUse: true })).toBeNull();
    });

    it('never recommends the chosen model again when its files are missing, but offers the next one', () => {
        expect(recommendIdentificationModel(lineup, { currentId: 'small_birds', currentInUse: false })?.id).toBe('rope_vit_b14_inat21');
        expect(recommendIdentificationModel(lineup, { currentId: 'small_birds/eu', currentInUse: false })?.id).toBe('rope_vit_b14_inat21');
    });

    it('recommends the starter model on a Raspberry Pi image, where larger models are too heavy', () => {
        expect(recommendIdentificationModel(lineup, { currentId: null, currentInUse: false, imageFlavor: 'rpi' })?.id).toBe('mobilenet_v2_birds');
    });
});

describe('the SPA and the server read a classifier report as the same readiness', () => {
    // The cases the server's `identification_readiness` is tested against (backend/tests/pure).
    const shared = JSON.parse(
        readFileSync(new URL('../../../../../backend/tests/fixtures/model_readiness_cases.json', import.meta.url), 'utf8')
    ) as { cases: Array<{ name: string; status: ClassifierStatus | null; readiness: string }> };
    const READINESS: Record<ReturnType<typeof identificationStatus>['kind'], string> = {
        checking: 'checking',
        missing: 'missing',
        failed: 'failed',
        unavailable: 'failed',
        planned: 'ready',
        running: 'running'
    };

    it.each(shared.cases)('$name', ({ status, readiness }) => {
        expect(READINESS[identificationStatus(status).kind]).toBe(readiness);
    });

    it('covers an incomplete install: weights present, labels unreadable', () => {
        expect(shared.cases.some((entry) => entry.readiness === 'failed' && entry.status?.active_model_installed === true)).toBe(true);
    });
});
