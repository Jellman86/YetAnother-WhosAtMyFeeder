/**
 * The window the Dashboard describes. Every figure, list and link on the desk reads the one window
 * a load settles, so the day bar, the log, Needs your call and the rail never count different days.
 */
const DESK_WINDOWS = ['today', 'rolling'] as const;

/** `today`: from the viewer's local midnight to now. `rolling`: the last 24 hours. */
export type DeskWindowKind = (typeof DESK_WINDOWS)[number];

export interface DeskWindow {
    kind: DeskWindowKind;
    start: Date;
    end: Date;
}

/** Early in the morning Today holds almost nothing, so a device starts on the last 24 hours. */
const DEFAULT_DESK_WINDOW: DeskWindowKind = 'rolling';
export const DESK_WINDOW_STORAGE_KEY = 'yawamf.dashboard.window';
const ROLLING_DAY_MS = 24 * 60 * 60 * 1000;

function isDeskWindowKind(value: unknown): value is DeskWindowKind {
    return typeof value === 'string' && (DESK_WINDOWS as readonly string[]).includes(value);
}

/** The first instant a window holds, in epoch milliseconds. */
export function deskWindowStart(kind: DeskWindowKind, now: Date): number {
    if (kind === 'rolling') return now.getTime() - ROLLING_DAY_MS;
    const midnight = new Date(now);
    midnight.setHours(0, 0, 0, 0);
    return midnight.getTime();
}

/** The exact instants one load of the Dashboard reads, settled once and given to every read. */
export function deskWindow(kind: DeskWindowKind, now: Date): DeskWindow {
    return { kind, start: new Date(deskWindowStart(kind, now)), end: new Date(now.getTime()) };
}

/** This device's choice. Storage can be blocked or cleared, and then the default holds. */
export function readDeskWindowChoice(storage: () => Pick<Storage, 'getItem'>): DeskWindowKind {
    try {
        const stored = storage().getItem(DESK_WINDOW_STORAGE_KEY);
        return isDeskWindowKind(stored) ? stored : DEFAULT_DESK_WINDOW;
    } catch {
        return DEFAULT_DESK_WINDOW;
    }
}

export function saveDeskWindowChoice(storage: () => Pick<Storage, 'setItem'>, kind: DeskWindowKind): void {
    try {
        storage().setItem(DESK_WINDOW_STORAGE_KEY, kind);
    } catch {
        // Remembering the choice is a convenience; the page still shows the window chosen.
    }
}

/**
 * Where a guest's Today really starts, when the owner's shared history begins after the viewer's
 * midnight: the server counts from the later of the two and says so in `window_start`.
 */
export function sharedHistoryStart(window: DeskWindow, counted: string | null | undefined): string | null {
    if (window.kind !== 'today' || !counted) return null;
    return Date.parse(counted) > window.start.getTime() ? counted : null;
}
