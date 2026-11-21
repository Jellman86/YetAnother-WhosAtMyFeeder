import { describe, expect, it } from 'vitest';
import { ADD_OBSERVATION_PATH, addObservationEntry, isPlainClick } from './add-observation';

describe('addObservationEntry', () => {
    it('offers Add observation to the owner only, in the header on a wider screen', () => {
        expect(addObservationEntry('/events', true, false)).toEqual({ inHeader: true, inMenu: false, current: false });
        expect(addObservationEntry('/events', false, false)).toEqual({ inHeader: false, inMenu: false, current: false });
    });

    it('moves it into the phone menu where the header has no room for it', () => {
        expect(addObservationEntry('/events', true, true)).toEqual({ inHeader: false, inMenu: true, current: false });
        expect(addObservationEntry('/events', false, true)).toEqual({ inHeader: false, inMenu: false, current: false });
    });

    it('marks the entry current on the Add observation page, and only there', () => {
        expect(addObservationEntry(ADD_OBSERVATION_PATH, true, false).current).toBe(true);
        expect(addObservationEntry('/observations/new/', true, true).current).toBe(true);
        expect(addObservationEntry('/events', true, false).current).toBe(false);
        expect(addObservationEntry('/', true, false).current).toBe(false);
    });

    it('never marks a hidden entry current', () => {
        expect(addObservationEntry(ADD_OBSERVATION_PATH, false, false).current).toBe(false);
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
