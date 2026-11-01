import type { Settings, SettingsUpdate } from '../api/settings';

/**
 * One Settings section's share of the single form draft.
 *
 * Settings keeps one draft and one Apply, because a save restarts workers and settings
 * interact. Each section owns how its saved values become editable fields (`decode`) and how
 * those fields become its part of the save (`encodePatch`); the page composes the sections.
 */
export interface SettingsSectionAdapter<Draft, Patch extends SettingsUpdate> {
    decode(saved: Settings): Draft;
    encodePatch(draft: Draft): Patch;
}

/**
 * A section is unsaved when what it would send differs from what its saved values would send.
 * Comparing encoded patches gives the dirty check the same defaults and normalisation as loading,
 * so an unedited section can never look changed.
 */
export function sectionIsDirty<Draft, Patch extends SettingsUpdate>(
    adapter: SettingsSectionAdapter<Draft, Patch>,
    draft: Draft,
    saved: Settings
): boolean {
    const current = adapter.encodePatch(draft);
    const baseline = adapter.encodePatch(adapter.decode(saved));
    return (Object.keys(current) as (keyof Patch)[]).some(
        (key) => JSON.stringify(current[key]) !== JSON.stringify(baseline[key])
    );
}
