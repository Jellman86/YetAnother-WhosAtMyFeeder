import type { EventFilters } from '../api';

/** Latest projection wins; a failed guest invalidation must not retain old facets. */
export function createEventMetadataRefresh(options: {
    fetch: (options: { forceRefresh: boolean }) => Promise<EventFilters>;
    apply: (filters: EventFilters) => void;
    clear: () => void;
    isGuest: () => boolean;
}) {
    let generation = 0;
    return {
        async load(forceRefresh = false): Promise<EventFilters | null> {
            const requestGeneration = ++generation;
            if (forceRefresh && options.isGuest()) options.clear();
            try {
                const filters = await options.fetch({ forceRefresh });
                if (requestGeneration !== generation) return null;
                options.apply(filters);
                return filters;
            } catch {
                if (requestGeneration === generation && options.isGuest()) options.clear();
                return null;
            }
        }
    };
}
