/** The Add observation page's address. Links and bookmarks to it predate the header entry. */
export const ADD_OBSERVATION_PATH = '/observations/new';

/**
 * A picture with a plus: add a photo (or clip) of your own. Unlabelled in the header, it has to say
 * "add" on its own; an upload arrow reads as share or export there, and the camera beside it is a
 * video camera, so the two glyphs stay apart.
 */
export const ADD_OBSERVATION_ICON =
    'M20 12v6a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h6M18 3v6M15 6h6M20 15l-3.3-3.3a1 1 0 0 0-1.4 0L7 20M9 10.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3z';

export type AddObservationEntry = {
    /** In the header's owner controls, beside Refresh. */
    inHeader: boolean;
    /** A place in the phone menu instead. */
    inMenu: boolean;
    /** The reader is on the page the entry opens. */
    current: boolean;
};

/**
 * Where the owner's way to Add observation is drawn. Adding writes to the history, so it is the
 * owner's only, by the sidebar's own rule (owner access). On a phone the header has no room for a
 * fifth 44 px control: it would squeeze the page title until a word such as "Leaderboard" breaks.
 * There it is a place in the menu; from the docked sidebar's width up, it is in the header.
 */
export function addObservationEntry(currentRoute: string, ownerAccess: boolean, phone: boolean): AddObservationEntry {
    if (!ownerAccess) return { inHeader: false, inMenu: false, current: false };
    return { inHeader: !phone, inMenu: phone, current: currentRoute.startsWith(ADD_OBSERVATION_PATH) };
}

type ClickModifiers = Pick<MouseEvent, 'button' | 'metaKey' | 'ctrlKey' | 'shiftKey' | 'altKey'>;

/** A plain primary click the app may handle in place; any other keeps the browser's meaning, such as a new tab. */
export function isPlainClick(event: ClickModifiers): boolean {
    return event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey;
}
