import type { EventFilters, FetchEventFiltersOptions } from '../api';

/**
 * Latest projection wins; a failed guest invalidation must not retain old facets. A read is also
 * discarded once `invalidate` is called, so a newer read can be scheduled before it starts, and
 * once its caller's `isCurrent` says no: no answer to a replaced read is ever applied.
 */
export function createEventMetadataRefresh(options: {
    fetch: (options: FetchEventFiltersOptions) => Promise<EventFilters>;
    apply: (filters: EventFilters) => void;
    clear: () => void;
    isGuest: () => boolean;
}) {
    let generation = 0;
    return {
        invalidate(): void {
            generation += 1;
        },
        async load(
            forceRefresh = false,
            counted: Omit<FetchEventFiltersOptions, 'forceRefresh'> = {},
            isCurrent: () => boolean = () => true
        ): Promise<EventFilters | null> {
            const requestGeneration = ++generation;
            const current = (): boolean => requestGeneration === generation && isCurrent();
            if (forceRefresh && options.isGuest()) options.clear();
            try {
                const filters = await options.fetch({ ...counted, forceRefresh });
                if (!current()) return null;
                options.apply(filters);
                return filters;
            } catch {
                if (current() && options.isGuest()) options.clear();
                return null;
            }
        }
    };
}
