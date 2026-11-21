/** Facts about the running instance, worded from what was measured and nothing else. */

const RUNTIMES: Record<string, string> = {
    tflite: 'TFLite',
    onnxruntime: 'ONNX Runtime',
    onnx: 'ONNX Runtime',
    openvino: 'OpenVINO'
};

const DEVICES: Record<string, string> = {
    cpu: 'CPU',
    intel_cpu: 'CPU',
    intel_gpu: 'Intel GPU',
    intel_npu: 'Intel NPU',
    cuda: 'NVIDIA GPU'
};

export interface RuntimeDescription {
    runtime: string;
    /** Null when the classifier did not report a device it recognisably runs on. */
    device: string | null;
}

/** The device a provider runs on, as a product name; null for one it does not recognise. */
export function deviceName(provider: string | null | undefined): string | null {
    return DEVICES[provider?.trim().toLowerCase() ?? ''] ?? null;
}

/** The inference runtime and the device it runs on, as product names rather than config tokens. */
export function describeRuntime(
    classifier: { inference_backend?: string | null; active_provider?: string | null } | null | undefined
): RuntimeDescription | null {
    const backend = classifier?.inference_backend?.trim();
    if (!backend) return null;
    const provider = classifier?.active_provider?.trim().toLowerCase() ?? '';
    return { runtime: RUNTIMES[backend.toLowerCase()] ?? backend, device: deviceName(provider) };
}

type StartSource = { startup_started_at?: string | null } | null | undefined;

/** The process start time from the first source that measured one; null means not measured. */
export function startedAtFrom(...sources: StartSource[]): string | null {
    for (const source of sources) {
        const value = source?.startup_started_at;
        if (value && !Number.isNaN(Date.parse(value))) return value;
    }
    return null;
}
