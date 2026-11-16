import { describe, expect, it } from 'vitest';
import { gigabytesToStoredMegabytes, parseStorageLimitGigabytes, storedMegabytesToGigabytes } from './storage-budget';

describe('the photo and video storage budget', () => {
    it('shows the saved limit in GB, the unit the rest of the tab uses', () => {
        expect(storedMegabytesToGigabytes(20480)).toBe(20);
        expect(storedMegabytesToGigabytes(1536)).toBe(1.5);
    });

    it('saves a limit typed in GB in the unit the server stores', () => {
        expect(gigabytesToStoredMegabytes(20)).toBe(20480);
        expect(gigabytesToStoredMegabytes(0.5)).toBe(512);
    });

    it('reads a typed limit only when it is a size it can keep', () => {
        expect(parseStorageLimitGigabytes('25')).toBe(25);
        expect(parseStorageLimitGigabytes(' 0.5 ')).toBe(0.5);
        expect(parseStorageLimitGigabytes('1024')).toBe(1024);
    });

    it('rejects an emptied, zero, negative, too large or unreadable limit instead of substituting a small one', () => {
        for (const typed of ['', '   ', '0', '0.4', '-3', '1025', 'abc', 'NaN', 'Infinity']) {
            expect(parseStorageLimitGigabytes(typed), typed).toBeNull();
        }
    });
});
