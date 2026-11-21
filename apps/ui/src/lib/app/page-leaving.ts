/** How long a beforeunload counts as leaving. Settings may still keep the reader, and no event says so. */
const BEFOREUNLOAD_LEAVING_MS = 3000;

export interface PageLeaving {
    isLeaving(): boolean;
    dispose(): void;
}

/**
 * Whether the reader is going to another page. Safari ends the imports this page is still loading
 * as soon as a navigation starts, with the words a missing chunk gives, so deploy recovery asks this
 * before it reloads. beforeunload comes first where it fires; Safari on iPhone gives only pagehide.
 */
export function createPageLeaving(target: EventTarget, beforeUnloadMs = BEFOREUNLOAD_LEAVING_MS): PageLeaving {
    let leaving = false;
    let lapse: ReturnType<typeof setTimeout> | undefined;
    const settle = (): void => {
        if (lapse !== undefined) clearTimeout(lapse);
        lapse = undefined;
    };
    const onBeforeUnload = (): void => {
        settle();
        leaving = true;
        lapse = setTimeout(() => {
            leaving = false;
            lapse = undefined;
        }, beforeUnloadMs);
    };
    const onPageHide = (): void => {
        settle();
        leaving = true;
    };
    const onPageShow = (): void => {
        settle();
        leaving = false;
    };
    target.addEventListener('beforeunload', onBeforeUnload);
    target.addEventListener('pagehide', onPageHide);
    target.addEventListener('pageshow', onPageShow);
    return {
        isLeaving: () => leaving,
        dispose: () => {
            settle();
            target.removeEventListener('beforeunload', onBeforeUnload);
            target.removeEventListener('pagehide', onPageHide);
            target.removeEventListener('pageshow', onPageShow);
        }
    };
}
