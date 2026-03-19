export const BIRD_MODEL_REGION_OVERRIDE_VALUES = ['auto', 'eu', 'na'] as const;

export type BirdModelRegionOverride = (typeof BIRD_MODEL_REGION_OVERRIDE_VALUES)[number];

export function normalizeBirdModelRegionOverride(
    value: string | null | undefined
): BirdModelRegionOverride {
    const candidate = String(value ?? '').trim().toLowerCase();
    return (BIRD_MODEL_REGION_OVERRIDE_VALUES as readonly string[]).includes(candidate)
        ? (candidate as BirdModelRegionOverride)
        : 'auto';
}

export function resolveBirdModelRegionOverrideFromSettings(
    value: string | null | undefined
): BirdModelRegionOverride {
    return normalizeBirdModelRegionOverride(value);
}

export function buildBirdModelRegionOverrideSettings(
    value: BirdModelRegionOverride
): { bird_model_region_override: BirdModelRegionOverride } {
    return { bird_model_region_override: value };
}

export function roundTripBirdModelRegionOverride(
    incoming: string | null | undefined,
    outgoing: BirdModelRegionOverride
): {
    loaded: BirdModelRegionOverride;
    payload: { bird_model_region_override: BirdModelRegionOverride };
} {
    return {
        loaded: resolveBirdModelRegionOverrideFromSettings(incoming),
        payload: buildBirdModelRegionOverrideSettings(outgoing),
    };
}
