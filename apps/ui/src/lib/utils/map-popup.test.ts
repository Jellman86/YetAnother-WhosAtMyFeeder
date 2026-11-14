import { describe, expect, it } from 'vitest';
import { markerName } from './map-popup';

/** A map pin is a button; a button with no name is announced as nothing but "button". */
describe('markerName', () => {
    it('uses the pin’s own title', () => {
        expect(markerName({ lat: 1, lng: 2, title: 'Rutland Water' }, 'Sighting location')).toBe('Rutland Water');
    });

    it('falls back to the first line of its popup', () => {
        expect(markerName({ lat: 1, lng: 2, popupLines: ['Seen 3 times', 'Yesterday'] }, 'Sighting location')).toBe('Seen 3 times');
    });

    it('never leaves a pin unnamed', () => {
        expect(markerName({ lat: 1, lng: 2 }, 'Sighting location')).toBe('Sighting location');
        expect(markerName({ lat: 1, lng: 2, title: '  ' }, 'Sighting location')).toBe('Sighting location');
    });
});
