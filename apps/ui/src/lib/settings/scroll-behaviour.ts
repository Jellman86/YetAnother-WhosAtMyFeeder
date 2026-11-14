/** What asks for less motion: the system setting, or the app's own Accessibility switch. */
export interface MotionPreference {
    systemReducesMotion: boolean;
    appReducesMotion: boolean;
}

/** A jump within Settings glides, unless either the system or the app asks for less motion. */
export function scrollBehaviourFor(preference: MotionPreference): ScrollBehavior {
    return preference.systemReducesMotion || preference.appReducesMotion ? 'auto' : 'smooth';
}

/** The scroll behaviour for a jump within Settings right now. */
export function settingsScrollBehaviour(): ScrollBehavior {
    return scrollBehaviourFor({
        systemReducesMotion: window.matchMedia('(prefers-reduced-motion: reduce)').matches,
        // The app's Accessibility setting marks the document; see the reduced-motion styles.
        appReducesMotion: document.documentElement.classList.contains('reduced-motion')
    });
}
