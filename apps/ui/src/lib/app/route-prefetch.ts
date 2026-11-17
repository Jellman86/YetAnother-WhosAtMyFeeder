import { routeIdFor, type RouteId } from './route-title';

type PageLoaders = Partial<Record<RouteId, () => Promise<unknown>>>;

interface RoutePrefetchOptions {
    /** True when the browser asks to save data; nothing is then loaded ahead of a click. */
    saveData?: () => boolean;
}

function browserSavesData(): boolean {
    const connection = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection;
    return connection?.saveData === true;
}

/**
 * Starts loading a page's code when its link is hovered or focused, so the click that follows
 * shows the page without waiting for it. The loaders cache their import, so a page is fetched
 * once however often its link is pointed at. A failed prefetch is let go: opening the page loads
 * it again, and says so if it still fails.
 */
export function createRoutePrefetch(loaders: PageLoaders, options: RoutePrefetchOptions = {}): (path: string) => Promise<void> {
    const saveData = options.saveData ?? browserSavesData;
    return async (path) => {
        const route = routeIdFor(path);
        const load = route ? loaders[route] : undefined;
        if (!load || saveData()) return;
        try {
            await load();
        } catch {
            // Opening the page retries the load and reports a failure there.
        }
    };
}
