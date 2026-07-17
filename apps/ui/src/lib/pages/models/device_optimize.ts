import type { DeviceMatrix } from '../../api/model_eval';

/**
 * Map an OpenVINO sweep device to the inference-provider setting value.
 * The device sweep enumerates CPU / GPU / NPU (optionally suffixed, e.g. "GPU.0").
 */
const DEVICE_TO_PROVIDER: Record<string, string> = {
    CPU: 'intel_cpu',
    GPU: 'intel_gpu',
    NPU: 'intel_npu'
};

export interface OptimalDevice {
    device: string;
    provider: string;
    latencyMs: number;
}

/**
 * Pick the fastest device that is safe to use for `modelId` from a device sweep.
 *
 * A device qualifies only when it compiled, produced finite output, and — for an
 * accelerator — agreed with the CPU baseline on the sampled images (`matches_cpu`).
 * CPU is its own baseline and always qualifies if it compiled. Among qualifying
 * devices the lowest measured latency wins. Returns null when nothing beats a plain
 * CPU/Auto setup (e.g. a host with no OpenVINO accelerators, or where only CPU passed).
 */
export function pickFastestProvider(matrix: DeviceMatrix | null, modelId: string): OptimalDevice | null {
    const devices = matrix?.models?.[modelId]?.devices;
    if (!devices) return null;

    let best: OptimalDevice | null = null;
    for (const [deviceKey, entry] of Object.entries(devices)) {
        const base = deviceKey.split('.')[0].toUpperCase();
        const provider = DEVICE_TO_PROVIDER[base];
        if (!provider) continue;

        const finiteOk = entry.finite !== false; // undefined (not measured) is not a failure
        const agreesWithCpu = base === 'CPU' || entry.matches_cpu === true;
        const qualifies = entry.compiles && finiteOk && agreesWithCpu;
        if (!qualifies || entry.latency_ms == null) continue;

        if (!best || entry.latency_ms < best.latencyMs) {
            best = { device: base, provider, latencyMs: entry.latency_ms };
        }
    }
    return best;
}
