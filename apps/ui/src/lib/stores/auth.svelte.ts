import {
    fetchAuthStatus,
    getAuthToken,
    login as apiLogin,
    logout as apiLogout,
    setAuthToken,
    setInitialPassword
} from '../api';

class AuthStore {
    authRequired = $state(false);
    publicAccessEnabled = $state(false);
    needsInitialSetup = $state(false);
    isAuthenticated = $state(false);
    username = $state<string | null>(null);
    statusLoaded = $state(false);
    token = $state(getAuthToken());
    httpsWarning = $state(false);
    forceLogin = $state(false);
    birdnetEnabled = $state(false);
    llmEnabled = $state(false);
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
    locationTemperatureUnit = $state("celsius");

    // Derived permission states
    canModify = $derived(this.isAuthenticated || !this.authRequired);
    isGuest = $derived(this.authRequired && !this.isAuthenticated && this.publicAccessEnabled);
    showSettings = $derived(this.isAuthenticated || !this.authRequired);

    constructor() {
        // Status is loaded via loadStatus()
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
            this.needsInitialSetup = status.needs_initial_setup;
            this.isAuthenticated = status.is_authenticated;
            this.username = status.username ?? null;
            this.httpsWarning = status.https_warning ?? false;
            this.birdnetEnabled = status.birdnet_enabled ?? false;
            this.llmEnabled = status.llm_enabled ?? false;
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
            this.locationTemperatureUnit = status.location_temperature_unit ?? "celsius";
        } catch (err) {
            console.error('Failed to load auth status', err);
        } finally {
            this.token = getAuthToken();
            this.statusLoaded = true;
        }
    }

    async login(username: string, password: string) {
        await apiLogin(username, password);
        this.token = getAuthToken();
        await this.loadStatus();
    }

    async logout() {
        await apiLogout();
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
