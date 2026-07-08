import type { ModelMetadata } from '../api/classifier';

export const CROP_MODEL_OVERRIDE_VALUES = ['default', 'on', 'off'] as const;
export const CROP_SOURCE_OVERRIDE_VALUES = ['default', 'standard', 'high_quality'] as const;

export type CropModelOverride = (typeof CROP_MODEL_OVERRIDE_VALUES)[number];
export type CropSourceOverride = (typeof CROP_SOURCE_OVERRIDE_VALUES)[number];

export interface CropVariantOverrideEntry {
    id: string;
    label: string;
    region: string;
}

type CropGeneratorDefaults = NonNullable<ModelMetadata['crop_generator']>;

export interface CropVariantMetadata {
    name?: string;
    region_scope?: string;
    crop_generator?: CropGeneratorDefaults;
}

export function normalizeCropModelOverride(
    value: string | null | undefined
): CropModelOverride {
    const candidate = String(value ?? '').trim().toLowerCase();
    return (CROP_MODEL_OVERRIDE_VALUES as readonly string[]).includes(candidate)
        ? (candidate as CropModelOverride)
        : 'default';
}

export function normalizeCropSourceOverride(
    value: string | null | undefined
): CropSourceOverride {
    const candidate = String(value ?? '').trim().toLowerCase();
    return (CROP_SOURCE_OVERRIDE_VALUES as readonly string[]).includes(candidate)
        ? (candidate as CropSourceOverride)
        : 'default';
}

export function normalizeCropOverrideMap<TValue extends string>(
    value: Record<string, string> | null | undefined,
    valueNormalizer: (incoming: string | null | undefined) => TValue
): Record<string, TValue> {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
        return {};
    }
    return Object.fromEntries(
        Object.entries(value).map(([key, rawValue]) => [key, valueNormalizer(rawValue)])
    );
}

export function resolveCropOverridesFromSettings(
    cropModelOverrides: Record<string, string> | null | undefined,
    cropSourceOverrides: Record<string, string> | null | undefined
): {
    cropModelOverrides: Record<string, CropModelOverride>;
    cropSourceOverrides: Record<string, CropSourceOverride>;
} {
    return {
        cropModelOverrides: normalizeCropOverrideMap(cropModelOverrides, normalizeCropModelOverride),
        cropSourceOverrides: normalizeCropOverrideMap(cropSourceOverrides, normalizeCropSourceOverride),
    };
}

function stripDefaultEntries<TValue extends string>(
    value: Record<string, TValue>,
    defaultValue: TValue
): Record<string, TValue> {
    return Object.fromEntries(
        Object.entries(value).filter(([, entryValue]) => entryValue !== defaultValue)
    );
}

export function buildCropOverrideSettings(
    cropModelOverrides: Record<string, CropModelOverride>,
    cropSourceOverrides: Record<string, CropSourceOverride>
): {
    crop_model_overrides: Record<string, CropModelOverride>;
    crop_source_overrides: Record<string, CropSourceOverride>;
} {
    return {
        crop_model_overrides: stripDefaultEntries(cropModelOverrides, 'default'),
        crop_source_overrides: stripDefaultEntries(cropSourceOverrides, 'default'),
    };
}

export function roundTripCropOverrides(
    incomingModelOverrides: Record<string, string> | null | undefined,
    incomingSourceOverrides: Record<string, string> | null | undefined,
    outgoingModelOverrides: Record<string, CropModelOverride>,
    outgoingSourceOverrides: Record<string, CropSourceOverride>
): {
    loaded: {
        modelOverrides: Record<string, CropModelOverride>;
        sourceOverrides: Record<string, CropSourceOverride>;
    };
    payload: {
        crop_model_overrides: Record<string, CropModelOverride>;
        crop_source_overrides: Record<string, CropSourceOverride>;
    };
} {
    const loaded = resolveCropOverridesFromSettings(incomingModelOverrides, incomingSourceOverrides);
    return {
        loaded: {
            modelOverrides: loaded.cropModelOverrides,
            sourceOverrides: loaded.cropSourceOverrides,
        },
        payload: buildCropOverrideSettings(outgoingModelOverrides, outgoingSourceOverrides),
    };
}

function isRecord(value: unknown): value is Record<string, unknown> {
    return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function cropGeneratorFromUnknown(value: unknown): CropGeneratorDefaults | undefined {
    if (!isRecord(value)) return undefined;
    return {
        enabled: typeof value.enabled === 'boolean' ? value.enabled : undefined,
        source_preference: typeof value.source_preference === 'string' ? value.source_preference : undefined,
        input_context: isRecord(value.input_context)
            ? { is_cropped: typeof value.input_context.is_cropped === 'boolean' ? value.input_context.is_cropped : undefined }
            : null,
    };
}

export function getCropVariantMetadata(
    model: Pick<ModelMetadata, 'region_variants'>,
    region: string
): CropVariantMetadata | undefined {
    const rawVariant = model.region_variants?.[region];
    if (!isRecord(rawVariant)) return undefined;
    return {
        name: typeof rawVariant.name === 'string' ? rawVariant.name : undefined,
        region_scope: typeof rawVariant.region_scope === 'string' ? rawVariant.region_scope : undefined,
        crop_generator: cropGeneratorFromUnknown(rawVariant.crop_generator),
    };
}

export function getCropVariantOverrideEntries(model: Pick<ModelMetadata, 'id' | 'family_id' | 'region_variants'>): CropVariantOverrideEntry[] {
    const familyId = String(model.family_id || model.id || '').trim();
    const regionVariants = model.region_variants || {};

    return Object.entries(regionVariants)
        .map(([region]) => {
            const variant = getCropVariantMetadata(model, region);
            return {
                id: `${familyId}.${region}`,
                label: variant?.name || variant?.region_scope || region.toUpperCase(),
                region,
            };
        })
        .sort((left, right) => left.label.localeCompare(right.label));
}
