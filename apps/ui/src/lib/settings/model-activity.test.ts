import { describe, expect, it } from 'vitest';
import { HINT_GRACE_MS, reconcileActivity } from './model-activity';

const NOW = 1_000_000;

describe('work in progress, with the server as the authority', () => {
    it('is what the server reports, whoever started it', () => {
        const { phases } = reconcileActivity({ small_birds: 'downloading' }, {}, NOW);
        expect(phases).toEqual({ small_birds: 'downloading' });
    });

    it('shows work this page just started until the server has had time to report it', () => {
        const hints = { small_birds: { phase: 'downloading', at: NOW - 500 } } as const;
        expect(reconcileActivity({}, hints, NOW).phases).toEqual({ small_birds: 'downloading' });
    });

    it('drops a hint the server never confirmed: the work did not start, or is over', () => {
        const hints = { small_birds: { phase: 'downloading', at: NOW - HINT_GRACE_MS - 1 } } as const;
        const result = reconcileActivity({}, hints, NOW);
        expect(result.phases).toEqual({});
        expect(result.hints).toEqual({});
    });

    it('hands a model over to the server once the server reports it, so its end is the server\'s to say', () => {
        const hints = { small_birds: { phase: 'validating', at: NOW - 100 } } as const;
        const confirmed = reconcileActivity({ small_birds: 'validating' }, hints, NOW);
        expect(confirmed.hints).toEqual({});
        // The check ends: the page that started it no longer holds a memory that it is running.
        expect(reconcileActivity({}, confirmed.hints, NOW + 50).phases).toEqual({});
    });

    it('says what the server says when the two disagree', () => {
        const hints = { small_birds: { phase: 'validating', at: NOW } } as const;
        expect(reconcileActivity({ small_birds: 'downloading' }, hints, NOW).phases).toEqual({ small_birds: 'downloading' });
    });

    it('keeps models apart', () => {
        const hints = { rope: { phase: 'downloading', at: NOW } } as const;
        expect(reconcileActivity({ small_birds: 'validating' }, hints, NOW).phases).toEqual({ small_birds: 'validating', rope: 'downloading' });
    });
});
