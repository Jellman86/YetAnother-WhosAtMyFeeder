/** The Models tab's Runtime report: where a runtime problem is shown. */
export const RUNTIME_DISCLOSURES = ['detection-inference-advanced'] as const;

/** The parts of the classifier status that report a problem the owner must act on. */
interface RuntimeStatus {
    fallback_reason?: string | null;
    model_config_warnings?: readonly string[] | null;
    openvino_model_compile_ok?: boolean | null;
    image_flavor_warning?: string | null;
    cuda_probe_error?: string | null;
}

/**
 * A stable name for the runtime problems reported now, or null when there are none. The same
 * problems give the same name on every poll, so a section the owner closed on them stays closed,
 * while a different problem gives a different name and opens it again.
 */
export function runtimeProblemKey(
    status: RuntimeStatus | null,
    flags: { videoCircuitOpen: boolean; autoVideoClassification: boolean }
): string | null {
    const parts = [
        status?.fallback_reason ? `fallback:${status.fallback_reason}` : null,
        ...(status?.model_config_warnings ?? []).map((warning) => `config:${warning}`),
        status?.openvino_model_compile_ok === false ? 'compile:openvino' : null,
        status?.image_flavor_warning ? `image:${status.image_flavor_warning}` : null,
        status?.cuda_probe_error ? `cuda:${status.cuda_probe_error}` : null,
        flags.autoVideoClassification && flags.videoCircuitOpen ? 'circuit:video' : null
    ].filter((part): part is string => part !== null);
    return parts.length > 0 ? parts.join('|') : null;
}
