import type { ClassifierStatus } from '../api/classifier';

export const INFERENCE_PROVIDERS = [
    'auto',
    'cpu',
    'cuda',
    'intel_gpu',
    'intel_cpu',
    'intel_npu',
] as const;

export type InferenceProvider = (typeof INFERENCE_PROVIDERS)[number];

export interface InferenceProviderChoice {
    value: InferenceProvider;
    unavailable: boolean;
}

const SELECTABLE_PROVIDERS = new Set<InferenceProvider>(INFERENCE_PROVIDERS.slice(1));

function isInferenceProvider(value: string | null | undefined): value is InferenceProvider {
    return INFERENCE_PROVIDERS.includes(value as InferenceProvider);
}

function uniqueSelectableProviders(values: string[] | null | undefined): InferenceProvider[] {
    const providers: InferenceProvider[] = [];
    for (const value of values ?? []) {
        if (!isInferenceProvider(value) || !SELECTABLE_PROVIDERS.has(value) || providers.includes(value)) {
            continue;
        }
        providers.push(value);
    }
    return providers;
}

export function getProviderPreferenceOrder(status: ClassifierStatus | null): InferenceProvider[] {
    if (!status) return [];
    const available = new Set(uniqueSelectableProviders(status.available_providers));
    return uniqueSelectableProviders(status.provider_preference_order).filter((provider) => available.has(provider));
}

export function getRuntimeProviderOrder(
    status: ClassifierStatus | null,
    supportedProviders?: string[] | null,
): InferenceProvider[] {
    if (!status) return [];

    const available = uniqueSelectableProviders(status.available_providers);
    const availableSet = new Set(available);
    const supported = uniqueSelectableProviders(supportedProviders);
    const supportedSet = new Set(supported);
    const activeProvider = isInferenceProvider(status.active_provider) && status.active_provider !== 'auto'
        ? status.active_provider
        : null;
    const preferenceOrder = uniqueSelectableProviders(status.provider_preference_order);

    if (preferenceOrder.length === 0) {
        return activeProvider && (available.length === 0 || availableSet.has(activeProvider))
            ? [activeProvider]
            : [];
    }

    const runtimeOrder = preferenceOrder.filter((provider) =>
        (available.length === 0 || availableSet.has(provider))
        && (provider === activeProvider || supported.length === 0 || supportedSet.has(provider))
    );

    // Live runtime state is stronger evidence than an installed model sidecar.
    // Keep the active provider visible while the backend reconciles stale metadata.
    if (
        activeProvider
        && (available.length === 0 || availableSet.has(activeProvider))
        && !runtimeOrder.includes(activeProvider)
    ) {
        runtimeOrder.unshift(activeProvider);
    }

    return runtimeOrder;
}

export function buildInferenceProviderChoices(
    status: ClassifierStatus | null,
    configuredProvider: string,
    prospectiveModelProviders?: string[] | null,
    validatedModelProviders?: string[] | null,
): InferenceProviderChoice[] {
    const choices: InferenceProviderChoice[] = [{ value: 'auto', unavailable: false }];
    const supported = uniqueSelectableProviders(prospectiveModelProviders);
    const available = status
        ? uniqueSelectableProviders(
            supported.length > 0
                ? (status.host_available_providers ?? status.available_providers)
                : status.available_providers
        )
        : [];
    const packaged = uniqueSelectableProviders(status?.packaged_inference_providers);
    const packagedSet = new Set(packaged);
    const packagedAvailable = packaged.length
        ? available.filter((provider) => packagedSet.has(provider))
        : available;
    let filteredAvailable = supported.length > 0
        ? packagedAvailable.filter((provider) => supported.includes(provider))
        : packagedAvailable;
    if (Array.isArray(validatedModelProviders)) {
        const validated = uniqueSelectableProviders(validatedModelProviders);
        filteredAvailable = filteredAvailable.filter((provider) => validated.includes(provider));
    }

    for (const provider of filteredAvailable) {
        choices.push({ value: provider, unavailable: false });
    }

    if (
        isInferenceProvider(configuredProvider)
        && configuredProvider !== 'auto'
        && !filteredAvailable.includes(configuredProvider)
    ) {
        choices.push({ value: configuredProvider, unavailable: true });
    }

    return choices;
}
