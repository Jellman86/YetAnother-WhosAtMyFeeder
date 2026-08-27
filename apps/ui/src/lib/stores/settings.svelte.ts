import { fetchSettings as apiFetchSettings, type Settings } from '../api';
import { authStore } from './auth.svelte';
import { StaleTracker } from '../utils/stale_tracker';
import { refreshCoordinator } from './refresh_coordinator.svelte';

interface SettingsStoreOptions {
    fetchSettings?: () => Promise<Settings>;
    /** Settings are an owner reading; guests must not poll an endpoint that will 403. */
    canReadSettings?: () => boolean;
}

// Svelte 5 shared state for settings
export class SettingsStore {
    settings = $state<Settings | null>(null);
    isLoading = $state(false);
    error = $state<string | null>(null);
    private _loadPromise: Promise<void> | null = null;
    private readonly staleTracker = new StaleTracker(300_000); // 5 minutes
    private readonly unregister: () => void;
    private readonly fetchSettings: () => Promise<Settings>;
    private readonly canReadSettings: () => boolean;

    constructor(options: SettingsStoreOptions = {}) {
        this.fetchSettings = options.fetchSettings ?? apiFetchSettings;
        this.canReadSettings =
            options.canReadSettings ??
            (() => authStore.isAuthenticated || !authStore.authRequired);
        this.unregister = refreshCoordinator.register(() => this.refreshIfStale());
    }

    async load() {
        if (!this.canReadSettings()) return;
        if (this._loadPromise) return this._loadPromise;

        this._loadPromise = (async () => {
            this.isLoading = true;
            this.error = null;
            try {
                this.settings = await this.fetchSettings();
                this.staleTracker.touch();
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

    async refreshIfStale(): Promise<void> {
        if (!this.canReadSettings()) return;
        if (this._loadPromise !== null || !this.staleTracker.isStale()) return;
        await this.load();
    }

    update(newSettings: Settings) {
        this.settings = newSettings;
    }

    clear() {
        this.settings = null;
    }

    // Computed properties for common settings
    get llmEnabled() {
        return this.settings?.llm_enabled ?? authStore.llmEnabled ?? false;
    }

    get llmReady() {
        return this.settings?.llm_ready ?? authStore.llmReady ?? false;
    }

    get birdnetEnabled() {
        return this.settings?.birdnet_enabled ?? authStore.birdnetEnabled ?? false;
    }

    get displayCommonNames() {
        return this.settings?.display_common_names ?? authStore.displayCommonNames ?? true;
    }

    get scientificNamePrimary() {
        return this.settings?.scientific_name_primary ?? authStore.scientificNamePrimary ?? false;
    }

    get liveAnnouncements() {
        return this.settings?.accessibility_live_announcements ?? authStore.liveAnnouncements ?? true;
    }
}

export const settingsStore = new SettingsStore();
