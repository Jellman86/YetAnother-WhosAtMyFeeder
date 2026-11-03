import type { components } from '../api/generated/openapi';
import type { GardenModelRole, GardenModelRow } from './garden-models';

/**
 * What a beta feature card says about Garden animals in one line, and what is still left for the
 * owner to do. Both come from the draft switch, the applied switch and what the Garden service has
 * measured: a reading the server has not made (status not loaded, Garden not applied yet) is left
 * out rather than guessed.
 */

export type ExecutionProvider = components['schemas']['InferenceExecution']['provider'];

/** Device names are product names, so they are not translated. */
export const EXECUTION_DEVICE_LABEL: Record<ExecutionProvider, string> = {
    intel_npu: 'NPU',
    intel_gpu: 'Intel GPU',
    intel_cpu: 'Intel CPU',
    cuda: 'NVIDIA GPU',
    cpu: 'CPU'
};

export interface GardenBetaInput {
    /** The switch as staged in the Settings draft. */
    enabled: boolean;
    /** The switch as the server has it; Garden's status can only be read once this is on. */
    savedEnabled: boolean;
    /** Cameras watching for Garden animals, as staged in Connection. */
    cameras: readonly string[];
    models: readonly GardenModelRow[];
    /** The country Garden names animals for; null when Garden reported none, undefined when unread. */
    country: string | null | undefined;
    /** The device the last automatic check actually ran on, if one has reported. */
    lastProvider: ExecutionProvider | null;
}

export type GardenStatusPart =
    | { kind: 'off' }
    | { kind: 'off_after_apply' }
    | { kind: 'on' }
    | { kind: 'on_after_apply' }
    | { kind: 'cameras'; count: number }
    | { kind: 'device'; provider: ExecutionProvider }
    | { kind: 'model_missing' }
    | { kind: 'no_country' };

export type GardenNextStep =
    | { kind: 'choose_camera' }
    | { kind: 'apply' }
    | { kind: 'download_model'; role: GardenModelRole }
    | { kind: 'set_location' };

export interface GardenBetaSummary {
    parts: GardenStatusPart[];
    steps: GardenNextStep[];
    /** True only when a step needs the owner; a pending Apply is the save bar's to announce. */
    attention: boolean;
}

export function gardenBetaSummary(input: GardenBetaInput): GardenBetaSummary {
    if (!input.enabled) {
        return { parts: [{ kind: input.savedEnabled ? 'off_after_apply' : 'off' }], steps: [], attention: false };
    }

    const parts: GardenStatusPart[] = [{ kind: input.savedEnabled ? 'on' : 'on_after_apply' }, { kind: 'cameras', count: input.cameras.length }];
    const steps: GardenNextStep[] = input.cameras.length === 0 ? [{ kind: 'choose_camera' }] : [];

    if (!input.savedEnabled) {
        steps.push({ kind: 'apply' });
        return { parts, steps, attention: steps.some(step => step.kind !== 'apply') };
    }

    if (input.lastProvider) parts.push({ kind: 'device', provider: input.lastProvider });
    const missing = input.models.filter(model => model.requirement === 'required' && model.state === 'missing');
    if (missing.length > 0) parts.push({ kind: 'model_missing' });
    if (input.country === null) parts.push({ kind: 'no_country' });

    steps.push(...missing.map(model => ({ kind: 'download_model' as const, role: model.role })));
    if (input.country === null) steps.push({ kind: 'set_location' });

    return { parts, steps, attention: steps.length > 0 };
}

type GardenExecution = components['schemas']['InferenceExecution'];

/**
 * The device fact in Collection status. A preferred device is only "used" once a check actually
 * ran on it; a CPU fallback leaves it unused, so the box never claims an accelerator that did not run.
 */
export type GardenDeviceFact =
    | { kind: 'preferred_used'; provider: ExecutionProvider }
    | { kind: 'preferred_unused'; provider: ExecutionProvider }
    | { kind: 'ran'; provider: ExecutionProvider }
    | { kind: 'not_used' };

export interface GardenCollectionFacts {
    device: GardenDeviceFact;
    lastCheck: { provider: ExecutionProvider; checkedAt: string; fallback: boolean } | null;
    /** Cameras collecting motion photos; null when the motion status could not be read. */
    motionCameras: string[] | null;
}

export function gardenCollectionFacts(
    identification: { preferred_provider?: ExecutionProvider; last_execution?: GardenExecution | null } | null,
    motion: { cameras: string[] } | null
): GardenCollectionFacts {
    const execution = identification?.last_execution ?? null;
    const preferred = identification?.preferred_provider;
    const device: GardenDeviceFact = preferred
        ? { kind: execution?.provider === preferred ? 'preferred_used' : 'preferred_unused', provider: preferred }
        : execution
            ? { kind: 'ran', provider: execution.provider }
            : { kind: 'not_used' };
    return {
        device,
        lastCheck: execution ? { provider: execution.provider, checkedAt: execution.checked_at, fallback: Boolean(execution.fallback_reason) } : null,
        motionCameras: motion ? [...motion.cameras] : null
    };
}
