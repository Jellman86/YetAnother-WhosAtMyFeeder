import { beforeEach, describe, expect, it, vi } from 'vitest';

const settingsState: { settings: Record<string, unknown> | null } = { settings: null };
const authState: { dateFormat: string; timeFormat: string } = { dateFormat: 'locale', timeFormat: 'locale' };

vi.mock('../stores/settings.svelte', () => ({ settingsStore: settingsState }));
vi.mock('../stores/auth.svelte', () => ({ authStore: authState }));

const { formatCalendarDay, formatDay, formatHour, formatShortDay, formatTime, formatDateTime, normalizeDateFormat, normalizeTimeFormat } = await import('./datetime');

// 13:45 local, so the two clocks are unambiguous.
const AFTERNOON = new Date(2026, 7, 22, 13, 45, 0);

describe('time format follows the owner setting, not the browser locale', () => {
    beforeEach(() => {
        settingsState.settings = null;
        authState.dateFormat = 'locale';
        authState.timeFormat = 'locale';
    });

    it('renders a 24 hour clock when the owner asks for one', () => {
        settingsState.settings = { time_format: '24h' };
        expect(formatTime(AFTERNOON)).toBe('13:45');
    });

    it('renders a 12 hour clock when the owner asks for one', () => {
        settingsState.settings = { time_format: '12h' };
        expect(formatTime(AFTERNOON)).toMatch(/^01:45\s?(PM|pm)$/);
    });

    it('pairs a pinned date format with the pinned clock in one string', () => {
        settingsState.settings = { date_format: 'dmy', time_format: '24h' };
        expect(formatDateTime(AFTERNOON)).toBe('22/08/2026 13:45');
    });

    it('states a time to the minute, the same as every other time in the app', () => {
        // `formatTime` asks for hour and minute; `formatDateTime` asked for
        // neither and got the locale default, which carries seconds. So a
        // detection read 07:38 in one place and 07:38:00 in another, and an
        // eBird sighting claimed a precision the observation never had.
        settingsState.settings = { date_format: 'dmy', time_format: '24h' };
        expect(formatDateTime(AFTERNOON)).not.toMatch(/:\d{2}:\d{2}/);
    });

    it('drops the seconds under the browser locale too', () => {
        // The locale branch had the same problem by a different route.
        expect(formatDateTime(AFTERNOON)).not.toMatch(/:\d{2}:\d{2}/);
    });

    it('falls back to the auth payload before the settings store has loaded', () => {
        authState.timeFormat = '24h';
        expect(formatTime(AFTERNOON)).toBe('13:45');
    });

    it('defers to the browser locale when nothing is pinned', () => {
        const expected = AFTERNOON.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        expect(formatTime(AFTERNOON)).toBe(expected);
    });

    it('ignores an unrecognised value rather than guessing', () => {
        settingsState.settings = { time_format: 'nonsense' };
        const expected = AFTERNOON.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        expect(formatTime(AFTERNOON)).toBe(expected);
    });
});


describe('display preference normalization', () => {
    it.each(['locale', 'mdy', 'dmy', 'ymd'])('preserves the accepted date choice %s', value => {
        expect(normalizeDateFormat(value)).toBe(value);
    });
    it.each(['locale', '12h', '24h'])('preserves the accepted clock choice %s independently of the date', value => {
        expect(normalizeTimeFormat(value)).toBe(value);
        expect(normalizeDateFormat('locale')).toBe('locale');
    });
    it.each([undefined, null, '', 'unknown', 24])('falls back to the browser language for invalid preferences %s', value => {
        expect(normalizeDateFormat(value)).toBe('locale');
        expect(normalizeTimeFormat(value)).toBe('locale');
    });
});

describe('a calendar day, as a date filter names it', () => {
    const NOW = new Date(2026, 9, 31, 9, 0, 0);

    beforeEach(() => {
        settingsState.settings = null;
        authState.dateFormat = 'locale';
    });

    it('reads a day and short month in the locale, without the year when it is this year', () => {
        const expected = new Date(2026, 9, 1).toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
        expect(formatCalendarDay('2026-10-01', NOW)).toBe(expected);
    });

    it('adds the year for a day in another year', () => {
        const expected = new Date(2025, 9, 1).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
        expect(formatCalendarDay('2025-10-01', NOW)).toBe(expected);
    });

    it('keeps the day the input names in every time zone, rather than reading it as UTC midnight', () => {
        settingsState.settings = { date_format: 'ymd' };
        expect(formatCalendarDay('2026-10-01', NOW)).toBe('2026-10-01');
    });

    it('follows a pinned date format', () => {
        settingsState.settings = { date_format: 'dmy' };
        expect(formatCalendarDay('2026-10-01', NOW)).toBe('01/10/2026');
    });

    it('returns an unreadable value as it is', () => {
        expect(formatCalendarDay('not-a-day', NOW)).toBe('not-a-day');
    });
});

describe('a day in a record names its year, so a span across years reads plainly', () => {
    beforeEach(() => {
        settingsState.settings = null;
        authState.dateFormat = 'locale';
    });

    it('reads as day, short month and year under the locale format', () => {
        const day = new Date(2025, 2, 14, 7, 12);
        expect(formatDay(day)).toBe(day.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }));
    });

    it('follows a pinned date format, and leaves an unreadable value empty', () => {
        settingsState.settings = { date_format: 'dmy' };
        expect(formatDay(new Date(2026, 10, 2, 8, 41))).toBe('02/11/2026');
        expect(formatDay(null)).toBe('');
    });
});

describe('a whole hour, on a chart axis or in a sentence, follows the same clock as every other time', () => {
    beforeEach(() => {
        settingsState.settings = null;
        authState.timeFormat = 'locale';
    });

    it('reads on the 24 hour clock when the owner asks for one', () => {
        settingsState.settings = { time_format: '24h' };
        expect(formatHour(7)).toBe('07:00');
        expect(formatHour(17)).toBe('17:00');
        expect([0, 6, 12, 18, 23].map((hour) => formatHour(hour, 'axis'))).toEqual(['00', '06', '12', '18', '23']);
    });

    it('reads on the 12 hour clock when the owner asks for one, with no space an axis could break at', () => {
        settingsState.settings = { time_format: '12h' };
        expect(formatHour(17)).toMatch(/^0?5:00\s?(PM|pm)$/);
        expect(formatHour(0, 'axis')).toMatch(/^12\u00a0?(AM|am)$/);
        expect(formatHour(17, 'axis')).not.toMatch(/ /);
    });

    it('never prints an hour outside the day', () => {
        settingsState.settings = { time_format: '24h' };
        expect(formatHour(-3)).toBe('00:00');
        expect(formatHour(40)).toBe('23:00');
    });
});

describe('a short day, as a chart or a strip of days labels it', () => {
    const NOW = new Date(2026, 9, 31, 9, 0, 0);

    beforeEach(() => {
        settingsState.settings = null;
        authState.dateFormat = 'locale';
    });

    it('is a day and short month under the locale format', () => {
        const expected = new Date(2026, 9, 1).toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
        expect(formatShortDay(new Date(2026, 9, 1, 15, 30), NOW)).toBe(expected);
    });

    it('follows a pinned date format, and leaves an unreadable value empty', () => {
        settingsState.settings = { date_format: 'ymd' };
        expect(formatShortDay(new Date(2026, 9, 1, 15, 30), NOW)).toBe('2026-10-01');
        expect(formatShortDay('not a date', NOW)).toBe('');
    });
});
