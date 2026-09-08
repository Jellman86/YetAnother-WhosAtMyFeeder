import { API_BASE, apiFetch, setAuthToken } from './core';
import { readApiErrorMessage } from './error-message';
import type { paths } from './generated/openapi';

export type AuthStatusResponse = paths['/api/auth/status']['get']['response'];

export type LoginResponse = paths['/api/auth/login']['post']['response'];
export type InitialSetupResponse = paths['/api/auth/initial-setup']['post']['response'];
export type StreamTicketResponse = paths['/api/auth/stream-ticket']['post']['response'];

export async function fetchAuthStatus(): Promise<AuthStatusResponse> {
    const response = await apiFetch(`${API_BASE}/auth/status`, { timeoutMs: 10_000 });

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
        throw new Error(await readApiErrorMessage(response, 'Login failed'));
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
}): Promise<InitialSetupResponse> {
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
        throw new Error(await readApiErrorMessage(response, 'Initial setup failed'));
    }

    const data: InitialSetupResponse = await response.json();
    if (data.access_token) {
        setAuthToken(data.access_token, data.expires_in_hours ?? undefined);
    }
    return data;
}

/**
 * Exchange the current session for a single-use ticket that opens the live stream.
 * The stream cannot carry the session token itself (see `app/stream-url.ts`).
 */
export async function createStreamTicket(): Promise<StreamTicketResponse> {
    const response = await apiFetch(`${API_BASE}/auth/stream-ticket`, { method: 'POST', timeoutMs: 10_000 });

    if (!response.ok) {
        throw new Error(await readApiErrorMessage(response, 'Could not open the live stream'));
    }

    return response.json();
}

/**
 * Attach this browser's existing session to the media cookie.
 *
 * Login and first-run setup set the cookie themselves; this covers a browser that
 * signed in before the cookie existed and still holds only a bearer token, so its
 * images keep loading after the upgrade without a fresh login.
 */
export async function createSessionCookie(): Promise<void> {
    const response = await apiFetch(`${API_BASE}/auth/session-cookie`, { method: 'POST', timeoutMs: 10_000 });

    if (!response.ok) {
        throw new Error(await readApiErrorMessage(response, 'Could not attach the session to media requests'));
    }
}
