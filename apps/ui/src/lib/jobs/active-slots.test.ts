import { describe, expect, it } from 'vitest';

import { buildStableActiveJobSlots, sameActiveSlotAssignments } from './active-slots';

describe('buildStableActiveJobSlots', () => {
    it('keeps existing jobs in their assigned slots even when their order changes', () => {
        const first = buildStableActiveJobSlots(
            [{ id: 'job-a' }, { id: 'job-b' }],
            {},
            3
        );

        expect(first.slots.map((slot) => slot.job?.id ?? null)).toEqual(['job-a', 'job-b', null]);

        const second = buildStableActiveJobSlots(
            [{ id: 'job-b' }, { id: 'job-a' }],
            first.assignments,
            3
        );

        expect(second.slots.map((slot) => slot.job?.id ?? null)).toEqual(['job-a', 'job-b', null]);
    });

    it('reuses the lowest free slot when a job finishes and a new one arrives', () => {
        const initial = buildStableActiveJobSlots(
            [{ id: 'job-a' }, { id: 'job-b' }],
            {},
            2
        );

        const afterCompletion = buildStableActiveJobSlots(
            [{ id: 'job-b' }],
            initial.assignments,
            2
        );

        expect(afterCompletion.slots.map((slot) => slot.job?.id ?? null)).toEqual([null, 'job-b']);

        const withReplacement = buildStableActiveJobSlots(
            [{ id: 'job-b' }, { id: 'job-c' }],
            afterCompletion.assignments,
            2
        );

        expect(withReplacement.slots.map((slot) => slot.job?.id ?? null)).toEqual(['job-c', 'job-b']);
    });
});

describe('sameActiveSlotAssignments', () => {
    it('compares slot maps structurally', () => {
        expect(sameActiveSlotAssignments({ a: 0, b: 1 }, { a: 0, b: 1 })).toBe(true);
        expect(sameActiveSlotAssignments({ a: 0 }, { a: 1 })).toBe(false);
        expect(sameActiveSlotAssignments({ a: 0 }, { a: 0, b: 1 })).toBe(false);
    });
});
