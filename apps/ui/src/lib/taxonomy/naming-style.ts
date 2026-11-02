import { authStore } from '../stores/auth.svelte';
import { settingsStore } from '../stores/settings.svelte';
import { namingStyle, type NamingStyle } from './nomenclature';

/**
 * The reader's Bird Naming Style (Settings, Appearance), the same one the record and the
 * leaderboard follow. Read inside a `$derived`, so changing it relabels every tree at once.
 */
export function currentNamingStyle(): NamingStyle {
    return namingStyle(
        settingsStore.settings?.display_common_names ?? authStore.displayCommonNames ?? true,
        settingsStore.settings?.scientific_name_primary ?? authStore.scientificNamePrimary ?? false
    );
}
