/**
 * The defaults for everyone being edited in Settings, shown on this device before they are saved.
 *
 * The preview is read from the Settings draft itself, never written by a switch: the Settings page
 * connects its draft and the saved copy while it is open. So a Discard, a restored draft, closing
 * More options or a section change cannot leave the look out of step with what is pending, and
 * leaving Settings disconnects it, so an unsaved preview never sticks to the rest of the app.
 */
type PreviewedChoice = 'highContrast' | 'dyslexiaFont' | 'reducedMotion';

interface PreviewSource {
    draft: Record<PreviewedChoice, boolean>;
    /** The saved defaults, or null before they have been read: nothing is previewed against a guess. */
    saved: Record<PreviewedChoice, boolean> | null;
}

/** The draft's value where it differs from the saved one; null where nothing unsaved is pending. */
export function previewedValue(source: PreviewSource | null, key: PreviewedChoice): boolean | null {
    if (!source?.saved) return null;
    return source.draft[key] !== source.saved[key] ? source.draft[key] : null;
}

class AccessibilityPreview {
    #source = $state<(() => PreviewSource) | null>(null);

    /** Shows the draft's unsaved defaults while the returned function has not been called. */
    connect(source: () => PreviewSource): () => void {
        this.#source = source;
        return () => {
            if (this.#source === source) this.#source = null;
        };
    }

    #value(key: PreviewedChoice): boolean | null {
        return previewedValue(this.#source?.() ?? null, key);
    }

    get highContrast(): boolean | null {
        return this.#value('highContrast');
    }

    get dyslexiaFont(): boolean | null {
        return this.#value('dyslexiaFont');
    }

    get reducedMotion(): boolean | null {
        return this.#value('reducedMotion');
    }
}

export const accessibilityPreview = new AccessibilityPreview();
