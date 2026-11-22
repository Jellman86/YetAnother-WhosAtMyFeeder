import { settingsSectionOfPart, type SettingsPart, type SettingsSection } from './settings-route';

/**
 * A place in Settings as copy names it: "Settings → Cameras & connection → Location". The words
 * come from the navigation's own labels, so a sentence that points at a setting follows it when a
 * section is renamed or a part moves, in every language.
 */
type Translate = (key: string) => string;

const ARROW = ' → ';

/** A section's name as the navigation shows it. */
export function settingsSectionName(section: SettingsSection, translate: Translate): string {
    return translate(`settings.sections.${section}`);
}

/** "Settings → <section>". */
export function settingsSectionPlace(section: SettingsSection, translate: Translate): string {
    return [translate('nav.settings'), settingsSectionName(section, translate)].join(ARROW);
}

/** "Settings → <section> → <part>", the section being the one that holds the part. */
export function settingsPartPlace(part: SettingsPart, translate: Translate): string {
    return [settingsSectionPlace(settingsSectionOfPart(part), translate), translate(`settings.tabs.${part}`)].join(ARROW);
}

/** "Settings → <section> → <group>", for a group that is not a part, named by its own heading. */
export function settingsGroupPlace(section: SettingsSection, headingKey: string, translate: Translate): string {
    return [settingsSectionPlace(section, translate), translate(headingKey)].join(ARROW);
}
