/**
 * Which page an in-app address opens, for its heading and the browser tab title.
 * Prefixes match the way App.svelte chooses the page to render, so an address
 * this returns null for is one that renders the not-found state.
 */
export type RouteId =
    | 'dashboard'
    | 'explorer'
    | 'add_observation'
    | 'leaderboard'
    | 'audio_history'
    | 'notifications'
    | 'settings'
    | 'model_evaluation'
    | 'about';

const ROUTE_PREFIXES: ReadonlyArray<[prefix: string, id: RouteId]> = [
    ['/events', 'explorer'],
    ['/observations/new', 'add_observation'],
    ['/species', 'leaderboard'],
    ['/audio', 'audio_history'],
    ['/settings', 'settings'],
    ['/notifications', 'notifications'],
    ['/diagnostics/model-eval', 'model_evaluation'],
    ['/about', 'about']
];

const PRODUCT_NAME = 'YA-WAMF';

export function routeIdFor(path: string): RouteId | null {
    if (path === '/') return 'dashboard';
    return ROUTE_PREFIXES.find(([prefix]) => path.startsWith(prefix))?.[1] ?? null;
}

export function documentTitle(pageTitle: string): string {
    const page = pageTitle.trim();
    return page ? `${page} · ${PRODUCT_NAME}` : PRODUCT_NAME;
}
