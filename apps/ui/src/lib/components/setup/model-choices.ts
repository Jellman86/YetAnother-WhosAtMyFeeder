import type { DeviceMatrix, ModelEvalModelSummary } from '../../api/model_eval';
import { parseInferenceProvider, type InferenceProvider } from '../../settings/inference-providers';

interface FeederCoordinates {
    latitude: number | null;
    longitude: number | null;
    error: 'incomplete' | 'range' | null;
}

export function feederCoordinates(latitude: string, longitude: string): FeederCoordinates {
    const lat = latitude.trim();
    const lon = longitude.trim();
    if (!lat && !lon) return { latitude: null, longitude: null, error: null };
    if (!lat || !lon) return { latitude: null, longitude: null, error: 'incomplete' };
    const numbers = { latitude: Number(lat), longitude: Number(lon), error: null };
    if (!Number.isFinite(numbers.latitude) || !Number.isFinite(numbers.longitude)
        || Math.abs(numbers.latitude) > 90 || Math.abs(numbers.longitude) > 180) {
        return { latitude: null, longitude: null, error: 'range' };
    }
    return numbers;
}

interface ValidationRecommendation {
    provider: InferenceProvider | null;
    medianMs: number | null;
    providers: InferenceProvider[];
}

export function validationRecommendation(
    modelId: string,
    summary: ModelEvalModelSummary | undefined,
    matrix: DeviceMatrix | null,
): ValidationRecommendation {
    const empty: ValidationRecommendation = { provider: null, medianMs: null, providers: [] };
    if (!summary?.ready || summary.model_id !== modelId || summary.warnings.some((warning) => warning.severity === 'critical')) return empty;
    const row = matrix?.models[modelId];
    if (row?.error) return empty;
    const entries = row?.providers ?? row?.devices;
    const passed = entries
        ? Object.entries(entries).filter(([, entry]) => entry.ok === true && entry.compiles !== false && entry.finite !== false).map(([provider]) => provider)
        : summary.validated_providers ?? [summary.active_provider ?? ''];
    const providers = passed.flatMap((value) => {
        const provider = parseInferenceProvider(value);
        return provider && provider !== 'auto' ? [provider] : [];
    });
    const best = parseInferenceProvider(row ? row.best_provider : summary.active_provider);
    const provider = best && best !== 'auto' && providers.includes(best) ? best : null;
    const latency = provider ? (entries ? entries[provider]?.latency_ms : summary.p50_latency_ms) : null;
    return { provider, medianMs: typeof latency === 'number' && Number.isFinite(latency) && latency >= 0 ? latency : null, providers };
}
