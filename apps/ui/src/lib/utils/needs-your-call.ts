import type { KeptBirdCandidate } from './domestic-birds';

/**
 * What the Dashboard's "Needs your call" panel may claim. Two readings feed it: the visits still
 * waiting for a species, and the species the range check flags as probably misnamed. Each part is
 * stated on its own, and "nothing waiting" is said only once both were measured as zero.
 */
export type ReadingStatus = 'loading' | 'ready' | 'unavailable';
/** The range check can also be switched off (no eBird or no feeder location): no pending work, nothing measured. */
export type ChecksStatus = ReadingStatus | 'off';
/** `stale`: work from an earlier read, shown with the failure of the latest one. */
type PartState = 'loading' | 'unavailable' | 'clear' | 'waiting' | 'stale' | 'off';

export interface NeedsYourCallInput {
    /** Reviewing is an owner capability; a guest is never shown the panel. */
    canReview: boolean;
    queueStatus: ReadingStatus;
    queueTotal: number;
    checksStatus: ChecksStatus;
    checkCount: number;
}

export interface NeedsYourCall {
    visible: boolean;
    visits: PartState;
    checks: PartState;
    /** Everything waiting on the owner: unidentified visits plus flagged species. */
    total: number;
    nothingWaiting: boolean;
}

// Work already shown stays shown while a later reading is in flight, and is marked stale when it fails.
function partState(status: ChecksStatus, count: number): PartState {
    if (count > 0) return status === 'unavailable' ? 'stale' : 'waiting';
    if (status === 'ready') return 'clear';
    return status;
}

export function needsYourCall(input: NeedsYourCallInput): NeedsYourCall {
    if (!input.canReview) return { visible: false, visits: 'clear', checks: 'clear', total: 0, nothingWaiting: false };
    const visits = partState(input.queueStatus, input.queueTotal);
    const checks = partState(input.checksStatus, input.checkCount);
    return {
        visible: true,
        visits,
        checks,
        total: input.queueTotal + input.checkCount,
        nothingWaiting: visits === 'clear' && checks === 'clear'
    };
}

/** The species the range check flags in the same 24 hours, named as the Species page names them. */
export interface SpeciesChecksView {
    status: ChecksStatus;
    names: string[];
    nearbyRadiusKm: number | null;
    /** For an owner with Garden on: flagged species that are a domestic bird under another name. */
    keptBirds: KeptBirdCandidate[];
}
