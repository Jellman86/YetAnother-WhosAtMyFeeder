import { describe, expect, it } from 'vitest';

import { locationTogglePresentation } from './location-toggle';

describe('locationTogglePresentation', () => {
    it('aligns the thumb with Auto when auto-detect is enabled', () => {
        const presentation = locationTogglePresentation(true);

        expect(presentation.thumbTranslateClass).toBe('translate-x-0');
        expect(presentation.autoActive).toBe(true);
        expect(presentation.manualActive).toBe(false);
    });

    it('aligns the thumb with Manual when auto-detect is disabled', () => {
        const presentation = locationTogglePresentation(false);

        expect(presentation.thumbTranslateClass).toBe('translate-x-5');
        expect(presentation.autoActive).toBe(false);
        expect(presentation.manualActive).toBe(true);
    });
});
