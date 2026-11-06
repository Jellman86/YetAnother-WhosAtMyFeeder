import {
    fetchGardenIdentification,
    fetchGardenMotion,
    type GardenIdentificationStatus,
    type GardenMotionStatus
} from '../../api/garden';

/**
 * What the Garden service reports about itself: its models, country, last execution and collector.
 * The Garden card's status line, its models and its collection status all read one copy, so one
 * refresh updates all three and they can never disagree. The Garden API answers only while the
 * saved beta switch is on; the caller decides when to read.
 */
export class GardenServiceStatus {
    identification = $state.raw<GardenIdentificationStatus | null>(null);
    motion = $state.raw<GardenMotionStatus | null>(null);
    loading = $state(false);
    /** The first failure's message; an empty string when a read failed without one. */
    loadError = $state<string | null>(null);
    #generation = 0;

    async refresh(signal: AbortSignal = new AbortController().signal): Promise<void> {
        const request = ++this.#generation;
        this.loading = true;
        this.loadError = null;
        const [identification, motion] = await Promise.allSettled([fetchGardenIdentification(signal), fetchGardenMotion(signal)]);
        if (request !== this.#generation || signal.aborted) return;
        this.identification = identification.status === 'fulfilled' ? identification.value : null;
        this.motion = motion.status === 'fulfilled' ? motion.value : null;
        const failure = [identification, motion].find((result): result is PromiseRejectedResult => result.status === 'rejected');
        this.loadError = failure === undefined ? null : failure.reason instanceof Error ? failure.reason.message : '';
        this.loading = false;
    }

    /** Drops any read in flight, so a late answer cannot overwrite a newer one. */
    cancel(): void {
        this.#generation += 1;
        this.loading = false;
    }
}
