import { beforeEach, describe, expect, it, vi } from 'vitest';

const { apiFetchMock, handleResponseMock } = vi.hoisted(() => ({
    apiFetchMock: vi.fn(),
    handleResponseMock: vi.fn(),
}));

vi.mock('./core', () => ({
    API_BASE: '/api',
    apiFetch: apiFetchMock,
    handleResponse: handleResponseMock,
    fetchWithAbort: vi.fn(),
}));

import {
    fetchAvailableModels,
    getVisibleTieredModelLineup,
    groupTieredModelLineup,
    categorizeModel,
    summarizeModelMetadata,
    type ClassifierStatus,
    type InstalledModel,
    type ModelMetadata
} from './classifier';

describe('fetchAvailableModels', () => {
    beforeEach(() => {
        apiFetchMock.mockReset();
        handleResponseMock.mockReset();
        apiFetchMock.mockResolvedValue({});
    });

    it('preserves tiered taxonomy and advanced-state metadata in the model payload', async () => {
        const model: ModelMetadata = {
            id: 'eva02_large_inat21',
            name: 'EVA-02 Large (Elite Accuracy)',
            description: 'State-of-the-art iNat21 classifier.',
            architecture: 'EVA-02-Large',
            file_size_mb: 1200,
            accuracy_tier: 'Elite (91%+)',
            inference_speed: 'Slow (~1s)',
            download_url: 'https://example.com/models/eva02_large_inat21.onnx',
            weights_url: 'https://example.com/models/eva02_large_inat21.onnx.data',
            labels_url: 'https://example.com/models/eva02_large_inat21_labels.txt',
            input_size: 336,
            runtime: 'onnx',
            supported_inference_providers: ['cpu', 'cuda', 'intel_cpu', 'intel_gpu'],
            tier: 'advanced',
            taxonomy_scope: 'wildlife_wide',
            recommended_for: 'Highest-accuracy wildlife classification for advanced users with more compute and RAM.',
            estimated_ram_mb: 3072,
            advanced_only: true,
            sort_order: 30,
            status: 'stable',
            notes: 'Elite accuracy model.',
        };

        handleResponseMock.mockReturnValueOnce([model]);

        const result = await fetchAvailableModels();

        expect(result).toEqual([model]);
        expect(result[0].taxonomy_scope).toBe('wildlife_wide');
        expect(result[0].advanced_only).toBe(true);
        expect(result[0].recommended_for).toContain('advanced users');

        const installed: InstalledModel = {
            id: model.id,
            path: '/models/eva02_large_inat21/model.onnx',
            labels_path: '/models/eva02_large_inat21/labels.txt',
            is_active: true,
            metadata: result[0],
        };

        expect(installed.metadata?.status).toBe('stable');
        expect(installed.metadata?.notes).toBe('Elite accuracy model.');

        const summary = summarizeModelMetadata(installed.metadata);
        expect(summary).toEqual({
            tierLabel: 'Advanced',
            taxonomyScopeLabel: 'Wildlife Wide',
            advancedStateLabel: 'Advanced only',
            statusLabel: 'Stable',
            labels: ['Advanced', 'Wildlife Wide', 'Advanced only', 'Stable'],
        });
    });
});


