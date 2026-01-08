import { setApiKey, getApiKey } from '../api';

class AuthStore {
    requiresLogin = $state(false);
    apiKey = $state(getApiKey());

    constructor() {
        // If we have a key, assume we are logged in until proven otherwise (401)
        // Actually, if we have no key, we might need login IF the server requires it.
        // But the server only requires it if configured.
        // So we should try to make a request (e.g. /version or /health) and see if we get 401.
        // But /health is public. /api/settings requires auth.
    }

    setRequiresLogin(value: boolean) {
        this.requiresLogin = value;
    }

    login(key: string) {
        setApiKey(key);
        this.apiKey = key;
        this.requiresLogin = false;
        // Reload page or re-init app?
        // Ideally just retry failed requests, but simple reload is easier for now
        window.location.reload(); 
    }

    logout() {
        setApiKey(null);
        this.apiKey = null;
        this.requiresLogin = true;
    }
}

export const authStore = new AuthStore();
