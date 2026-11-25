import { describe, expect, it, vi } from 'vitest';

import {
    DayTurnedError,
    DESK_WINDOW_STORAGE_KEY,
    StraddledReadError,
    deskWindow,
    deskWindowStart,
    narrowedToSharedDay,
    readDeskWindowChoice,
    readOneDay,
    saveDeskWindowChoice,
    sharedHistoryStart,
    withinCounted
} from './desk-window';

function memoryStorage(initial: Record<string, string> = {}): Storage {
    const values = new Map(Object.entries(initial));
    return {
        get length() {
            return values.size;
        },
        clear: () => values.clear(),
        getItem: (key) => values.get(key) ?? null,
        key: (index) => [...values.keys()][index] ?? null,
        removeItem: (key) => void values.delete(key),
        setItem: (key, value) => void values.set(key, value)
    };
}

describe('the desk window', () => {
    it('reads the last 24 hours as the 24 hours before now', () => {
        const now = new Date('2026-11-25T06:30:00Z');
        const window = deskWindow('rolling', now);
        expect(window.kind).toBe('rolling');
        expect(window.end.toISOString()).toBe('2026-11-25T06:30:00.000Z');
        expect(window.start.toISOString()).toBe('2026-11-24T06:30:00.000Z');
    });

    it('reads Today from the viewer\'s local midnight to now', () => {
        const now = new Date(2026, 10, 25, 6, 30);
        const window = deskWindow('today', now);
        expect(window.kind).toBe('today');
        expect(window.start.getTime()).toBe(new Date(2026, 10, 25, 0, 0, 0, 0).getTime());
        expect(window.end.getTime()).toBe(now.getTime());
    });

    it('does not change the instant it was given', () => {
        const now = new Date(2026, 10, 25, 6, 30);
        deskWindow('today', now);
        expect(now.getHours()).toBe(6);
    });

    it('starts each window where the live captures it keeps begin', () => {
        const now = new Date(2026, 10, 25, 6, 30);
        expect(deskWindowStart('today', now)).toBe(new Date(2026, 10, 25).getTime());
        expect(deskWindowStart('rolling', now)).toBe(now.getTime() - 24 * 60 * 60 * 1000);
    });
});

describe('the remembered window', () => {
    it('is the last 24 hours until this device chooses Today, so an early morning is never empty', () => {
        expect(readDeskWindowChoice(() => memoryStorage())).toBe('rolling');
        expect(readDeskWindowChoice(() => memoryStorage({ [DESK_WINDOW_STORAGE_KEY]: 'today' }))).toBe('today');
        expect(readDeskWindowChoice(() => memoryStorage({ [DESK_WINDOW_STORAGE_KEY]: 'rolling' }))).toBe('rolling');
    });

    it('ignores a value it did not write', () => {
        for (const stored of ['week', 'TODAY', '', '24h']) {
            expect(readDeskWindowChoice(() => memoryStorage({ [DESK_WINDOW_STORAGE_KEY]: stored }))).toBe('rolling');
        }
    });

    it('falls back to the last 24 hours when storage cannot be read', () => {
        expect(readDeskWindowChoice(() => { throw new DOMException('blocked', 'SecurityError'); })).toBe('rolling');
        const failing = memoryStorage();
        failing.getItem = () => { throw new Error('denied'); };
        expect(readDeskWindowChoice(() => failing)).toBe('rolling');
    });

    it('is saved per device and a failed save is not an error', () => {
        const storage = memoryStorage();
        saveDeskWindowChoice(() => storage, 'today');
        expect(storage.getItem(DESK_WINDOW_STORAGE_KEY)).toBe('today');
        const failing = memoryStorage();
        failing.setItem = () => { throw new Error('quota'); };
        expect(() => saveDeskWindowChoice(() => failing, 'rolling')).not.toThrow();
        expect(() => saveDeskWindowChoice(() => { throw new Error('blocked'); }, 'today')).not.toThrow();
    });
});

describe('a guest\'s shared history', () => {
    it('is named only when it starts after the Today that was asked for', () => {
        const window = deskWindow('today', new Date('2026-11-25T09:30:00+09:00'));
        const later = new Date(window.start.getTime() + 9 * 60 * 60 * 1000).toISOString();
        expect(sharedHistoryStart(window, later)).toBe(later);
        expect(sharedHistoryStart(window, window.start.toISOString())).toBeNull();
    });

    it('is not named for the last 24 hours, whose start is not a midnight', () => {
        const window = deskWindow('rolling', new Date('2026-11-25T09:30:00Z'));
        expect(sharedHistoryStart(window, '2026-11-25T00:00:00Z')).toBeNull();
    });

    it('is not named without a reading of where the count started', () => {
        const window = deskWindow('today', new Date('2026-11-25T09:30:00Z'));
        expect(sharedHistoryStart(window, null)).toBeNull();
        expect(sharedHistoryStart(window, undefined)).toBeNull();
        expect(sharedHistoryStart(window, 'not a time')).toBeNull();
    });
});

