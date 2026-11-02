import { fetchGardenDomesticBirds } from '../api/garden';
import {
    keptBirdCandidates,
    offersStillOpen,
    type DomesticBirdKey,
    type DomesticBirdOption,
    type KeptBirdCandidate
} from './domestic-birds';
import { getErrorMessage } from './error-handling';
import { logger } from './logger';

/**
 * The kept-bird offers for flagged species, shared by the Species page and the Dashboard. The
 * domestic birds an owner can keep are read while `enabled` holds (an owner with Garden on);
 * without them a flagged species is simply not offered as a kept bird. A bird kept since the
 * flagged list was last measured is never offered again until a fresh read succeeds, so a failed
 * reload cannot leave an action that has already been taken.
 * Call during component initialisation; the read follows the component's lifetime.
 */
export class DomesticBirdOffers {
    #options = $state.raw<DomesticBirdOption[]>([]);
    #keptSinceRead = $state.raw<ReadonlySet<DomesticBirdKey>>(new Set());
    #run = $state(0);

    constructor(enabled: () => boolean) {
        $effect(() => {
            void this.#run;
            if (!enabled()) {
                this.#options = [];
                return;
            }
            const controller = new AbortController();
            fetchGardenDomesticBirds(controller.signal)
                .then((options) => {
                    if (!controller.signal.aborted) this.#options = options;
                })
                .catch((error: unknown) => logger.debug('Domestic bird options unavailable', { message: getErrorMessage(error) }));
            return () => controller.abort();
        });
    }

    /** The offers for these flagged rows, without any bird kept since they were measured. */
    offersFor(rows: readonly { displayName: string; scientificName: string | null }[]): KeptBirdCandidate[] {
        return offersStillOpen(keptBirdCandidates(rows, this.#options), this.#keptSinceRead);
    }

    /** A bird's records moved to Garden: close its offer now, and read the options again (it is declared). */
    kept(bird: DomesticBirdKey): void {
        this.#keptSinceRead = new Set([...this.#keptSinceRead, bird]);
        this.#run += 1;
    }

    /** The flagged list was measured afresh, so it alone decides what is offered. */
    measured(): void {
        if (this.#keptSinceRead.size > 0) this.#keptSinceRead = new Set();
    }
}
