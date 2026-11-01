import type { Settings } from '../api/settings';
import type { SettingsSectionAdapter } from './section-adapter';

/** The Accessibility choices saved for the whole installation, guests included. */
export interface AccessibilityDraft {
    highContrast: boolean;
    dyslexiaFont: boolean;
    liveAnnouncements: boolean;
    reducedMotion: boolean;
}

interface AccessibilityPatch {
    accessibility_high_contrast: boolean;
    accessibility_dyslexia_font: boolean;
    accessibility_live_announcements: boolean;
    accessibility_reduced_motion: boolean;
}

export const accessibilitySection: SettingsSectionAdapter<AccessibilityDraft, AccessibilityPatch> = {
    decode(saved: Settings): AccessibilityDraft {
        return {
            highContrast: saved.accessibility_high_contrast ?? false,
            dyslexiaFont: saved.accessibility_dyslexia_font ?? false,
            liveAnnouncements: saved.accessibility_live_announcements ?? true,
            reducedMotion: saved.accessibility_reduced_motion ?? false
        };
    },
    encodePatch(draft: AccessibilityDraft): AccessibilityPatch {
        return {
            accessibility_high_contrast: draft.highContrast,
            accessibility_dyslexia_font: draft.dyslexiaFont,
            accessibility_live_announcements: draft.liveAnnouncements,
            accessibility_reduced_motion: draft.reducedMotion
        };
    }
};