describe('getVisibleTieredModelLineup', () => {
    it('sorts by tier and sort order and hides advanced-only models by default', () => {
        const models: ModelMetadata[] = [
            {
                id: 'bird_crop_detector',
                name: 'Bird Crop Detector',
                description: 'Managed crop detector dependency',
                architecture: 'SSD-MobileNet',
                file_size_mb: 12.4,
                accuracy_tier: 'System',
                inference_speed: 'Fast',
                download_url: 'https://example.com/models/bird_crop_detector.onnx',
                labels_url: 'https://example.com/models/bird_crop_detector_labels.txt',
                input_size: 320,
                runtime: 'onnx',
                supported_inference_providers: ['cpu'],
                tier: 'dependency',
                taxonomy_scope: 'system',
                recommended_for: 'Crop dependency',
                estimated_ram_mb: 128,
                advanced_only: true,
                sort_order: 5,
                status: 'stable',
                notes: 'Managed crop detector.',
                artifact_kind: 'crop_detector',
            },
            {
                id: 'eva02_large_inat21',
                name: 'EVA-02 Large (Elite Accuracy)',
                description: 'Advanced option',
                architecture: 'EVA-02-Large',
                file_size_mb: 1200,
                accuracy_tier: 'Elite (91%+)',
                inference_speed: 'Slow (~1s)',
                download_url: 'https://example.com/models/eva02_large_inat21.onnx',
                weights_url: 'https://example.com/models/eva02_large_inat21.onnx.data',
                labels_url: 'https://example.com/models/eva02_large_inat21_labels.txt',
                input_size: 336,
                runtime: 'onnx',
                supported_inference_providers: ['cpu', 'cuda'],
                tier: 'advanced',
                taxonomy_scope: 'wildlife_wide',
                recommended_for: 'Advanced users',
                estimated_ram_mb: 3072,
                advanced_only: true,
                sort_order: 30,
                status: 'stable',
                notes: 'Elite accuracy model.',
                artifact_kind: 'classifier',
            },
            {
                id: 'convnext_large_inat21',
                name: 'ConvNeXt Large (High Accuracy)',
                description: 'Broad wildlife option',
                architecture: 'ConvNeXt-Large-MLP',
                file_size_mb: 760,
                accuracy_tier: 'Very High (90%+)',
                inference_speed: 'Slow (~500-800ms)',
                download_url: 'https://example.com/models/convnext_large_inat21.onnx',
                weights_url: 'https://example.com/models/convnext_large_inat21.onnx.data',
                labels_url: 'https://example.com/models/convnext_large_inat21_labels.txt',
                input_size: 384,
                runtime: 'onnx',
                supported_inference_providers: ['cpu', 'cuda'],
                tier: 'large',
                taxonomy_scope: 'wildlife_wide',
                recommended_for: 'General wildlife',
                estimated_ram_mb: 2048,
                advanced_only: false,
                sort_order: 20,
                status: 'stable',
                notes: 'Higher-accuracy broad model.',
                artifact_kind: 'classifier',
            },
            {
                id: 'rope_vit_b14_inat21',
                name: 'ConvNeXt V2 Nano (Medium Birds)',
                description: 'Medium bird-only option',
                architecture: 'ConvNeXt V2 Nano',
                file_size_mb: 375,
                accuracy_tier: 'Very High (89%+)',
                inference_speed: 'Medium-Slow (~220-400ms)',
                download_url: 'https://example.com/models/rope_vit_b14_inat21.onnx',
                labels_url: 'https://example.com/models/rope_vit_b14_inat21_labels.txt',
                input_size: 224,
                runtime: 'onnx',
                supported_inference_providers: ['cpu', 'cuda'],
                tier: 'medium',
                taxonomy_scope: 'birds_only',
                recommended_for: 'Bird-only medium inference',
                estimated_ram_mb: 1536,
                advanced_only: true,
                sort_order: 18,
                status: 'stable',
                notes: 'OpenVINO Intel GPU validated; CUDA not validated in this environment.',
                artifact_kind: 'classifier',
            },
            {
                id: 'hieradet_small_inat21',
                name: 'MobileNetV4 Conv Medium (Small Birds)',
                description: 'Small bird-only option',
                architecture: 'MobileNetV4 Conv Medium',
                file_size_mb: 168,
                accuracy_tier: 'High (88%+)',
                inference_speed: 'Medium (~120-250ms)',
                download_url: 'https://example.com/models/hieradet_small_inat21.onnx',
                labels_url: 'https://example.com/models/hieradet_small_inat21_labels.txt',
                input_size: 256,
                runtime: 'onnx',
                supported_inference_providers: ['cpu', 'cuda'],
                tier: 'small',
                taxonomy_scope: 'birds_only',
                recommended_for: 'Bird-only small inference',
                estimated_ram_mb: 1024,
                advanced_only: true,
                sort_order: 15,
                status: 'stable',
                notes: 'OpenVINO Intel GPU validated; CUDA not validated in this environment.',
                artifact_kind: 'classifier',
            },
            {
                id: 'mobilenet_v2_birds',
                name: 'MobileNet V2 (Fast)',
                description: 'Default model',
                architecture: 'MobileNetV2',
                file_size_mb: 3.4,
                accuracy_tier: 'Medium',
                inference_speed: 'Fast (~30ms)',
                download_url: 'https://example.com/models/mobilenet_v2_birds.tflite',
                labels_url: 'https://example.com/models/mobilenet_v2_birds_labels.txt',
                input_size: 224,
                runtime: 'tflite',
                supported_inference_providers: ['cpu'],
                tier: 'cpu_only',
                taxonomy_scope: 'birds_only',
                recommended_for: 'Default bird-only inference',
                estimated_ram_mb: 128,
                advanced_only: false,
                sort_order: 10,
                status: 'stable',
                notes: 'Fastest option.',
                artifact_kind: 'classifier',
            },
        ];

        expect(getVisibleTieredModelLineup(models)).toMatchObject([
            { id: 'mobilenet_v2_birds' },
            { id: 'convnext_large_inat21' },
        ]);
        expect(getVisibleTieredModelLineup(models, true)).toMatchObject([
            { id: 'mobilenet_v2_birds' },
            { id: 'hieradet_small_inat21' },
            { id: 'rope_vit_b14_inat21' },
            { id: 'convnext_large_inat21' },
            { id: 'eva02_large_inat21' },
        ]);
    });

    it('keeps the active advanced model visible when advanced models are collapsed', () => {
        const models: ModelMetadata[] = [
            {
                id: 'eva02_large_inat21',
                name: 'EVA-02 Large (Elite Accuracy)',
                description: 'Advanced option',
                architecture: 'EVA-02-Large',
                file_size_mb: 1200,
                accuracy_tier: 'Elite (91%+)',
                inference_speed: 'Slow (~1s)',
                download_url: 'https://example.com/models/eva02_large_inat21.onnx',
                weights_url: 'https://example.com/models/eva02_large_inat21.onnx.data',
                labels_url: 'https://example.com/models/eva02_large_inat21_labels.txt',
                input_size: 336,
                runtime: 'onnx',
                supported_inference_providers: ['cpu', 'cuda'],
                tier: 'advanced',
                taxonomy_scope: 'wildlife_wide',
                recommended_for: 'Advanced users',
                estimated_ram_mb: 3072,
                advanced_only: true,
                sort_order: 30,
                status: 'stable',
                notes: 'Elite accuracy model.',
                artifact_kind: 'classifier',
            },
            {
                id: 'rope_vit_b14_inat21',
                name: 'RoPE-ViT B/14',
                description: 'Advanced option',
                architecture: 'RoPE-ViT',
                file_size_mb: 375,
                accuracy_tier: 'Very High',
                inference_speed: 'Medium-Slow',
                download_url: 'https://example.com/models/rope_vit_b14_inat21.onnx',
                labels_url: 'https://example.com/models/rope_vit_b14_inat21_labels.txt',
                input_size: 224,
                runtime: 'onnx',
                supported_inference_providers: ['cpu', 'cuda'],
                tier: 'medium',
                taxonomy_scope: 'birds_only',
                recommended_for: 'Advanced users',
                estimated_ram_mb: 1536,
                advanced_only: true,
                sort_order: 18,
                status: 'stable',
                notes: 'Advanced bird model.',
                artifact_kind: 'classifier',
            },
            {
                id: 'mobilenet_v2_birds',
                name: 'MobileNet V2 (Fast)',
                description: 'Default model',
                architecture: 'MobileNetV2',
                file_size_mb: 3.4,
                accuracy_tier: 'Medium',
                inference_speed: 'Fast (~30ms)',
                download_url: 'https://example.com/models/mobilenet_v2_birds.tflite',
                labels_url: 'https://example.com/models/mobilenet_v2_birds_labels.txt',
                input_size: 224,
                runtime: 'tflite',
                supported_inference_providers: ['cpu'],
                tier: 'cpu_only',
                taxonomy_scope: 'birds_only',
                recommended_for: 'Default bird-only inference',
                estimated_ram_mb: 128,
                advanced_only: false,
                sort_order: 10,
                status: 'stable',
                notes: 'Fastest option.',
                artifact_kind: 'classifier',
            },
        ];

        expect(getVisibleTieredModelLineup(models, false, 'eva02_large_inat21')).toMatchObject([
            { id: 'mobilenet_v2_birds' },
            { id: 'eva02_large_inat21' },
        ]);
        expect(getVisibleTieredModelLineup(models, false, 'rope_vit_b14_inat21')).toMatchObject([
            { id: 'mobilenet_v2_birds' },
            { id: 'rope_vit_b14_inat21' },
        ]);
    });
});

