import type { GardenIdentificationStatus, GardenIdentifyRequest, GardenMotionStatus } from '../api/garden';

/**
 * Garden runs three models of its own, none of them the bird classifier: SpeciesNet's tracked-crop
 * variant checks every new capture and names confident animals, its whole-photo variant answers
 * owner species requests, and MegaDetector Cedar proposes animals from motion footage.
 */
export type GardenModelRole = 'automatic_check' | 'species_suggestions' | 'motion_detector';

type GardenVariant = NonNullable<GardenIdentifyRequest['variant']>;

type GardenModelInstall = { kind: 'speciesnet'; variant: GardenVariant } | { kind: 'motion' };

/** `unknown` means the status could not be read; it is never shown as ready. */
type GardenModelState = 'ready' | 'missing' | 'unavailable' | 'unknown';

export interface GardenModelRow {
    role: GardenModelRole;
    install: GardenModelInstall;
    requirement: 'required' | 'optional';
    state: GardenModelState;
    sizeBytes: number | null;
}

export type GardenSetupBlock = 'downloading' | 'busy' | 'error' | 'unknown';

function speciesNetRow(
    role: GardenModelRole,
    variant: GardenVariant,
    requirement: GardenModelRow['requirement'],
    status: GardenIdentificationStatus | null
): GardenModelRow {
    const model = status?.models.find(candidate => candidate.variant === variant);
    const state: GardenModelState = !status || !model
        ? 'unknown'
        : !status.catalogue_ready || status.error
            ? 'unavailable'
            : model.installed ? 'ready' : 'missing';
    return { role, install: { kind: 'speciesnet', variant }, requirement, state, sizeBytes: model?.size_bytes ?? null };
}

export function gardenModelRows(
    identification: GardenIdentificationStatus | null,
    motion: GardenMotionStatus | null,
    motionCameras: readonly string[]
): GardenModelRow[] {
    const motionState: GardenModelState = !motion
        ? 'unknown'
        : !motion.catalogue_ready ? 'unavailable' : motion.installed ? 'ready' : 'missing';
    return [
        speciesNetRow('automatic_check', '4.0.3a', 'required', identification),
        speciesNetRow('species_suggestions', '4.0.3b', 'optional', identification),
        {
            role: 'motion_detector',
            install: { kind: 'motion' },
            requirement: motionCameras.length > 0 ? 'required' : 'optional',
            state: motionState,
            sizeBytes: motion?.model_bytes ?? null
        }
    ];
}

/** Garden admits one operation at a time, so a download waits for any check, scan or download. */
export function gardenSetupBlock(
    identification: GardenIdentificationStatus | null,
    downloading: GardenModelRole | null
): GardenSetupBlock | null {
    if (downloading) return 'downloading';
    if (!identification) return 'unknown';
    if (identification.error) return 'error';
    if (identification.busy) return 'busy';
    return null;
}

export function formatModelSize(bytes: number): string {
    return `${Math.round(bytes / 1_000_000)} MB`;
}
