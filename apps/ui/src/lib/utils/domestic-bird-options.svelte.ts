import { fetchGardenDomesticBirds } from '../api/garden';
import type { DomesticBirdOption } from './domestic-birds';
import { getErrorMessage } from './error-handling';
import { logger } from './logger';

/**
 * The domestic birds an owner can keep, read while `enabled` holds (an owner with Garden on).
 * Without them a flagged species is simply not offered as a kept bird; nothing else changes.
 * Call during component initialisation; the read follows the component's lifetime.
 */
export class DomesticBirdOptions {
    options = $state.raw<DomesticBirdOption[]>([]);
    #run = $state(0);

    constructor(enabled: () => boolean) {
        $effect(() => {
            void this.#run;
            if (!enabled()) {
                this.options = [];
                return;
            }
            const controller = new AbortController();
            fetchGardenDomesticBirds(controller.signal)
                .then((options) => {
                    if (!controller.signal.aborted) this.options = options;
                })
                .catch((error: unknown) => logger.debug('Domestic bird options unavailable', { message: getErrorMessage(error) }));
            return () => controller.abort();
        });
    }

    /** A kept bird becomes declared, so its offer changes wording. */
    reload(): void {
        this.#run += 1;
    }
}
