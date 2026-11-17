import { routeIdFor, type RouteId } from './route-title';

type PageLoaders = Partial<Record<RouteId, () => Promise<unknown>>>;
type MatchMedia = (query: string) => { matches: boolean };

/** The parts of the browser these rules read, passed in so they are tested without one. */
interface BrowserHints {
    connection?: { saveData?: boolean };
    matchMedia?: MatchMedia;
}

function currentBrowser(): BrowserHints {
    if (typeof window === 'undefined') return {};
    return {
        connection: (navigator as Navigator & { connection?: { saveData?: boolean } }).connection,
        matchMedia: (query) => window.matchMedia(query)
    };
}

/** True when the browser asks to spend less data: Save-Data, or `prefers-reduced-data: reduce`. */
export function prefersLessData(browser: BrowserHints = currentBrowser()): boolean {
    if (browser.connection?.saveData === true) return true;
    return browser.matchMedia?.('(prefers-reduced-data: reduce)').matches === true;
}

/**
 * Whether a pointer passing over a link means someone is about to choose it: a mouse or pen on a
 * device that can hover. A finger crossing a link while it scrolls the menu is not, so touch never
 * prefetches; keyboard focus prefetches on its own.
 */
export function pointerMayPrefetch(pointerType: string, matchMedia: MatchMedia = (query) => window.matchMedia(query)): boolean {
    return (pointerType === 'mouse' || pointerType === 'pen') && matchMedia('(hover: hover)').matches;
}

interface RoutePrefetchOptions {
    /** True when nothing should be loaded ahead of a click; the browser's own wish by default. */
    prefersLessData?: () => boolean;
}

/**
 * Starts loading a page's code when its link is hovered or focused, so the click that follows
 * shows the page without waiting for it. The loaders cache their import, so a page is fetched
 * once however often its link is pointed at. A failed prefetch is let go: opening the page loads
 * it again, and says so if it still fails.
 */
export function createRoutePrefetch(loaders: PageLoaders, options: RoutePrefetchOptions = {}): (path: string) => Promise<void> {
    const lessData = options.prefersLessData ?? (() => prefersLessData());
    return async (path) => {
        const route = routeIdFor(path);
        const load = route ? loaders[route] : undefined;
        if (!load || lessData()) return;
        try {
            await load();
        } catch {
            // Opening the page retries the load and reports a failure there.
        }
    };
}
