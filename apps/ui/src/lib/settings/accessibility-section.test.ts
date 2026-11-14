import { describe, expect, it } from 'vitest';
import type { Settings } from '../api/settings';
import { accessibilitySection } from './accessibility-section';
import { sectionChangedFields } from './section-adapter';

function saved(fields: Partial<Settings>): Settings {
    return fields as Settings;
}

describe('Accessibility section draft', () => {
    it('loads every choice off except live announcements when a server leaves them out', () => {
        expect(accessibilitySection.decode(saved({}))).toEqual({
            highContrast: false,
            dyslexiaFont: false,
            liveAnnouncements: true,
            reducedMotion: false
        });
    });

    it('round-trips the saved choices into the save', () => {
        const stored = saved({
            accessibility_high_contrast: true,
            accessibility_dyslexia_font: true,
            accessibility_live_announcements: false,
            accessibility_reduced_motion: true
        });
        expect(accessibilitySection.encodePatch(accessibilitySection.decode(stored))).toEqual({
            accessibility_high_contrast: true,
            accessibility_dyslexia_font: true,
            accessibility_live_announcements: false,
            accessibility_reduced_motion: true
        });
    });

    it('is unsaved only while a toggle differs from the saved value', () => {
        const stored = saved({ accessibility_reduced_motion: true });
        const draft = accessibilitySection.decode(stored);
        expect(sectionChangedFields(accessibilitySection, draft, stored)).toEqual([]);
        expect(sectionChangedFields(accessibilitySection, { ...draft, liveAnnouncements: false }, stored)).not.toEqual([]);
        expect(sectionChangedFields(accessibilitySection, { ...draft, reducedMotion: false }, stored)).not.toEqual([]);
    });
});
