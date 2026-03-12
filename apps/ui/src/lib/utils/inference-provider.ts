export type InferenceKind = 'gpu' | 'cpu' | null;

export function classifyInferenceProvider(
    provider?: string | null,
    backend?: string | null
): { kind: InferenceKind; label: string } {
    const providerNormalized = String(provider ?? '').trim().toLowerCase();
    const backendNormalized = String(backend ?? '').trim().toLowerCase();

    if (
        providerNormalized.includes('gpu') ||
        providerNormalized === 'cuda' ||
        backendNormalized === 'cuda'
    ) {
        return { kind: 'gpu', label: 'GPU' };
    }

    if (
        providerNormalized.includes('cpu') ||
        providerNormalized === 'tflite' ||
        backendNormalized.includes('cpu') ||
        backendNormalized === 'tflite'
    ) {
        return { kind: 'cpu', label: 'CPU' };
    }

    return { kind: null, label: 'Unknown' };
}
