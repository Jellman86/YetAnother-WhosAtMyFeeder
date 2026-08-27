import { beforeEach, describe, expect, it, vi } from 'vitest';

const settingsState: { settings: Record<string, unknown> | null } = { settings: null };
const authState: { dateFormat: string; timeFormat: string } = { dateFormat: 'locale', timeFormat: 'locale' };

vi.mock('../stores/settings.svelte', () => ({ settingsStore: settingsState }));
vi.mock('../stores/auth.svelte', () => ({ authStore: authState }));

const { formatTime, formatDateTime } = await import('./datetime');

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
