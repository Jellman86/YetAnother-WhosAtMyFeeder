import { API_BASE, apiFetch, setAuthToken } from './core';
import { readApiErrorMessage } from './error-message';
import type { paths } from './generated/openapi';

export type AuthStatusResponse = paths['/api/auth/status']['get']['response'];

export type LoginResponse = paths['/api/auth/login']['post']['response'];
export type InitialSetupResponse = paths['/api/auth/initial-setup']['post']['response'];

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
