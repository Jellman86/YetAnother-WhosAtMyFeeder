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

import { fetchAvailableModels, type InstalledModel, type ModelMetadata } from './classifier';

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
    });
});
