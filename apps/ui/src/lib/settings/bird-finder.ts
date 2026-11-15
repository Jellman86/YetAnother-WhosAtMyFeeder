import type { SettingsUpdate } from '../api/settings';
import type { InstalledModel } from '../api';

export type BirdFinderProvider = NonNullable<SettingsUpdate['bird_crop_inference_provider']>;

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
type DeclaredProviders = Pick<NonNullable<InstalledModel['metadata']>, 'supported_inference_providers' | 'candidate_inference_providers'>;

type FinderEvidence = Pick<InstalledModel, 'provider_preference_order' | 'preferred_inference_provider'> & {
    metadata?: DeclaredProviders | null;
};

export function birdFinderDevice(
    installed: FinderEvidence | undefined,
    hostProviders: readonly string[] = [],
    /** The registry's entry for the finder, which declares its devices even before a download. */
    registry?: DeclaredProviders,
): BirdFinderDevice {
    const source = registry ?? installed?.metadata;
    const declared = new Set([
        ...(source?.supported_inference_providers ?? []),
        ...(source?.candidate_inference_providers ?? []),
    ]);
    const accelerators = ACCELERATORS.filter((provider) => declared.has(provider) && hostProviders.includes(provider));
    const preferred = installed?.provider_preference_order?.[0];
    return preferred
        ? { provider: preferred, checked: true, accelerators }
        : { provider: 'cpu', checked: false, accelerators };
}

/** The finder's device check as the classifier status reports it. */
export interface FinderDeviceCheck {
    state: string;
    model_id: string | null;
    providers?: string[] | null;
    reason?: string | null;
    checked_at?: string | null;
}

/** Why a check failed, when the backend's reason is one this page can state as a measured fact. */
type FinderCheckCause = 'mismatch' | 'unfinished' | null;

/** The one measured fact the "Runs on" row states. Every kind but `passed` and `checking` runs on the CPU. */
export type FinderRunsOn =
    | { kind: 'not_downloaded' }
    | { kind: 'checking'; devices: string[] }
    | { kind: 'passed'; provider: string; checkedAt: string | null }
    | { kind: 'cpu_chosen' }
    | { kind: 'failed'; devices: string[]; checkedAt: string | null; cause: FinderCheckCause }
    | { kind: 'interrupted'; devices: string[]; checkedAt: string | null }
    | { kind: 'waiting'; devices: string[] }
    | { kind: 'never_checked' }
    | { kind: 'cpu_only' };

export interface FinderRunsOnInput {
    installed: boolean;
    /** The finder's current passing evidence on this host, fastest first. */
    evidence: readonly string[];
    /** Graphics and NPU devices this host offers the finder. */
    accelerators: readonly string[];
    savedProvider: string;
    check: FinderDeviceCheck | null | undefined;
    modelId: string;
    /** A check the owner started from this page is running. */
    checkRunning: boolean;
}

// The backend reports its reason as a sentence. Only the two it is known to write are read as a
// cause; anything else is left unsaid rather than guessed at.
function finderCheckCause(reason: string | null | undefined): FinderCheckCause {
    if (!reason) return null;
    if (reason.includes('did not match the CPU')) return 'mismatch';
    if (reason.includes('could not finish')) return 'unfinished';
    return null;
}

/**
 * Where the finder runs and why, from evidence only: the host's passing checks, the saved device,
 * and the last device check the backend reports for this finder. Passing evidence outranks an
 * older failed check, because a later check from this page replaces the evidence, not the report.
 */
export function finderRunsOn(input: FinderRunsOnInput): FinderRunsOn {
    const { installed, evidence, accelerators, savedProvider, modelId, checkRunning } = input;
    if (!installed) return { kind: 'not_downloaded' };
    const check = input.check?.model_id === modelId ? input.check : null;
    const checkedDevices = check?.providers?.length ? [...check.providers] : null;
    const specific = savedProvider !== 'auto' && savedProvider !== 'cpu' ? savedProvider : null;
    const wantedDevices = checkedDevices ?? (specific ? [specific] : [...accelerators]);
    if (checkRunning || check?.state === 'running') return { kind: 'checking', devices: wantedDevices };
    if (savedProvider === 'cpu') return { kind: 'cpu_chosen' };
    const running = specific ? (evidence.includes(specific) ? specific : undefined) : evidence[0];
    if (running && running !== 'cpu') {
        const measured = check?.state === 'succeeded' && (check.providers ?? []).includes(running);
        return { kind: 'passed', provider: running, checkedAt: measured ? (check.checked_at ?? null) : null };
    }
    if (check?.state === 'failed') {
        return { kind: 'failed', devices: wantedDevices, checkedAt: check.checked_at ?? null, cause: finderCheckCause(check.reason) };
    }
    if (check?.state === 'interrupted') return { kind: 'interrupted', devices: wantedDevices, checkedAt: check.checked_at ?? null };
    if (check?.state === 'waiting') return { kind: 'waiting', devices: wantedDevices };
    return specific || accelerators.length > 0 ? { kind: 'never_checked' } : { kind: 'cpu_only' };
}

export interface FinderDeviceOption {
    value: string;
    /** This host holds a passing check for the finder on this device. */
    passed: boolean;
    /** The server would accept this choice: it passed, or it is the saved device, left as it is. */
    selectable: boolean;
}

const DEVICE_ORDER = ['intel_cpu', 'intel_gpu', 'intel_npu', 'cuda'] as const;

/**
 * The devices offered after Automatic and CPU: those this host offers the finder, any with passing
 * evidence, and the chosen one, so a saved device is never missing from its own list. The server
 * refuses a newly chosen device without a passing check and keeps an unchanged one, so only
 * `keepable` (the saved device, while the saved finder is still chosen) stays selectable unpassed.
 */
export function finderDeviceOptions(input: {
    evidence: readonly string[];
    accelerators: readonly string[];
    hostProviders: readonly string[];
    chosen: string;
    keepable: string | null;
}): FinderDeviceOption[] {
    const { evidence, accelerators, hostProviders, chosen, keepable } = input;
    return DEVICE_ORDER
        .filter((device) => accelerators.includes(device)
            || evidence.includes(device)
            || chosen === device
            || (device === 'intel_cpu' && hostProviders.includes(device)))
        .map((device) => {
            const passed = evidence.includes(device);
            return { value: device, passed, selectable: passed || device === keepable };
        });
}
