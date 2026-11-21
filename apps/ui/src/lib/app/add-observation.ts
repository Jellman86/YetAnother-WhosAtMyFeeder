/** The Add observation page's address. Links and bookmarks to it predate the header entry. */
export const ADD_OBSERVATION_PATH = '/observations/new';

export type AddObservationEntry = {
    /** Adding an observation writes to the history, so only the owner is offered it. */
    shown: boolean;
    /** The reader is on the page the entry opens. */
    current: boolean;
};

/**
 * Whether the header offers Add observation, and whether it marks the page as the current one. The
 * rule is the sidebar's own for owner places: owner access, never a guest or a signed-out reader.
 */
export function addObservationEntry(currentRoute: string, ownerAccess: boolean): AddObservationEntry {
    if (!ownerAccess) return { shown: false, current: false };
    return { shown: true, current: currentRoute.startsWith(ADD_OBSERVATION_PATH) };
}

type ClickModifiers = Pick<MouseEvent, 'button' | 'metaKey' | 'ctrlKey' | 'shiftKey' | 'altKey'>;

/** A plain primary click the app may handle in place; any other keeps the browser's meaning, such as a new tab. */
export function isPlainClick(event: ClickModifiers): boolean {
    return event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey;
}