describe('reading one day', () => {
    const beforeMidnight = new Date(2026, 10, 25, 23, 59, 59, 500);
    const afterMidnight = new Date(2026, 10, 26, 0, 0, 1);
    const day25 = new Date(2026, 10, 25).getTime();
    const day26 = new Date(2026, 10, 26).getTime();

    function clockAt(...instants: Date[]): () => Date {
        let index = 0;
        return () => instants[Math.min(index++, instants.length - 1)];
    }

    it('publishes an answer counted from the day it asked about', async () => {
        const result = await readOneDay({
            kind: 'today',
            day: day25,
            clock: clockAt(beforeMidnight),
            read: async (window) => ({ window_start: window.start.toISOString() }),
            countedFrom: (value) => [value.window_start]
        });
        expect(result.window.start.getTime()).toBe(day25);
    });

    it('accepts a guest answer that starts later the same day', async () => {
        const result = await readOneDay({
            kind: 'today',
            day: day25,
            clock: clockAt(beforeMidnight),
            read: async () => ({ window_start: new Date(2026, 10, 25, 9).toISOString() }),
            countedFrom: (value) => [value.window_start]
        });
        expect(result.value.window_start).toBe(new Date(2026, 10, 25, 9).toISOString());
    });

    it('asks again when the server answered for the next day, and never publishes mixed days', async () => {
        const read = vi.fn(async () => ({ window_start: new Date(day26).toISOString() }));
        await expect(readOneDay({
            kind: 'today',
            day: day25,
            clock: clockAt(beforeMidnight),
            read,
            countedFrom: (value) => [value.window_start]
        })).rejects.toBeInstanceOf(StraddledReadError);
        // The first read and two retries.
        expect(read).toHaveBeenCalledTimes(3);
    });

    it('stops as soon as midnight has passed on this side, so the new day is read from the start', async () => {
        const read = vi.fn(async () => ({ window_start: new Date(day25).toISOString() }));
        await expect(readOneDay({
            kind: 'today',
            day: day25,
            clock: clockAt(afterMidnight),
            read,
            countedFrom: (value) => [value.window_start]
        })).rejects.toBeInstanceOf(DayTurnedError);
        expect(read).not.toHaveBeenCalled();
    });

    it('never publishes an old-day answer that settles just after midnight', async () => {
        // Asked at 23:59:59.5, answered at 00:00:00.200, before the page's own midnight timer.
        const read = vi.fn(async () => ({ window_start: new Date(day25).toISOString() }));
        await expect(readOneDay({
            kind: 'today',
            day: day25,
            clock: clockAt(beforeMidnight, new Date(2026, 10, 26, 0, 0, 0, 200)),
            read,
            countedFrom: (value) => [value.window_start]
        })).rejects.toBeInstanceOf(DayTurnedError);
        expect(read).toHaveBeenCalledTimes(1);
    });

    it('asks again when a read reports its own answers do not agree', async () => {
        let attempt = 0;
        const result = await readOneDay({
            kind: 'today',
            day: day25,
            clock: clockAt(beforeMidnight),
            read: async () => ({ window_start: new Date(day25).toISOString(), agrees: ++attempt > 1 }),
            countedFrom: (value) => [value.window_start],
            consistent: (value) => value.agrees
        });
        expect(attempt).toBe(2);
        expect(result.value.agrees).toBe(true);
    });

    it('checks every answer a read collects, and skips one that was not read', async () => {
        let attempt = 0;
        const result = await readOneDay({
            kind: 'today',
            day: day25,
            clock: clockAt(beforeMidnight),
            read: async () => {
                attempt += 1;
                return { seen: new Date(day25).toISOString(), heard: attempt === 1 ? new Date(day26).toISOString() : null };
            },
            countedFrom: (value) => [value.seen, value.heard]
        });
        expect(attempt).toBe(2);
        expect(result.value.heard).toBeNull();
    });

    it('refuses an answer whose start cannot be read', async () => {
        await expect(readOneDay({
            kind: 'today',
            day: day25,
            clock: clockAt(beforeMidnight),
            read: async () => ({ window_start: 'not a time' }),
            countedFrom: (value) => [value.window_start]
        })).rejects.toBeInstanceOf(StraddledReadError);
    });

    it('takes the last 24 hours as they come, since they name no day', async () => {
        const read = vi.fn(async () => ({ window_start: 'anything' }));
        const result = await readOneDay({
            kind: 'rolling',
            day: null,
            clock: clockAt(afterMidnight),
            read,
            countedFrom: (value) => [value.window_start]
        });
        expect(read).toHaveBeenCalledTimes(1);
        expect(result.window.kind).toBe('rolling');
    });
});

describe('the window a reading counted', () => {
    it('holds an instant from its start up to, not including, its end', () => {
        const start = '2026-11-26T00:00:00Z';
        const end = '2026-11-26T09:00:00Z';
        expect(withinCounted('2026-11-26T00:00:00Z', start, end)).toBe(true);
        expect(withinCounted('2026-11-25T23:50:00Z', start, end)).toBe(false);
        expect(withinCounted('2026-11-26T09:00:00Z', start, end)).toBe(false);
        expect(withinCounted('2026-11-26T08:59:59Z', start, end)).toBe(true);
    });

    it('excludes nothing by a bound the reading did not report, and refuses an unreadable instant', () => {
        expect(withinCounted('2026-11-25T23:50:00Z', null, undefined)).toBe(true);
        expect(withinCounted('not a time', '2026-11-26T00:00:00Z', null)).toBe(false);
    });
});

describe('a guest\'s shared day', () => {
    // Tokyo's Today began at 15:00 UTC; the shared history starts at a UTC midnight after it.
    const window = { kind: 'today' as const, start: new Date('2026-11-25T15:00:00Z'), end: new Date('2026-11-26T00:30:00Z') };

    it('is the counted start when it is a UTC midnight later than the window asked for', () => {
        expect(narrowedToSharedDay(window, '2026-11-26T00:00:00Z')).toBe('2026-11-26T00:00:00.000Z');
    });

    it('is nothing when the count started where it was asked, or a moment later on the server clock', () => {
        expect(narrowedToSharedDay(window, '2026-11-25T15:00:00Z')).toBeNull();
        expect(narrowedToSharedDay(window, '2026-11-25T15:00:00.120Z')).toBeNull();
        expect(narrowedToSharedDay(window, null)).toBeNull();
    });
});
