import { API_BASE, apiFetch, fetchWithAbort, handleResponse } from './core';
import type { components, paths } from './generated/openapi';

export type ClassifierStatus = components['schemas']['ClassifierStatusResponse'];

export async function fetchClassifierStatus(): Promise<ClassifierStatus> {
    const response = await apiFetch(`${API_BASE}/classifier/status`);
    return handleResponse<ClassifierStatus>(response);
}

/** The small CPU model: it runs on any machine, so it is where setup starts on a Raspberry Pi. */
const RECOMMENDED_SETUP_MODEL_ID = 'mobilenet_v2_birds';

/** Every model the setup step can offer: the catalogue, then installed models it does not list. */
export function setupModelOptions(available: ModelMetadata[], installed: InstalledModel[]): ModelMetadata[] {
    const listed = new Set(available.map((model) => model.id));
    const unlisted = installed.flatMap((model) => (model.metadata && !listed.has(model.id) ? [model.metadata] : []));
    return [...available, ...unlisted];
}

/**
 * The model the setup step opens on. It is always one the list can show: an id with no option
 * would leave the select blank and Continue disabled with nothing to explain it.
 */
export function selectSetupModelId(
    status: ClassifierStatus,
    available: ModelMetadata[],
    installed: InstalledModel[]
): string {
    const options = setupModelOptions(available, installed);
    const selectable = new Set(options.map((model) => model.id));
    const usable = installed.filter((model) => selectable.has(model.id));
    const candidates = [
        usable.find((model) => model.id === (status.effective_model_id ?? ''))?.id,
        usable.find((model) => model.is_active && model.ready !== false)?.id,
        status.image_flavor === 'rpi' ? usable.find((model) => model.id === RECOMMENDED_SETUP_MODEL_ID)?.id : undefined,
        usable.find((model) => model.ready !== false)?.id,
        status.image_flavor === 'rpi' ? RECOMMENDED_SETUP_MODEL_ID : undefined,
        status.active_model_id ?? undefined,
        RECOMMENDED_SETUP_MODEL_ID,
        options[0]?.id
    ];
    return candidates.find((id): id is string => Boolean(id) && selectable.has(id as string)) ?? '';
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

/** What a detection reads now, when a decision was taken on an identification that has since changed. */
export type CurrentIdentification = components['schemas']['CurrentIdentification'];
/** The 409 body of PATCH /api/events/{event_id}, as the API declares it. */
type IdentificationChangedResponse = components['schemas']['IdentificationChangedResponse'];

/** The server refused a decision because the visit was changed elsewhere after it was shown. */
export class IdentificationChangedError extends Error {
    readonly status = 409;
    readonly current: CurrentIdentification;

    constructor(message: string, current: CurrentIdentification) {
        super(message);
        this.name = 'IdentificationChangedError';
        this.current = current;
    }
}

function isIdentificationChanged(payload: unknown): payload is IdentificationChangedResponse {
    if (typeof payload !== 'object' || payload === null || !('detail' in payload)) return false;
    const detail = (payload as { detail: unknown }).detail;
    return typeof detail === 'object' && detail !== null && (detail as { code?: unknown }).code === 'identification_changed';
}

/**
 * Sets a detection's species. `shownCategoryName` is the identification the owner was looking at:
 * given, the server applies the change only while the detection still carries it, and otherwise
 * refuses with what it says now (IdentificationChangedError).
 */
export async function updateDetectionSpecies(eventId: string, displayName: string, shownCategoryName?: string | null): Promise<UpdateDetectionResult> {
    const body: components['schemas']['UpdateDetectionRequest'] = { display_name: displayName };
    if (shownCategoryName) body.expected_category_name = shownCategoryName;
    const response = await apiFetch(`${API_BASE}/events/${encodeURIComponent(eventId)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    if (response.status === 409) {
        const payload: unknown = await response.clone().json().catch(() => null);
        if (isIdentificationChanged(payload)) throw new IdentificationChangedError(payload.detail.message, payload.detail.current);
    }
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
// a model: "what is small and quick?" / "what is fastest on my hardware?" /
// "what is most accurate if I don't mind waiting?". Whether a model ships
// with the app is a fact about this install (InstalledModel.bundled), never
// a group name, so no group claims a model is built in.
// ---------------------------------------------------------------------------

export type ModelCategory =
    | 'compact'
    | 'igpu_recommended'
    | 'cpu_high_accuracy'
    | 'cpu_standard'
    | 'cpu_alternative';

/** Each group's heading, as an i18n key with its English text. */
export const MODEL_CATEGORY_LABEL: Record<ModelCategory, { key: string; fallback: string }> = {
    compact: { key: 'settings.models.group.compact', fallback: 'Small and quick' },
    cpu_standard: { key: 'settings.models.group.cpu_standard', fallback: 'Balanced' },
    igpu_recommended: { key: 'settings.models.group.igpu_recommended', fallback: 'Fast on Intel graphics' },
    cpu_high_accuracy: { key: 'settings.models.group.cpu_high_accuracy', fallback: 'Most accurate' },
    cpu_alternative: { key: 'settings.models.group.cpu_alternative', fallback: 'Experimental' },
};

const CATEGORY_DISPLAY_ORDER: ModelCategory[] = [
    'compact',
    'cpu_standard',
    'igpu_recommended',
    'cpu_high_accuracy',
    'cpu_alternative',
];

export function categorizeModel(model: ModelMetadata): ModelCategory {
    const providers = (model.supported_inference_providers || []).map((p) => p.toLowerCase());
    const tier = (model.tier || '').toLowerCase();
    const accuracy = (model.accuracy_tier || '').toLowerCase();
    const runtime = (model.runtime || '').toLowerCase();

    // The small TFLite model that runs on any CPU.
    if (tier === 'cpu_only' || runtime === 'tflite') return 'compact';

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
        buckets.get(cat)?.push(m);
    }
    return CATEGORY_DISPLAY_ORDER
        .map((category) => ({
            category,
            models: buckets.get(category) || [],
        }))
        .filter((group) => group.models.length > 0);
}

export type InstalledModel = components['schemas']['InstalledModel'];

export type DownloadProgress = components['schemas']['DownloadProgress'];

export async function fetchAvailableModels(): Promise<ModelMetadata[]> {
    const response = await apiFetch(`${API_BASE}/models/available`);
    return handleResponse<ModelMetadata[]>(response);
}

export type ResolvedModelFamilies = paths['/api/models/families/resolved']['get']['response'];

/** Which region each regional model family runs for, given the saved settings. Owner only. */
export async function fetchResolvedModelFamilies(): Promise<ResolvedModelFamilies> {
    const response = await apiFetch(`${API_BASE}/models/families/resolved`);
    return handleResponse<ResolvedModelFamilies>(response);
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
