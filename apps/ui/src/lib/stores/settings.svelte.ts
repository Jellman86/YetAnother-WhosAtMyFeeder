import { fetchSettings, type Settings } from '../api';

// Svelte 5 shared state for settings
class SettingsStore {
    settings = $state<Settings | null>(null);
    isLoading = $state(false);
    error = $state<string | null>(null);

    async load() {
        this.isLoading = true;
        this.error = null;
        try {
            this.settings = await fetchSettings();
        } catch (e) {
            const errorMessage = e instanceof Error ? e.message : 'Failed to load settings';
            this.error = errorMessage;
            console.error('Failed to load settings store', e);
        } finally {
            this.isLoading = false;
        }
    }

    update(newSettings: Settings) {
        this.settings = newSettings;
    }

    clear() {
        this.settings = null;
    }

    // Computed properties for common settings
    get llmEnabled() {
        return this.settings?.llm_enabled ?? false;
    }

    get displayCommonNames() {
        return this.settings?.display_common_names ?? true;
    }

    get scientificNamePrimary() {
        return this.settings?.scientific_name_primary ?? false;
    }
}

export const settingsStore = new SettingsStore();
