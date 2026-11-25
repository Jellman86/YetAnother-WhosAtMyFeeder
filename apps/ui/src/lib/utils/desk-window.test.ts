import { describe, expect, it } from 'vitest';

import {
    DESK_WINDOW_STORAGE_KEY,
    deskWindow,
    deskWindowStart,
    readDeskWindowChoice,
    saveDeskWindowChoice,
    sharedHistoryStart
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
