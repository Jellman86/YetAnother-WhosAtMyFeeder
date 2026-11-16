import { describe, expect, it } from 'vitest';
import { gigabytesToStoredMegabytes, storedMegabytesToGigabytes } from './storage-budget';

describe('the photo and video storage budget', () => {
    it('shows the saved limit in GB, the unit the rest of the tab uses', () => {
        expect(storedMegabytesToGigabytes(20480)).toBe(20);
        expect(storedMegabytesToGigabytes(1536)).toBe(1.5);
    });

    it('saves a limit typed in GB in the unit the server stores', () => {
        expect(gigabytesToStoredMegabytes(20)).toBe(20480);
        expect(gigabytesToStoredMegabytes(0.5)).toBe(512);
    });

    it('never saves a limit below half a GB, so a stray small number cannot empty the media library', () => {
        expect(gigabytesToStoredMegabytes(0)).toBe(512);
        expect(gigabytesToStoredMegabytes(Number.NaN)).toBe(512);
    });
});
