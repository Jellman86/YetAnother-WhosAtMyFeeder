import { API_BASE, apiFetch, handleResponse } from './core';
import type { components } from './generated/openapi';

export type ModelEvalRunSummary = components['schemas']['ModelEvalRunResponse'];
export type ModelEvalModelSummary = components['schemas']['ModelEvalModelSummary'];
export type ModelEvalWarning = components['schemas']['ModelEvalWarning'];
export type ModelEvalRunRow = components['schemas']['ModelEvalRunRow'];
export type ModelEvalActiveStatus = components['schemas']['ModelEvalActiveStatus'];
type ModelEvalListResponse = components['schemas']['ModelEvalListResponse'];

const BASE = `${API_BASE}/diagnostics/model-eval`;

export async function startModelEvalRun(opts: {
    include_per_image?: boolean;
    region_override?: string | null;
    sweep_devices?: boolean;
    compat_only?: boolean;
    sweep_all_models?: boolean;
    model_ids?: string[];
} = {}): Promise<{ run_id: string }> {
    const resp = await apiFetch(`${BASE}/runs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            include_per_image: !!opts.include_per_image,
            region_override: opts.region_override ?? null,
            sweep_devices: !!opts.sweep_devices,
            compat_only: !!opts.compat_only,
            sweep_all_models: !!opts.sweep_all_models,
            model_ids: opts.model_ids ?? [],
        }),
    });
    return handleResponse<{ run_id: string }>(resp);
}

interface DeviceSweepEntry {
    provider?: string;
    backend?: string;
    device?: string;
    ok?: boolean;
    compiles: boolean;
    error?: string | null;
    finite?: boolean | null;
    latency_ms?: number;
    images_evaluated?: number;
    images_compared?: number;
    top1_match_rate?: number;   // vs CPU, over real images (0..1)
    mean_top5_overlap?: number; // vs CPU, over real images (0..5)
    comparison_kind?: 'classifier_top1' | 'crop_box';
    detection_match_rate?: number; // detector presence/box/confidence agreement vs CPU
    mean_box_iou?: number;
    mean_confidence_delta?: number;
    real_images_evaluated?: number;
    negative_images_evaluated?: number;
    real_detections?: number;
    matches_cpu?: boolean;      // top-1 matched CPU on every compared image
    matches_baseline?: boolean;
    baseline?: boolean;
}

export interface DeviceMatrix {
    schema_version?: number;
    run_id: string;
    generated_at: string;
    image_flavor?: string;
    providers?: string[];
    devices: string[];
    image_count?: number;
    models: Record<string, {
        error?: string;
        comparison_kind?: 'classifier_top1';
        baseline_provider?: string;
        best_provider?: string;
        providers?: Record<string, DeviceSweepEntry>;
        devices?: Record<string, DeviceSweepEntry>;
    }>;
    crop_detectors?: Record<string, {
        error?: string;
        comparison_kind?: 'crop_box';
        baseline_provider?: string;
        best_provider?: string;
        providers?: Record<string, DeviceSweepEntry>;
        devices?: Record<string, DeviceSweepEntry>;
    }>;
}

export async function getModelEvalDeviceMatrix(runId: string): Promise<DeviceMatrix | null> {
    const resp = await apiFetch(modelEvalArtifactUrl(runId, 'device_matrix.json'), { timeoutMs: 15_000 });
    if (!resp.ok) return null;
    return resp.json() as Promise<DeviceMatrix>;
}

export async function listModelEvalRuns(): Promise<ModelEvalListResponse> {
    const resp = await apiFetch(`${BASE}/runs`, { timeoutMs: 10_000 });
    return handleResponse<ModelEvalListResponse>(resp);
}

export async function getModelEvalRun(runId: string): Promise<ModelEvalRunSummary> {
    const resp = await apiFetch(`${BASE}/runs/${encodeURIComponent(runId)}`, { timeoutMs: 15_000 });
    return handleResponse<ModelEvalRunSummary>(resp);
}

export async function deleteModelEvalRun(runId: string): Promise<void> {
    const resp = await apiFetch(`${BASE}/runs/${encodeURIComponent(runId)}`, { method: 'DELETE' });
    await handleResponse(resp);
}

export async function cancelModelEvalRun(runId: string): Promise<void> {
    const resp = await apiFetch(`${BASE}/runs/${encodeURIComponent(runId)}/cancel`, { method: 'POST' });
    await handleResponse(resp);
}

export async function fetchModelEvalArtifact(runId: string, artifact: string): Promise<Blob> {
    const response = await apiFetch(modelEvalArtifactUrl(runId, artifact), { timeoutMs: 30_000 });
    if (!response.ok) await handleResponse(response);
    return response.blob();
}

function modelEvalArtifactUrl(runId: string, artifact: string): string {
    return `${BASE}/runs/${encodeURIComponent(runId)}/${encodeURIComponent(artifact)}`;
}
