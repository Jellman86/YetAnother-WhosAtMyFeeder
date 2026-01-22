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

    // Derived permission states
    canModify = $derived(this.isAuthenticated);
    isGuest = $derived(!this.isAuthenticated && this.publicAccessEnabled);
    showSettings = $derived(this.isAuthenticated);

    constructor() {
        // Status is loaded via loadStatus()
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
    }
}

export const authStore = new AuthStore();
