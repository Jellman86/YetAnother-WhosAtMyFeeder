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
}

/**
 * The device a bird finder loads on. Like the backend's crop service, this is
 * the first provider in the host's current preference order, and CPU when the
 * host has no current evidence for that finder.
 */
export function birdFinderDevice(
    installed: Pick<InstalledModel, 'provider_preference_order' | 'preferred_inference_provider'> | undefined,
): BirdFinderDevice {
    const preferred = installed?.provider_preference_order?.[0];
    return preferred ? { provider: preferred, checked: true } : { provider: 'cpu', checked: false };
}
