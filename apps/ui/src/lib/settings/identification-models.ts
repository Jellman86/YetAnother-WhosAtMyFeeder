import type { ClassifierStatus, ModelMetadata } from '../api/classifier';
import { deviceName } from '../utils/instance-facts';

/**
 * What names the birds right now, worded from the classifier's own report. Models, the first-run
 * wizard and About all say this with the same sentence, so none of them can contradict another.
 */
export type IdentificationStatus =
    | { kind: 'checking' }
    /** The chosen model's files are not on this install, so nothing can name birds. */
    | { kind: 'missing'; modelId: string | null; modelName: string | null }
    /** Workers start on the first detection; until then the device is the plan, not a fact. */
    | { kind: 'planned'; modelId: string | null; modelName: string | null; device: string | null }
    | {
          kind: 'running';
          modelId: string | null;
          modelName: string | null;
          device: string | null;
          species: number | null;
          /** Why it runs somewhere other than chosen: the device failed, or the isolated workers keep stopping. */
          fallback: 'device' | 'workers' | null;
      };

export function identificationStatus(status: ClassifierStatus | null | undefined): IdentificationStatus {
    if (!status) return { kind: 'checking' };
    const modelId = status.effective_model_id ?? status.active_model_id ?? null;
    const modelName = status.effective_model_name ?? null;
    if (status.active_model_installed === false) return { kind: 'missing', modelId, modelName };
    const device = deviceName(status.active_provider);
    if (status.runtime_source === 'planned') return { kind: 'planned', modelId, modelName, device };
    const fallback = status.worker_in_process_fallback?.active ? 'workers' : status.fallback_reason ? 'device' : null;
    const species = status.labels_count && status.labels_count > 0 ? status.labels_count : null;
    return { kind: 'running', modelId, modelName, device, species, fallback };
}

type Translate = (key: string, options?: { default?: string; values?: Record<string, string | number> }) => string;

/**
 * The name an owner chooses by: what the model is for. The catalogue's code name ("RoPE ViT-B14")
 * stays beside it as the technical name, for comparing with Model evaluation and the docs.
 */
const PURPOSE_NAMES: Record<string, string> = {
    mobilenet_v2_birds: 'Small and quick, birds worldwide',
    small_birds: 'Birds of your region, quick',
    medium_birds: 'Birds of your region, more accurate',
    convnext_large_inat21: 'Birds and wildlife, high accuracy',
    eu_medium_focalnet_b: 'European birds, accurate',
    flexivit_il_all: 'Birds of Israel, quick',
    rope_vit_b14_inat21: 'Birds and wildlife, balanced',
    eva02_large_inat21: 'Birds and wildlife, most accurate',
    dinov2_b14_inat21_metadata_336: 'Birds and wildlife, uses your location',
    rope_vit_b14_inat21_336: 'Birds and wildlife, finer detail',
    rope_vit_b14_eu_common_336: 'Common European birds, balanced',
    rope_deit3_m14_arabian_peninsula: 'Birds of the Arabian Peninsula',
    naflex_so150m_eu_common: 'Common European birds, large',
    naflex_so150m_il_all: 'Birds of Israel, large',
    vit_parallel_s16_eu_common: 'Common European birds, compact',
    bioclip25_inat9025: 'Birds and wildlife, broad coverage',
};

/** A regional variant ("small_birds/eu") is named for its family. */
function familyId(modelId: string): string {
    return modelId.split('/')[0];
}

export function identificationModelName(
    model: { id: string; name?: string | null },
    translate: Translate
): { name: string; technical: string | null } {
    const id = familyId(model.id);
    const catalogueName = (model.name ?? '').trim() || model.id;
    const purpose = PURPOSE_NAMES[id];
    if (!purpose) return { name: catalogueName, technical: null };
    // The bracketed words in catalogue names ("(Fast)", "(Elite Accuracy)") repeat the purpose.
    const technical = catalogueName.replace(/\s*\([^)]*\)\s*$/, '').trim() || catalogueName;
    return { name: translate(`settings.models.purpose.${id}`, { default: purpose }), technical };
}

function sizeText(megabytes: number, translate: Translate): string {
    if (megabytes >= 1000) {
        return translate('settings.models.size_gb', { default: '{size} GB', values: { size: (megabytes / 1000).toFixed(1) } });
    }
    return translate('settings.models.size_mb', { default: '{size} MB', values: { size: Math.max(1, Math.round(megabytes)) } });
}

function memoryText(ramMb: number, translate: Translate): string {
    const size = ramMb >= 1024
        ? translate('settings.models.size_gb', { default: '{size} GB', values: { size: (ramMb / 1024).toFixed(1) } })
        : translate('settings.models.size_mb', { default: '{size} MB', values: { size: Math.round(ramMb) } });
    return translate('settings.models.fact_memory', { default: 'about {size} memory', values: { size } });
}

/** The everyday costs of a model in one sentence-case line: coverage, getting it, and memory. */
export function modelFactsLine(
    model: ModelMetadata,
    install: { installed: boolean; bundled?: boolean },
    translate: Translate
): string {
    const scope = model.taxonomy_scope === 'wildlife_wide'
        ? translate('settings.models.fact_wildlife', { default: 'Birds and other wildlife' })
        : translate('settings.models.fact_birds_only', { default: 'Birds only' });
    const source = install.bundled
        ? translate('settings.models.fact_bundled', { default: 'comes with the app' })
        : install.installed
            ? translate('settings.models.fact_installed', { default: 'on this install' })
            : translate('settings.models.fact_download', {
                default: '{size} download',
                values: { size: sizeText(model.file_size_mb ?? 0, translate) },
            });
    const facts = [scope, source];
    if (model.estimated_ram_mb != null) facts.push(memoryText(model.estimated_ram_mb, translate));
    return facts.join(' · ');
}

/** Only the models an owner is likely to need next are recommended, in this order. */
const RECOMMENDATION_ORDER = ['small_birds', 'rope_vit_b14_inat21'];
const STARTER_MODEL_ID = 'mobilenet_v2_birds';

/**
 * One model worth moving to, or none. An install still on the small starter model, or with nothing
 * that can name birds, is offered the next step up; a deliberate fuller choice is left alone.
 * A Raspberry Pi image is only ever offered the starter model.
 */
export function recommendIdentificationModel(
    models: readonly ModelMetadata[],
    context: { currentId: string | null; imageFlavor?: string | null }
): ModelMetadata | null {
    const current = context.currentId ? familyId(context.currentId) : null;
    if (current !== null && current !== STARTER_MODEL_ID) return null;
    const order = context.imageFlavor === 'rpi' ? [STARTER_MODEL_ID] : RECOMMENDATION_ORDER;
    for (const id of order) {
        if (id === current) continue;
        const candidate = models.find((entry) => familyId(entry.id) === id && (entry.artifact_kind || 'classifier') === 'classifier');
        if (candidate) return candidate;
    }
    return null;
}
