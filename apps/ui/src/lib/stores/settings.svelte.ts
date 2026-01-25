import { fetchSettings, type Settings } from '../api';

// Svelte 5 shared state for settings
class SettingsStore {
    settings = $state<Settings | null>(null);
    isLoading = $state(false);
    error = $state<string | null>(null);
    private _loadPromise: Promise<void> | null = null;

    async load() {
        if (this._loadPromise) return this._loadPromise;

        this._loadPromise = (async () => {
            this.isLoading = true;
            this.error = null;
            try {
                this.settings = await fetchSettings();
            } catch (e) {
                const errorMessage = e instanceof Error ? e.message : 'Failed to load settings';
                const isAuthExpected =
                    typeof errorMessage === 'string' &&
                    (errorMessage.includes('Owner privileges required') ||
                        errorMessage.includes('HTTP 403') ||
                        errorMessage.includes('403'));
                if (!isAuthExpected) {
                    this.error = errorMessage;
                    // Don't log AbortError as it's expected behavior if we were using cancellable requests
                    if (e instanceof Error && e.name !== 'AbortError') {
                        console.error('Failed to load settings store', e);
                    }
                }
            } finally {
                this.isLoading = false;
                this._loadPromise = null;
            }
        })();

        return this._loadPromise;
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
