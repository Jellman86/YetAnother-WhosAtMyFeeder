import { beforeEach, describe, expect, it } from 'vitest';
import type { DownloadProgress, ModelMetadata } from '../../api/classifier';
import { jobProgressStore } from '../../stores/job_progress.svelte';
import { modelDownloadJobId, startModelDownloadProgress, syncModelDownloadProgress } from './model_download_progress';

const MODEL: ModelMetadata = {
    id: 'hieradet_small_inat21',
    name: 'HieraDet Small',
    description: 'Broad wildlife model',
    architecture: 'HieraDet',
    file_size_mb: 168,
    accuracy_tier: 'High',
    inference_speed: 'Medium',
    download_url: 'https://example.test/model.onnx',
    labels_url: 'https://example.test/labels.txt',
    input_size: 256,
    runtime: 'onnx',
    supported_inference_providers: ['cpu', 'intel_cpu'],
    tier: 'small',
    taxonomy_scope: 'wildlife_wide',
    recommended_for: 'Most installs',
    estimated_ram_mb: 1024,
    advanced_only: false,
    sort_order: 20,
    status: 'beta'
};

function makeStatus(overrides: Partial<DownloadProgress> = {}): DownloadProgress {
    return {
        model_id: MODEL.id,
        status: 'downloading',
        progress: 42,
        message: 'Downloading model weights',
        ...overrides
    };
}

describe('model download progress', () => {
    beforeEach(() => {
        jobProgressStore.clearAll();
    });

    it('creates and updates a global running job for active model downloads', () => {
        startModelDownloadProgress(jobProgressStore, MODEL, 1000);
        syncModelDownloadProgress(jobProgressStore, MODEL, makeStatus(), 2000);

        const item = jobProgressStore.activeJobs.find((entry) => entry.id === modelDownloadJobId(MODEL.id));
        expect(item).toMatchObject({
            kind: 'model_download',
            title: 'Download HieraDet Small',
            message: 'Downloading model weights',
            route: '/settings',
            current: 42,
            total: 100,
            status: 'running'
        });
    });


    it('resets an existing model download job when a re-download starts', () => {
        startModelDownloadProgress(jobProgressStore, MODEL, 1000);
        syncModelDownloadProgress(jobProgressStore, MODEL, makeStatus({ status: 'completed', progress: 100, message: 'Download complete' }), 2000);

        startModelDownloadProgress(jobProgressStore, MODEL, 3000);

        const active = jobProgressStore.activeJobs.find((entry) => entry.id === modelDownloadJobId(MODEL.id));
        expect(active).toMatchObject({
            status: 'running',
            current: 0,
            total: 100,
            message: 'Preparing download'
        });
        expect(jobProgressStore.historyJobs).toHaveLength(0);
    });

    it('marks model downloads completed and failed in the global history', () => {
        startModelDownloadProgress(jobProgressStore, MODEL, 1000);
        syncModelDownloadProgress(jobProgressStore, MODEL, makeStatus({ status: 'completed', progress: 100, message: 'Download complete' }), 2000);

        let item = jobProgressStore.historyJobs.find((entry) => entry.id === modelDownloadJobId(MODEL.id));
        expect(item).toMatchObject({
            status: 'completed',
            current: 100,
            total: 100,
            message: 'Download complete'
        });

        jobProgressStore.clearAll();
        startModelDownloadProgress(jobProgressStore, MODEL, 3000);
        syncModelDownloadProgress(jobProgressStore, MODEL, makeStatus({ status: 'error', progress: 17, error: 'network timeout' }), 4000);

        item = jobProgressStore.historyJobs.find((entry) => entry.id === modelDownloadJobId(MODEL.id));
        expect(item).toMatchObject({
            status: 'failed',
            current: 17,
            total: 100,
            message: 'network timeout'
        });
    });
});
