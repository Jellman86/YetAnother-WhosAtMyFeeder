import { describe, expect, it } from 'vitest';

import { getManualTagSearchOptions } from './manual-tag-search';

describe('getManualTagSearchOptions', () => {
    it('enables hydration for meaningful typed queries', () => {
        expect(getManualTagSearchOptions('finch')).toEqual({
            limit: 50,
            hydrateMissing: true
        });
    });

    it('keeps hydration off for short or blank queries', () => {
        expect(getManualTagSearchOptions('')).toEqual({
            limit: 50,
            hydrateMissing: false
        });
        expect(getManualTagSearchOptions('  ow ')).toEqual({
            limit: 50,
            hydrateMissing: false
        });
    });
});
