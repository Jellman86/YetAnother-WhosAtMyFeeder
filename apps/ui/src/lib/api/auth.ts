import { API_BASE, apiFetch, getHeaders, setAuthToken } from './core';

export interface AuthStatusResponse {
    auth_required: boolean;
    public_access_enabled: boolean;
    public_access_show_ai_conversation?: boolean;
    public_access_allow_clip_downloads?: boolean;
    is_authenticated: boolean;
    birdnet_enabled: boolean;
    llm_enabled: boolean;
    llm_ready: boolean;
    ebird_enabled: boolean;
    inaturalist_enabled: boolean;
    enrichment_mode: string;
    enrichment_single_provider: string;
    enrichment_summary_source: string;
    enrichment_sightings_source: string;
    enrichment_seasonality_source: string;
    enrichment_rarity_source: string;
    enrichment_links_sources: string[];
    display_common_names: boolean;
    scientific_name_primary: boolean;
    accessibility_live_announcements: boolean;
    location_temperature_unit: string;
    date_format: string;
    username: string | null;
    needs_initial_setup: boolean;
    https_warning: boolean;
}

export interface LoginResponse {
    access_token: string;
    token_type: string;
    username: string;
    expires_in_hours: number;
}

export async function fetchAuthStatus(): Promise<AuthStatusResponse> {
    const response = await fetch(`${API_BASE}/auth/status`, {
        headers: getHeaders()
    });

    if (!response.ok) {
        throw new Error('Failed to fetch auth status');
    }

    return response.json();
}

export async function login(username: string, password: string): Promise<LoginResponse> {
    const response = await apiFetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ username, password })
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || 'Login failed');
    }

    const data: LoginResponse = await response.json();
    setAuthToken(data.access_token, data.expires_in_hours);
    return data;
}

export async function logout(): Promise<void> {
    await apiFetch(`${API_BASE}/auth/logout`, { method: 'POST' });
    setAuthToken(null);
}

export async function setInitialPassword(options: {
    username: string;
    password: string | null;
    enableAuth: boolean;
}): Promise<void> {
    const response = await apiFetch(`${API_BASE}/auth/initial-setup`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            username: options.username,
            password: options.password,
            enable_auth: options.enableAuth
        })
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || 'Initial setup failed');
    }
}