describe('categorizeModel', () => {
    function base(extra: Partial<ModelMetadata> = {}): ModelMetadata {
        return {
            id: 'x',
            name: 'X',
            description: '',
            architecture: 'Test',
            file_size_mb: 1,
            accuracy_tier: '',
            inference_speed: '',
            download_url: '',
            labels_url: '',
            input_size: 224,
            tier: 'medium',
            taxonomy_scope: 'birds_only',
            recommended_for: '',
            advanced_only: false,
            sort_order: 100,
            status: 'stable',
            ...extra,
        } as ModelMetadata;
    }

    it('returns igpu_recommended when registry lists intel_gpu', () => {
        expect(categorizeModel(base({ supported_inference_providers: ['cpu', 'intel_cpu', 'intel_gpu'] }))).toBe('igpu_recommended');
    });

    it('returns bundled for tier=cpu_only or tflite runtime', () => {
        expect(categorizeModel(base({ tier: 'cpu_only', supported_inference_providers: ['cpu'] }))).toBe('bundled');
        expect(categorizeModel(base({ runtime: 'tflite', tier: 'small' }))).toBe('bundled');
    });

    it('returns cpu_high_accuracy for Elite / Very High accuracy without iGPU', () => {
        expect(categorizeModel(base({ accuracy_tier: 'Elite (91%+)', supported_inference_providers: ['cpu', 'intel_cpu'] }))).toBe('cpu_high_accuracy');
        expect(categorizeModel(base({ accuracy_tier: 'Very High (89%+)', supported_inference_providers: ['cpu'] }))).toBe('cpu_high_accuracy');
    });

    it('returns cpu_alternative for advanced_only experimental models', () => {
        expect(categorizeModel(base({ advanced_only: true, supported_inference_providers: ['cpu', 'intel_cpu'], accuracy_tier: 'High' }))).toBe('cpu_alternative');
    });

    it('returns cpu_standard otherwise', () => {
        expect(categorizeModel(base({ supported_inference_providers: ['cpu', 'intel_cpu'], accuracy_tier: 'High' }))).toBe('cpu_standard');
    });
});

