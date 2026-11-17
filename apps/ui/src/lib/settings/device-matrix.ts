import type { DeviceMatrix } from '../api/model_eval';
import { INFERENCE_PROVIDERS, type InferenceProvider } from './inference-providers';

/** The i18n key and English fallback naming each provider. */
export const INFERENCE_PROVIDER_LABELS: Readonly<Record<InferenceProvider, { key: string; fallback: string }>> = {
    auto: { key: 'settings.detection.provider_auto', fallback: 'Auto (recommended)' },
    cpu: { key: 'settings.detection.provider_cpu', fallback: 'CPU (ONNX Runtime)' },
    cuda: { key: 'settings.detection.provider_cuda', fallback: 'NVIDIA CUDA' },
    intel_gpu: { key: 'settings.detection.provider_intel_gpu', fallback: 'Intel GPU (OpenVINO)' },
    intel_cpu: { key: 'settings.detection.provider_intel_cpu', fallback: 'Intel CPU (OpenVINO)' },
    intel_npu: { key: 'settings.detection.provider_intel_npu', fallback: 'Intel NPU (OpenVINO)' }
};

export function isInferenceProvider(value: string): value is InferenceProvider {
    return (INFERENCE_PROVIDERS as readonly string[]).includes(value);
}

/** The providers a device check covered, newest result shape first. */
export function compatProviders(matrix: DeviceMatrix): string[] {
    return matrix.providers?.length ? matrix.providers : matrix.devices;
}

export type CompatRow = DeviceMatrix['models'][string] | NonNullable<DeviceMatrix['crop_detectors']>[string];

/** Every model the check ran, identification models then bird finders. */
export function compatRows(matrix: DeviceMatrix): Array<[string, CompatRow]> {
    return [...Object.entries(matrix.models), ...Object.entries(matrix.crop_detectors ?? {})];
}

export function compatEntry(row: CompatRow | undefined, provider: string) {
    return row?.providers?.[provider] ?? row?.devices?.[provider];
}
