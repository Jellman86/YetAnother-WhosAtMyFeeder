/**
 * The unsaved state of the Settings accessibility toggles.
 *
 * The editor publishes what the owner is trying out; App.svelte applies
 * preview ?? saved to the document root. Null means "no preview", so an
 * abandoned edit falls back to the saved value the moment the editor
 * unmounts - previously the editor toggled the classes itself with no
 * teardown, and an unsaved preview stuck to the whole app until a reload.
 */
class AccessibilityPreview {
    highContrast = $state<boolean | null>(null);
    dyslexiaFont = $state<boolean | null>(null);
    reducedMotion = $state<boolean | null>(null);

    clear(): void {
        this.highContrast = null;
        this.dyslexiaFont = null;
        this.reducedMotion = null;
    }
}

export const accessibilityPreview = new AccessibilityPreview();
