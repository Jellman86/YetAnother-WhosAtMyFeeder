import {
    fetchAuthStatus,
    getAuthToken,
    login as apiLogin,
    logout as apiLogout,
    setAuthToken,
    setInitialPassword
} from '../api';
import {
    getTemperatureUnitForSystem,
    resolveWeatherUnitSystem,
    type WeatherUnitSystem
} from '../utils/weather-units';
import { StaleTracker } from '../utils/stale_tracker';
import { refreshCoordinator } from './refresh_coordinator.svelte';

class AuthStore {
    authRequired = $state(false);
    publicAccessEnabled = $state(false);
    publicAccessShowAiConversation = $state(false);
    publicAccessAllowClipDownloads = $state(false);
    needsInitialSetup = $state(false);
    isAuthenticated = $state(false);
    username = $state<string | null>(null);
    statusLoaded = $state(false);
    statusHealthy = $state(false);
    token = $state(getAuthToken());
    httpsWarning = $state(false);
    forceLogin = $state(false);
    birdnetEnabled = $state(false);
    llmEnabled = $state(false);
    llmReady = $state(false);
    ebirdEnabled = $state(false);
    inaturalistEnabled = $state(false);
    enrichmentMode = $state("per_enrichment");
    enrichmentSingleProvider = $state("wikipedia");
    enrichmentSummarySource = $state("wikipedia");
    enrichmentSightingsSource = $state("disabled");
    enrichmentSeasonalitySource = $state("disabled");
    enrichmentRaritySource = $state("disabled");
    enrichmentLinksSources = $state<string[]>(["wikipedia", "inaturalist"]);
    displayCommonNames = $state(true);
    scientificNamePrimary = $state(false);
    liveAnnouncements = $state(true);
    locationWeatherUnitSystem = $state<WeatherUnitSystem>("metric");
    locationTemperatureUnit = $state("celsius");
    dateFormat = $state("locale");
    private readonly staleTracker = new StaleTracker(300_000); // 5 minutes
    private readonly unregister: () => void;

    // Owner-only UI must stay locked until auth status has loaded successfully.
    hasOwnerAccess = $derived(this.statusLoaded && this.statusHealthy && (this.isAuthenticated || !this.authRequired));
    canModify = $derived(this.hasOwnerAccess);
    isGuest = $derived(this.statusLoaded && this.statusHealthy && this.authRequired && !this.isAuthenticated && this.publicAccessEnabled);
    showSettings = $derived(this.hasOwnerAccess);
    canViewAiConversation = $derived(this.hasOwnerAccess || (this.isGuest && this.publicAccessShowAiConversation));

    constructor() {
        // Status is loaded via loadStatus()
        this.unregister = refreshCoordinator.register(() => this.refreshIfStale());
    }

    requestLogin() {
        this.forceLogin = true;
    }

    cancelLogin() {
        this.forceLogin = false;
    }

    async loadStatus() {
        try {
            const status = await fetchAuthStatus();
            this.authRequired = status.auth_required;
            this.publicAccessEnabled = status.public_access_enabled;
            this.publicAccessShowAiConversation = status.public_access_show_ai_conversation ?? false;
            this.publicAccessAllowClipDownloads = status.public_access_allow_clip_downloads ?? false;
            this.needsInitialSetup = status.needs_initial_setup;
            this.isAuthenticated = status.is_authenticated;
            this.username = status.username ?? null;
            this.httpsWarning = status.https_warning ?? false;
            this.birdnetEnabled = status.birdnet_enabled ?? false;
            this.llmEnabled = status.llm_enabled ?? false;
            this.llmReady = status.llm_ready ?? false;
            this.ebirdEnabled = status.ebird_enabled ?? false;
            this.inaturalistEnabled = status.inaturalist_enabled ?? false;
            this.enrichmentMode = status.enrichment_mode ?? "per_enrichment";
            this.enrichmentSingleProvider = status.enrichment_single_provider ?? "wikipedia";
            this.enrichmentSummarySource = status.enrichment_summary_source ?? "wikipedia";
            this.enrichmentSightingsSource = status.enrichment_sightings_source ?? "disabled";
            this.enrichmentSeasonalitySource = status.enrichment_seasonality_source ?? "disabled";
            this.enrichmentRaritySource = status.enrichment_rarity_source ?? "disabled";
            this.enrichmentLinksSources = status.enrichment_links_sources ?? ["wikipedia", "inaturalist"];
            this.displayCommonNames = status.display_common_names ?? true;
            this.scientificNamePrimary = status.scientific_name_primary ?? false;
            this.liveAnnouncements = status.accessibility_live_announcements ?? true;
            this.locationWeatherUnitSystem = resolveWeatherUnitSystem(
                status.location_weather_unit_system,
                status.location_temperature_unit
            );
            this.locationTemperatureUnit = getTemperatureUnitForSystem(this.locationWeatherUnitSystem);
            this.dateFormat = status.date_format ?? "locale";
            this.statusHealthy = true;
            this.staleTracker.touch();
        } catch (err) {
            console.error('Failed to load auth status', err);
            // Fail closed on auth-status errors so owner-only UI never leaks.
            this.authRequired = true;
            this.publicAccessEnabled = false;
            this.publicAccessShowAiConversation = false;
            this.publicAccessAllowClipDownloads = false;
            this.isAuthenticated = false;
            this.username = null;
            this.statusHealthy = false;
        } finally {
            this.token = getAuthToken();
            this.statusLoaded = true;
        }
    }

    async refreshIfStale(): Promise<void> {
        if (!this.staleTracker.isStale()) return;
        await this.loadStatus();
    }

    async login(username: string, password: string) {
        await apiLogin(username, password);
        this.token = getAuthToken();
        await this.loadStatus();
    }

    async logout() {
        await apiLogout();
        this.staleTracker.reset();
        this.token = null;
        await this.loadStatus();
    }

    async completeInitialSetup(options: { username: string; password: string | null; enableAuth: boolean }) {
        await setInitialPassword(options);
        this.token = getAuthToken();
        await this.loadStatus();
    }

    handleAuthError() {
        setAuthToken(null);
        this.token = null;
        this.isAuthenticated = false;
        // Refresh status to see if auth requirements changed (e.g. auth enabled)
        this.loadStatus();
    }
}

export const authStore = new AuthStore();
