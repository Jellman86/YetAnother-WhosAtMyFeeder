import { describe, expect, it } from 'vitest';
import { measuredCount } from './measured-count';

describe('a count is only a count when the server reported one', () => {
    it('keeps a whole number, zero included', () => {
        expect(measuredCount(931)).toBe(931);
        expect(measuredCount(0)).toBe(0);
    });

    it.each([undefined, null, '931', Number.NaN, Number.POSITIVE_INFINITY, -1, 12.5, {}])(
        'reads %p as not measured, never as zero',
        (value) => {
            expect(measuredCount(value)).toBeNull();
        }
    );
});
