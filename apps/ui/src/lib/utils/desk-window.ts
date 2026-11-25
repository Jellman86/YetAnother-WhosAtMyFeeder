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

/** Midnight passed on this side since the day being read was settled: the new day is read from the start. */
export class DayTurnedError extends Error {
    constructor() {
        super('Today became another day while the Dashboard was reading it.');
        this.name = 'DayTurnedError';
    }
}

/** Every attempt was answered for another day, so nothing from it may be shown under Today. */
export class StraddledReadError extends Error {
    constructor() {
        super('The server answered for another day than the one Today was read for.');
        this.name = 'StraddledReadError';
    }
}

/** A read and its retries: the first attempt and two more, as midnight takes a moment to settle. */
const STRADDLE_RETRIES = 2;

function nextLocalMidnight(start: Date): number {
    const next = new Date(start);
    next.setDate(next.getDate() + 1);
    next.setHours(0, 0, 0, 0);
    return next.getTime();
}

/** The server counted from inside Today's day: from its midnight, or later for a guest, never the next day. */
function countedWithinDay(window: DeskWindow, counted: string): boolean {
    const start = Date.parse(counted);
    return Number.isFinite(start) && start >= window.start.getTime() && start < nextLocalMidnight(window.start);
}

/**
 * One read of Today that never mixes two days. The window is settled from `clock` for `day`, the
 * local midnight the page is reading; once midnight has passed here the read stops with
 * `DayTurnedError`, so the page reads the new day from the start. Each server answer names where it
 * counted from (`countedFrom`; a reading that was not taken is null), and an answer for another day,
 * a server already past midnight, is asked again, at most twice, before `StraddledReadError`. The
 * last 24 hours name no day and are taken as they come.
 */
export async function readOneDay<T>(options: {
    kind: DeskWindowKind;
    day: number | null;
    clock: () => Date;
    read: (window: DeskWindow) => Promise<T>;
    countedFrom: (value: T) => readonly (string | null | undefined)[];
}): Promise<{ value: T; window: DeskWindow }> {
    for (let attempt = 0; attempt <= STRADDLE_RETRIES; attempt += 1) {
        const window = deskWindow(options.kind, options.clock());
        if (window.kind === 'rolling') return { value: await options.read(window), window };
        if (options.day !== null && window.start.getTime() !== options.day) throw new DayTurnedError();
        const value = await options.read(window);
        const counted = options.countedFrom(value).filter((start): start is string => start !== null && start !== undefined);
        if (counted.every((start) => countedWithinDay(window, start))) return { value, window };
    }
    throw new StraddledReadError();
}
