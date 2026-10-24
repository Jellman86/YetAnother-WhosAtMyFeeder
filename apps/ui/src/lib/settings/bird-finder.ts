import type { InstalledModel } from '../api';

export type BirdFinder = 'yolox_tiny' | 'rfdetr_nano';

export const BIRD_FINDER_MODEL_IDS: Record<BirdFinder, string> = {
    yolox_tiny: 'bird_crop_detector_accurate_yolox_tiny',
    rfdetr_nano: 'bird_crop_detector_accurate_rfdetr_nano',
};

/** The saved finder, read the way the backend reads it: anything unknown is the YOLOX-Tiny default. */
export function parseBirdFinder(value: unknown): BirdFinder {
    return value === 'rfdetr_nano' ? 'rfdetr_nano' : 'yolox_tiny';
}

export interface BirdFinderDevice {
    provider: string;
    /** True only when this host holds current device-check evidence for the finder. */
    checked: boolean;
    /** Graphics and NPU devices the finder declares that this host offers; each still needs a passing check. */
    accelerators: string[];
}

const ACCELERATORS = ['intel_gpu', 'intel_npu', 'cuda'] as const;

/**
 * The device a bird finder loads on. Like the backend's crop service, this is
 * the first provider in the host's current preference order, and CPU when the
 * host has no current evidence for that finder.
 */
type FinderEvidence = Pick<InstalledModel, 'provider_preference_order' | 'preferred_inference_provider'> & {
    metadata?: Pick<NonNullable<InstalledModel['metadata']>, 'supported_inference_providers' | 'candidate_inference_providers'> | null;
};

export function birdFinderDevice(
    installed: FinderEvidence | undefined,
    hostProviders: readonly string[] = [],
): BirdFinderDevice {
    const declared = new Set([
        ...(installed?.metadata?.supported_inference_providers ?? []),
        ...(installed?.metadata?.candidate_inference_providers ?? []),
    ]);
    const accelerators = ACCELERATORS.filter((provider) => declared.has(provider) && hostProviders.includes(provider));
    const preferred = installed?.provider_preference_order?.[0];
    return preferred
        ? { provider: preferred, checked: true, accelerators }
        : { provider: 'cpu', checked: false, accelerators };
}

export type BirdFinderDeviceNote = 'checked' | 'cpu_only' | 'until_checked' | 'check_running' | 'check_failed' | 'check_waiting';

/** The startup re-check of a finder's previously passed accelerators, as the classifier status reports it. */
export interface BirdFinderDeviceCheck {
    state: string;
    model_id: string | null;
}

/** Which sentence describes where a finder runs, given its evidence and the automatic re-check. */
export function birdFinderDeviceNote(
    device: BirdFinderDevice,
    check: BirdFinderDeviceCheck | null | undefined,
    modelId: string,
): BirdFinderDeviceNote {
    if (device.checked) return 'checked';
    if (device.accelerators.length === 0) return 'cpu_only';
    if (check?.model_id === modelId) {
        if (check.state === 'running') return 'check_running';
        if (check.state === 'failed') return 'check_failed';
        if (check.state === 'waiting') return 'check_waiting';
    }
    return 'until_checked';
}
