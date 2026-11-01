import { API_BASE, apiFetch, fetchWithAbort, handleResponse } from './core';
import type { components, paths } from './generated/openapi';

export type ClassifierStatus = components['schemas']['ClassifierStatusResponse'];

export async function fetchClassifierStatus(): Promise<ClassifierStatus> {
    const response = await apiFetch(`${API_BASE}/classifier/status`);
    return handleResponse<ClassifierStatus>(response);
}

export function selectSetupModelId(
    status: ClassifierStatus,
    available: ModelMetadata[],
    installed: InstalledModel[]
): string {
    const installedIds = new Set(installed.map((model) => model.id));
    const effectiveModelId = status.effective_model_id ?? '';
    if (effectiveModelId && installedIds.has(effectiveModelId)) return effectiveModelId;

    const activeInstalled = installed.find((model) => model.is_active && model.ready !== false);
    if (activeInstalled) return activeInstalled.id;

    if (status.image_flavor === 'rpi' && installedIds.has('mobilenet_v2_birds')) {
        return 'mobilenet_v2_birds';
    }

    const firstInstalled = installed.find((model) => model.ready !== false);
    if (firstInstalled) return firstInstalled.id;

    const preferredAvailable = status.image_flavor === 'rpi'
        ? available.find((model) => model.id === 'mobilenet_v2_birds')
        : undefined;
    return preferredAvailable?.id ?? status.active_model_id ?? available[0]?.id ?? '';
}

export type DownloadModelResult = paths['/api/classifier/download']['post']['response'];

export async function downloadDefaultModel(): Promise<DownloadModelResult> {
    const response = await apiFetch(`${API_BASE}/classifier/download`, {
        method: 'POST',
    });
    return handleResponse<DownloadModelResult>(response);
}

export type ReclassifyResult = paths['/api/events/{event_id}/reclassify']['post']['response'];

export type UpdateDetectionResult = paths['/api/events/{event_id}']['patch']['response'];

export type BulkUpdateDetectionResult = paths['/api/events/bulk/manual-tag']['patch']['response'];

export type ClassifierLabelsResponse = paths['/api/classifier/labels']['get']['response'];

export async function fetchClassifierLabels(): Promise<ClassifierLabelsResponse> {
    const response = await apiFetch(`${API_BASE}/classifier/labels`);
    return handleResponse<ClassifierLabelsResponse>(response);
}

export async function reclassifyDetection(eventId: string, strategy: 'snapshot' | 'video' = 'snapshot'): Promise<ReclassifyResult> {
    const params = new URLSearchParams({ strategy });
    const response = await apiFetch(`${API_BASE}/events/${encodeURIComponent(eventId)}/reclassify?${params.toString()}`, {
        method: 'POST',
    });
    return handleResponse<ReclassifyResult>(response);
}