describe('groupTieredModelLineup', () => {
    function model(id: string, extra: Partial<ModelMetadata> = {}): ModelMetadata {
        return {
            id,
            name: id,
            description: '',
            architecture: 'X',
            file_size_mb: 1,
            accuracy_tier: '',
            inference_speed: '',
            download_url: '',
            labels_url: '',
            input_size: 224,
            tier: 'medium',
            taxonomy_scope: 'birds_only',
            recommended_for: '',
            advanced_only: false,
            sort_order: 100,
            status: 'stable',
            ...extra,
        } as ModelMetadata;
    }

    it('groups in display order and drops empty buckets', () => {
        const ms = [
            model('a', { supported_inference_providers: ['cpu', 'intel_cpu', 'intel_gpu'], sort_order: 22, tier: 'medium' }),
            model('b', { runtime: 'tflite', tier: 'cpu_only', sort_order: 10 }),
            model('c', { accuracy_tier: 'Elite', supported_inference_providers: ['cpu'], sort_order: 30, tier: 'advanced' }),
        ];
        const groups = groupTieredModelLineup(ms, true);
        expect(groups.map((g) => g.category)).toEqual(['igpu_recommended', 'cpu_high_accuracy', 'bundled']);
        expect(groups[0].models).toHaveLength(1);
        expect(groups[0].models[0].id).toBe('a');
    });

    it('respects showAdvanced for advanced_only models', () => {
        const ms = [
            model('std', { sort_order: 10 }),
            model('exp', { advanced_only: true, sort_order: 20 }),
        ];
        const visible = groupTieredModelLineup(ms, false);
        expect(visible.flatMap((g) => g.models.map((m) => m.id))).toEqual(['std']);
        const all = groupTieredModelLineup(ms, true);
        expect(all.flatMap((g) => g.models.map((m) => m.id)).sort()).toEqual(['exp', 'std']);
    });
});

describe('ClassifierStatus', () => {
    it('supports crop detector readiness telemetry', () => {
        const status: ClassifierStatus = {
            loaded: true,
            error: null,
            labels_count: 10,
            enabled: true,
            crop_detector: {
                model_id: 'bird_crop_detector',
                installed: false,
                healthy: false,
                enabled_for_runtime: false,
                reason: 'not_installed',
            },
        };

        expect(status.crop_detector?.model_id).toBe('bird_crop_detector');
        expect(status.crop_detector?.enabled_for_runtime).toBe(false);
    });
});
