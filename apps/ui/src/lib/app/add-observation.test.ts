import { describe, expect, it } from 'vitest';
import { ADD_OBSERVATION_PATH, addObservationEntry, isPlainClick } from './add-observation';

describe('addObservationEntry', () => {
    it('offers Add observation to the owner only', () => {
        expect(addObservationEntry('/events', true).shown).toBe(true);
        expect(addObservationEntry('/events', false).shown).toBe(false);
    });

    it('marks the entry current on the Add observation page, and only there', () => {
        expect(addObservationEntry(ADD_OBSERVATION_PATH, true).current).toBe(true);
        expect(addObservationEntry('/observations/new/', true).current).toBe(true);
        expect(addObservationEntry('/events', true).current).toBe(false);
        expect(addObservationEntry('/', true).current).toBe(false);
    });

    it('never marks a hidden entry current', () => {
        expect(addObservationEntry(ADD_OBSERVATION_PATH, false)).toEqual({ shown: false, current: false });
    });
});

describe('isPlainClick', () => {
    const click = { button: 0, metaKey: false, ctrlKey: false, shiftKey: false, altKey: false };

    it('handles a plain primary click in place', () => {
        expect(isPlainClick(click)).toBe(true);
    });

    it('leaves a modified or non-primary click to the browser, so the link can open in a new tab', () => {
        expect(isPlainClick({ ...click, button: 1 })).toBe(false);
        expect(isPlainClick({ ...click, metaKey: true })).toBe(false);
        expect(isPlainClick({ ...click, ctrlKey: true })).toBe(false);
        expect(isPlainClick({ ...click, shiftKey: true })).toBe(false);
        expect(isPlainClick({ ...click, altKey: true })).toBe(false);
    });
});