export async function updateDetectionSpecies(eventId: string, displayName: string): Promise<UpdateDetectionResult> {
    const response = await apiFetch(`${API_BASE}/events/${encodeURIComponent(eventId)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ display_name: displayName }),
    });
    return handleResponse<UpdateDetectionResult>(response);
}

export async function bulkUpdateDetectionSpecies(eventIds: string[], displayName: string): Promise<BulkUpdateDetectionResult> {
    const response = await apiFetch(`${API_BASE}/events/bulk/manual-tag`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ event_ids: eventIds, display_name: displayName }),
    });
    return handleResponse<BulkUpdateDetectionResult>(response);
}

export type ModelMetadata = components['schemas']['ModelMetadata'];

export interface ModelMetadataSummary {
    tierLabel: string;
    taxonomyScopeLabel: string;
    advancedStateLabel: string;
    statusLabel: string;
    labels: string[];
}

const MODEL_TIER_PRIORITY: Record<string, number> = {
    cpu_only: 0,
    small: 1,
    medium: 2,
    large: 3,
    advanced: 4,
};

function compareTieredModelMetadata(a: ModelMetadata, b: ModelMetadata): number {
    return (
        (MODEL_TIER_PRIORITY[a.tier] ?? 99) - (MODEL_TIER_PRIORITY[b.tier] ?? 99) ||
        (a.sort_order ?? 0) - (b.sort_order ?? 0) ||
        a.name.localeCompare(b.name)
    );
}

export function getVisibleTieredModelLineup(
    models: ModelMetadata[],
    showAdvanced: boolean = false,
    selectedOrActiveModelId?: string | null
): ModelMetadata[] {
    return [...models]
        .sort(compareTieredModelMetadata)
        .filter((model) => (model.artifact_kind || 'classifier') === 'classifier')
        .filter((model) => showAdvanced || !model.advanced_only || model.id === selectedOrActiveModelId);
}

// ---------------------------------------------------------------------------
// Model categorization for the Model Manager UI.
//
// Splits the tiered lineup into groups that match how a user actually picks
// a model: "what's fastest on my hardware?" / "what's most accurate if I
// don't mind waiting?" / "what's a one-click fallback?". The harness
// validation status (registry intel_gpu support) is the primary signal.
// ---------------------------------------------------------------------------

export type ModelCategory =
    | 'igpu_recommended'
    | 'cpu_high_accuracy'
    | 'cpu_standard'
    | 'cpu_alternative'
    | 'bundled';

export interface ModelCategoryInfo {
    label: string;
    hint: string;
    icon: string;
}

export const MODEL_CATEGORY_INFO: Record<ModelCategory, ModelCategoryInfo> = {
    igpu_recommended: {
        label: 'Fast on Intel GPU',
        hint: 'Validated on Intel iGPU: sub-second inference with confirmed-good predictions.',
        icon: '🚀',
    },
    cpu_high_accuracy: {
        label: 'Highest accuracy',
        hint: 'The broadest, most accurate option. Runtime speed depends on the provider validated on this hardware.',
        icon: '🎯',
    },
    cpu_standard: {
        label: 'Balanced',
        hint: 'A practical balance of accuracy, latency, and memory use.',
        icon: '⚖️',
    },
    cpu_alternative: {
        label: 'Architectural alternatives',
        hint: 'Experimental options for accuracy comparison via the model-evaluation harness.',
        icon: '🧪',
    },
    bundled: {
        label: 'Built-in fallback',
        hint: 'TFLite model bundled with the app. Always available without download.',
        icon: '📦',
    },
};

const CATEGORY_DISPLAY_ORDER: ModelCategory[] = [
    'igpu_recommended',
    'cpu_standard',
    'cpu_high_accuracy',
    'cpu_alternative',
    'bundled',
];

export function categorizeModel(model: ModelMetadata): ModelCategory {
    const providers = (model.supported_inference_providers || []).map((p) => p.toLowerCase());
    const tier = (model.tier || '').toLowerCase();
    const accuracy = (model.accuracy_tier || '').toLowerCase();
    const runtime = (model.runtime || '').toLowerCase();

    // The bundled-fallback path: TFLite-only legacy model that ships in the
    // image as a guaranteed-installable fallback.
    if (tier === 'cpu_only' || runtime === 'tflite') return 'bundled';

    // Registry declares intel_gpu support → harness-validated for iGPU.
    if (providers.includes('intel_gpu')) return 'igpu_recommended';

    // Heavy iNat21-class CPU classifiers (top accuracy, much slower).
    if (accuracy.includes('elite') || accuracy.includes('very high')) {
        return 'cpu_high_accuracy';
    }

    // Experimental / advanced-only options grouped together as
    // architectural alternatives users opt into for comparison.
    if (model.advanced_only) return 'cpu_alternative';

    return 'cpu_standard';
}

export interface ModelCategoryGroup {
    category: ModelCategory;
    info: ModelCategoryInfo;
    models: ModelMetadata[];
}

/**
 * Group classifier models for the Model Manager UI by recommended-use category.
 * Order within each group preserves compareTieredModelMetadata. Empty groups
 * are dropped so the UI doesn't render headers with no entries.
 */
export function groupTieredModelLineup(
    models: ModelMetadata[],
    showAdvanced: boolean = false,
    selectedOrActiveModelId?: string | null,
): ModelCategoryGroup[] {
    const visible = getVisibleTieredModelLineup(models, showAdvanced, selectedOrActiveModelId);
    const buckets = new Map<ModelCategory, ModelMetadata[]>();
    for (const cat of CATEGORY_DISPLAY_ORDER) buckets.set(cat, []);
    for (const m of visible) {
        const cat = categorizeModel(m);
        buckets.get(cat)!.push(m);
    }
    return CATEGORY_DISPLAY_ORDER
        .map((category) => ({
            category,
            info: MODEL_CATEGORY_INFO[category],
            models: buckets.get(category) || [],
        }))
        .filter((group) => group.models.length > 0);
}

function formatModelMetadataLabel(value: string): string {
    return value
        .split(/[_-]+/g)
        .filter(Boolean)
        .map((segment) => {
            const lower = segment.toLowerCase();
            if (lower === 'cpu') return 'CPU';
            if (lower === 'cuda') return 'CUDA';
            if (lower === 'onnx') return 'ONNX';
            if (lower === 'tflite') return 'TFLite';
            if (lower === 'intel') return 'Intel';
            return segment.slice(0, 1).toUpperCase() + segment.slice(1).toLowerCase();
        })
        .join(' ');
}

export function summarizeModelMetadata(metadata?: ModelMetadata | null): ModelMetadataSummary | null {
    if (!metadata) return null;

    const tierLabel = formatModelMetadataLabel(metadata.tier);
    const taxonomyScopeLabel = formatModelMetadataLabel(metadata.taxonomy_scope);
    const advancedStateLabel = metadata.advanced_only ? 'Advanced only' : 'Standard';
    const statusLabel = formatModelMetadataLabel(metadata.status ?? 'stable');

    return {
        tierLabel,
        taxonomyScopeLabel,
        advancedStateLabel,
        statusLabel,
        labels: [tierLabel, taxonomyScopeLabel, advancedStateLabel, statusLabel],
    };
}

export type InstalledModel = components['schemas']['InstalledModel'];

export type DownloadProgress = components['schemas']['DownloadProgress'];

export async function fetchAvailableModels(): Promise<ModelMetadata[]> {
    const response = await apiFetch(`${API_BASE}/models/available`);
    return handleResponse<ModelMetadata[]>(response);
}

export async function fetchInstalledModels(): Promise<InstalledModel[]> {
    const response = await apiFetch(`${API_BASE}/models/installed`);
    return handleResponse<InstalledModel[]>(response);
}

export type ModelActionResult = paths['/api/models/{model_id}/download']['post']['response'];

export async function downloadModel(modelId: string): Promise<ModelActionResult> {
    const response = await apiFetch(`${API_BASE}/models/${modelId}/download`, {
        method: 'POST',
    });
    return handleResponse<ModelActionResult>(response);
}

export async function fetchDownloadStatus(modelId: string): Promise<DownloadProgress | null> {
    const response = await apiFetch(`${API_BASE}/models/download-status/${encodeURIComponent(modelId)}`, {
        timeoutMs: 10_000
    });
    return handleResponse<DownloadProgress | null>(response);
}

export async function activateModel(modelId: string): Promise<ModelActionResult> {
    const response = await apiFetch(`${API_BASE}/models/${modelId}/activate`, {
        method: 'POST',
    });
    return handleResponse<ModelActionResult>(response);
}

export type ModelDeleteResult = components['schemas']['ModelDeleteResponse'];

export async function deleteModel(modelId: string): Promise<ModelDeleteResult> {
    // Region variants are addressed as `family/region`, so each segment is
    // encoded separately and the separating slash is preserved.
    const path = modelId.split('/').map(encodeURIComponent).join('/');
    const response = await apiFetch(`${API_BASE}/models/${path}`, {
        method: 'DELETE',
    });
    return handleResponse<ModelDeleteResult>(response);
}

export type ModelValidateResult = components['schemas']['ModelValidateResponse'];

/**
 * Validate an installed model on this host. The backend trial-activates it and
 * isolates every provider in the running image/host/model intersection, requiring
 * finite CPU-baseline-consistent output before recording eligibility and restoring
 * the previously active model.
 */
export async function validateModel(modelId: string): Promise<ModelValidateResult> {
    const response = await apiFetch(`${API_BASE}/models/${encodeURIComponent(modelId)}/validate`, {
        method: 'POST',
    });
    return handleResponse<ModelValidateResult>(response);
}

export async function analyzeDetection(
    eventId: string,
    force: boolean = false,
): Promise<{ analysis: string; analysis_timestamp: string }> {
    const url = force
        ? `${API_BASE}/events/${encodeURIComponent(eventId)}/analyze?force=true`
        : `${API_BASE}/events/${encodeURIComponent(eventId)}/analyze`;
    return fetchWithAbort<{ analysis: string; analysis_timestamp: string }>(
        `analyze-${eventId}`,
        url,
        { method: 'POST' }
    );
}

export interface ConversationTurn {
    role: 'user' | 'assistant';
    content: string;
    created_at: string;
}

export async function fetchDetectionConversation(eventId: string): Promise<ConversationTurn[]> {
    const response = await apiFetch(`${API_BASE}/events/${encodeURIComponent(eventId)}/conversation`);
    return handleResponse<ConversationTurn[]>(response);
}

export async function sendDetectionConversationMessage(eventId: string, message: string): Promise<ConversationTurn[]> {
    const response = await apiFetch(`${API_BASE}/events/${encodeURIComponent(eventId)}/conversation`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message })
    });
    return handleResponse<ConversationTurn[]>(response);
}

export type ProviderValidationStatus = components['schemas']['ProviderValidationStatus'];

export async function fetchProviderValidationStatus(): Promise<ProviderValidationStatus> {
    return handleResponse<ProviderValidationStatus>(await apiFetch(`${API_BASE}/classifier/provider-validation`));
}
