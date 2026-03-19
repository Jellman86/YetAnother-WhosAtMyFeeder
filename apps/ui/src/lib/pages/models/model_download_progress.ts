import type { DownloadProgress, ModelMetadata } from '../../api/classifier';
import type { JobProgressTerminalInput, JobProgressUpdateInput } from '../../stores/job_progress.svelte';

export const MODEL_DOWNLOAD_JOB_KIND = 'model_download';
export const MODEL_DOWNLOAD_ROUTE = '/settings';

interface JobProgressWriter {
    upsertRunning(input: JobProgressUpdateInput): void;
    markCompleted(input: JobProgressTerminalInput): void;
    markFailed(input: JobProgressTerminalInput): void;
    remove(id: string): void;
}

type ModelDownloadDescriptor = Pick<ModelMetadata, 'id' | 'name'>;

export function modelDownloadJobId(modelId: string): string {
    return `model-download:${modelId}`;
}

function modelDownloadTitle(model: ModelDownloadDescriptor): string {
    return `Download ${model.name}`;
}

function normalizeProgress(progress: number | undefined): number {
    if (!Number.isFinite(progress)) return 0;
    return Math.max(0, Math.min(100, Math.floor(progress ?? 0)));
}

function resolveRunningMessage(status?: DownloadProgress | null): string {
    if (typeof status?.message === 'string' && status.message.trim().length > 0) {
        return status.message.trim();
    }
    if (status?.status === 'pending') {
        return 'Preparing download';
    }
    return 'Downloading model';
}

function resolveTerminalMessage(status: DownloadProgress): string {
    if (status.status === 'error') {
        if (typeof status.error === 'string' && status.error.trim().length > 0) {
            return status.error.trim();
        }
        if (typeof status.message === 'string' && status.message.trim().length > 0) {
            return status.message.trim();
        }
        return 'Download failed';
    }
    if (typeof status.message === 'string' && status.message.trim().length > 0) {
        return status.message.trim();
    }
    return 'Download complete';
}

export function startModelDownloadProgress(store: JobProgressWriter, model: ModelDownloadDescriptor, timestamp?: number): void {
    const id = modelDownloadJobId(model.id);
    store.remove(id);
    store.upsertRunning({
        id,
        kind: MODEL_DOWNLOAD_JOB_KIND,
        title: modelDownloadTitle(model),
        message: 'Preparing download',
        route: MODEL_DOWNLOAD_ROUTE,
        current: 0,
        total: 100,
        source: 'ui',
        timestamp
    });
}

export function syncModelDownloadProgress(
    store: JobProgressWriter,
    model: ModelDownloadDescriptor,
    status: DownloadProgress,
    timestamp?: number
): void {
    const input = {
        id: modelDownloadJobId(model.id),
        kind: MODEL_DOWNLOAD_JOB_KIND,
        title: modelDownloadTitle(model),
        route: MODEL_DOWNLOAD_ROUTE,
        current: normalizeProgress(status.progress),
        total: 100,
        source: 'poll' as const,
        timestamp
    };

    if (status.status === 'completed') {
        store.markCompleted({
            ...input,
            message: resolveTerminalMessage(status)
        });
        return;
    }

    if (status.status === 'error') {
        store.markFailed({
            ...input,
            message: resolveTerminalMessage(status)
        });
        return;
    }

    store.upsertRunning({
        ...input,
        message: resolveRunningMessage(status)
    });
}
