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
    private loadGeneration = 0;
    private readonly staleTracker = new StaleTracker(300_000); // 5 minutes
    private lastReadAt = Number.NEGATIVE_INFINITY;
    private readonly fetchSettings: () => Promise<Settings>;
    private readonly canReadSettings: () => boolean;

    constructor(options: SettingsStoreOptions = {}) {
        this.fetchSettings = options.fetchSettings ?? apiFetchSettings;
        this.canReadSettings =
            options.canReadSettings ??
            (() => authStore.isAuthenticated || !authStore.authRequired);
        refreshCoordinator.register(() => this.refreshIfStale());
    }

    async load() {
        if (!this.canReadSettings()) return;
        if (this._loadPromise) return this._loadPromise;

        const generation = this.loadGeneration;
        this._loadPromise = (async () => {
            this.isLoading = true;
            this.error = null;
            try {
                const settings = await this.fetchSettings();
                if (generation !== this.loadGeneration || !this.canReadSettings()) return;
                this.settings = settings;
                this.lastReadAt = Date.now();
                this.staleTracker.touch();
            } catch (e) {
                if (generation !== this.loadGeneration || !this.canReadSettings()) return;
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
                if (generation === this.loadGeneration) {
                    this.isLoading = false;
                    this._loadPromise = null;
                }
            }
        })();

        return this._loadPromise;
    }

    async refreshIfStale(): Promise<void> {
        if (!this.canReadSettings()) return;
        if (this._loadPromise !== null || !this.staleTracker.isStale()) return;
        await this.load();
    }

    /**
     * The settings for a reader that does not need its own request: the shell, a header control and
     * a page all ask during one page load, and one response answers them. Joins a read in flight,
     * reuses a copy no older than `maxAgeMs`, and reads otherwise.
     *
     * A reader that names an age is promised a copy that fresh. If the read it needs fails, this
     * rejects with the reason; it never hands back the older copy as though it had just been read.
     * A reader that only displays settings passes no age and accepts the copy held, which saves and
     * live updates keep current.
     */
    async read(maxAgeMs: number = Number.POSITIVE_INFINITY): Promise<Settings> {
        if (!this.canReadSettings()) throw new Error('Settings are not available to this session');
        const freshEnough = (): boolean => this.settings !== null && Date.now() - this.lastReadAt <= maxAgeMs;
        if (this._loadPromise === null && freshEnough() && this.settings) return this.settings;
        await this.load();
        if (!freshEnough() || !this.settings) throw new Error(this.error ?? 'Settings could not be read');
        return this.settings;
    }

    /** A complete copy just read from or saved to the server, so it is as fresh as a read. */
    update(newSettings: Settings) {
        if (!this.canReadSettings()) return;
        this.settings = newSettings;
        this.lastReadAt = Date.now();
    }

    /**
     * Merges fields the server has confirmed into the copy held. The rest of that copy is no newer
     * than before, so this keeps its age: a reader that needs a fresh copy still reads again.
     */
    patch(confirmed: Partial<Settings>) {
        if (!this.canReadSettings() || !this.settings) return;
        this.settings = { ...this.settings, ...confirmed };
    }

    clear() {
        this.loadGeneration += 1;
        this._loadPromise = null;
        this.settings = null;
        this.isLoading = false;
        this.error = null;
        this.staleTracker.reset();
        this.lastReadAt = Number.NEGATIVE_INFINITY;
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
