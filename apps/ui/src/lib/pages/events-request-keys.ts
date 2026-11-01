/**
 * Cancellation keys owned by the Explorer page. A keyed request aborts the earlier request
 * with the same key, so these are distinct from the dashboard store's keys: the page and the
 * shared store each cancel only their own reads, never each other's.
 */
export const EVENTS_PAGE_REQUEST_KEYS = {
    visits: 'events-page:visits',
    list: 'events-page:list',
    count: 'events-page:count',
    deepLink: 'events-page:deep-link'
} as const;
