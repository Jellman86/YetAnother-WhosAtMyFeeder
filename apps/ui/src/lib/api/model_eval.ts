import { API_BASE, apiFetch, handleResponse } from './core';

export interface ModelEvalRunSummary {
    run_id: string;
    started_at?: string;
    finished_at?: string | null;
    duration_seconds?: number | null;
    test_set?: {
        shared_core_species: number;
        regional_species: number;
        total_species: number;
        images_per_species: number;
        total_images: number;
        region: string | null;
        image_sources: Record<string, number>;
    };
    models?: ModelEvalModelSummary[];
    config_snapshot?: Record<string, unknown>;
    runtime?: Record<string, unknown>;
    error?: string;
}

export interface ModelEvalModelSummary {
    model_id: string;
    active_provider?: string | null;
    requested_provider?: string | null;
    device?: string | null;
    ready: boolean;
    ready_reason?: string;
    images_evaluated: number;
    top1_accuracy: number;
    top3_accuracy: number;
    top5_accuracy: number;
    abstention_rate: number;
    high_confidence_unknown_rate: number;
    mean_latency_ms?: number | null;
    p50_latency_ms?: number | null;
    p95_latency_ms?: number | null;
    startup_benchmark_ms?: number | null;
    latency_drift_ratio?: number | null;
    shared_core_top1: number;
    regional_top1: number;
    inference_health_verdict?: string | null;
    warnings: ModelEvalWarning[];
}

export interface ModelEvalWarning {
    code: string;
    message: string;
    severity: 'critical' | 'warning' | 'info';
}

export interface ModelEvalRunRow {
    run_id: string;
    status: string;
    started_at?: string | null;
    finished_at?: string | null;
    duration_seconds?: number | null;
    model_count?: number;
    total_species?: number;
    total_images?: number;
    region?: string | null;
    error?: string | null;
}

export interface ModelEvalActiveStatus {
    run_id: string;
    phase: string;
    started_at: string;
    progress: { done: number; total: number; label: string };
    error?: string;
}

export interface ModelEvalListResponse {
    active: ModelEvalActiveStatus | null;
    runs: ModelEvalRunRow[];
}

const BASE = `${API_BASE}/diagnostics/model-eval`;

export async function startModelEvalRun(opts: {
    include_per_image?: boolean;
    region_override?: string | null;
} = {}): Promise<{ run_id: string }> {
    const resp = await apiFetch(`${BASE}/runs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            include_per_image: !!opts.include_per_image,
            region_override: opts.region_override ?? null,
        }),
    });
    return handleResponse<{ run_id: string }>(resp);
}

export async function listModelEvalRuns(): Promise<ModelEvalListResponse> {
    const resp = await apiFetch(`${BASE}/runs`);
    return handleResponse<ModelEvalListResponse>(resp);
}

export async function getModelEvalRun(runId: string): Promise<ModelEvalRunSummary> {
    const resp = await apiFetch(`${BASE}/runs/${encodeURIComponent(runId)}`);
    return handleResponse<ModelEvalRunSummary>(resp);
}

export async function deleteModelEvalRun(runId: string): Promise<void> {
    const resp = await apiFetch(`${BASE}/runs/${encodeURIComponent(runId)}`, { method: 'DELETE' });
    await handleResponse(resp);
}

export function modelEvalArtifactUrl(runId: string, artifact: string): string {
    return `${BASE}/runs/${encodeURIComponent(runId)}/${encodeURIComponent(artifact)}`;
}
