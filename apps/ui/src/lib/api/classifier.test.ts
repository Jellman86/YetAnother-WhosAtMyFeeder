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
    summarizeModelMetadata,
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
            },
            {
                id: 'rope_vit_b14_inat21',
                name: 'RoPE ViT-B14',
                description: 'Medium wildlife option',
                architecture: 'RoPE-ViT-B14-CAPI',
                file_size_mb: 375,
                accuracy_tier: 'Very High (89%+)',
                inference_speed: 'Medium-Slow (~220-400ms)',
                download_url: 'https://example.com/models/rope_vit_b14_inat21.onnx',
                labels_url: 'https://example.com/models/rope_vit_b14_inat21_labels.txt',
                input_size: 224,
                runtime: 'onnx',
                supported_inference_providers: ['cpu', 'cuda'],
                tier: 'medium',
                taxonomy_scope: 'wildlife_wide',
                recommended_for: 'Broader wildlife',
                estimated_ram_mb: 1536,
                advanced_only: false,
                sort_order: 18,
                status: 'experimental',
                notes: 'Experimental medium model.',
            },
            {
                id: 'hieradet_small_inat21',
                name: 'HieraDet Small',
                description: 'Small wildlife option',
                architecture: 'HieraDet-Small-DINOv2',
                file_size_mb: 168,
                accuracy_tier: 'High (88%+)',
                inference_speed: 'Medium (~120-250ms)',
                download_url: 'https://example.com/models/hieradet_small_inat21.onnx',
                labels_url: 'https://example.com/models/hieradet_small_inat21_labels.txt',
                input_size: 256,
                runtime: 'onnx',
                supported_inference_providers: ['cpu', 'cuda'],
                tier: 'small',
                taxonomy_scope: 'wildlife_wide',
                recommended_for: 'Smaller wildlife model',
                estimated_ram_mb: 1024,
                advanced_only: false,
                sort_order: 15,
                status: 'experimental',
                notes: 'Experimental small model.',
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
            },
        ];

        expect(getVisibleTieredModelLineup(models)).toMatchObject([
            { id: 'mobilenet_v2_birds' },
            { id: 'hieradet_small_inat21' },
            { id: 'rope_vit_b14_inat21' },
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
});
