import type { SettingsSection } from './settings-route';

/** The disclosure id of a section's More options, which the page opens to show a field inside it. */
export function settingsMoreId(section: SettingsSection): string {
    return `settings-more-${section}`;
}
