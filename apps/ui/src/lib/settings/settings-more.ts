import type { SettingsPart, SettingsSection } from './settings-route';

/** The disclosure id of a section's More options, which the page opens to show a field inside it. */
export function settingsMoreId(section: SettingsSection): string {
    return `settings-more-${section}`;
}

/** Parts shown inside their section's More options, which the page opens to land on them. */
const PARTS_IN_MORE: ReadonlySet<SettingsPart> = new Set(['integrations', 'ai']);

export function settingsPartIsInMore(part: SettingsPart): boolean {
    return PARTS_IN_MORE.has(part);
}
