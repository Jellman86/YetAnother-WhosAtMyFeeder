export const API_BASE = '/api';

// API Key Management
let apiKey: string | null = typeof localStorage !== 'undefined' ? localStorage.getItem('api_key') : null;

// Auth Token Management (JWT)
let authToken: string | null = typeof localStorage !== 'undefined' ? localStorage.getItem('auth_token') : null;
let authTokenExpiresAt: number = typeof localStorage !== 'undefined'
    ? Number(localStorage.getItem('auth_token_expires_at') || 0)
    : 0;

export function setApiKey(key: string | null) {
    apiKey = key;
    if (typeof localStorage !== 'undefined') {
        if (key) localStorage.setItem('api_key', key);
        else localStorage.removeItem('api_key');
    }
}

export function getApiKey(): string | null {
    return apiKey;
}

function appendQueryParam(url: string, key: string, value: string): string {
    const separator = url.includes('?') ? '&' : '?';
    return `${url}${separator}${key}=${encodeURIComponent(value)}`;
}

export function withAuthParams(url: string): string {
    const token = getAuthToken();
    if (token) {
        return appendQueryParam(url, 'token', token);
    }
    if (apiKey) {
        return appendQueryParam(url, 'api_key', apiKey);
    }
    return url;
}

function isAuthTokenExpired(): boolean {
    if (!authToken || !authTokenExpiresAt) {
        return false;
    }
    return Date.now() >= authTokenExpiresAt;
}

export function setAuthToken(token: string | null, expiresInHours?: number) {
    authToken = token;
    if (typeof localStorage !== 'undefined') {
        if (token) {
            localStorage.setItem('auth_token', token);
            if (expiresInHours) {
                authTokenExpiresAt = Date.now() + expiresInHours * 60 * 60 * 1000;
                localStorage.setItem('auth_token_expires_at', String(authTokenExpiresAt));
            } else {
                authTokenExpiresAt = 0;
                localStorage.removeItem('auth_token_expires_at');
            }
        } else {
            localStorage.removeItem('auth_token');
            localStorage.removeItem('auth_token_expires_at');
            authTokenExpiresAt = 0;
        }
    }
}

export function getAuthToken(): string | null {
    if (isAuthTokenExpired()) {
        setAuthToken(null);
        return null;
    }
    return authToken;
}

export function getHeaders(customHeaders: HeadersInit = {}): HeadersInit {
    const headers: Record<string, string> = { ...customHeaders as Record<string, string> };
    const token = getAuthToken();
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }
    if (apiKey) {
        headers['X-API-Key'] = apiKey;
    }

    if (typeof localStorage !== 'undefined') {
        const preferredLang = localStorage.getItem('preferred-language');
        if (preferredLang) {
            headers['Accept-Language'] = preferredLang;
        }
    }

    return headers;
}

let authErrorCallback: (() => void) | null = null;

export function setAuthErrorCallback(callback: () => void) {
    authErrorCallback = callback;
}

export async function apiFetch(url: string, options: RequestInit = {}): Promise<Response> {
    const response = await fetch(url, {
        ...options,
        headers: getHeaders(options.headers)
    });

    if (response.status === 401 && authErrorCallback) {
        authErrorCallback();
    }

    return response;
}

const abortControllers = new Map<string, AbortController>();

export async function fetchWithAbort<T>(
    key: string | null,
    url: string,
    options: RequestInit = {}
): Promise<T> {
    if (key && abortControllers.has(key)) {
        abortControllers.get(key)!.abort();
        abortControllers.delete(key);
    }

    let controller: AbortController | undefined;
    if (key) {
        controller = new AbortController();
        abortControllers.set(key, controller);
    }

    try {
        const fetchOptions: RequestInit = {
            ...options,
            headers: getHeaders(options.headers),
            signal: controller?.signal
        };

        const response = await fetch(url, fetchOptions);

        if (key) {
            abortControllers.delete(key);
        }

        return await handleResponse<T>(response);
    } catch (error) {
        if (key) {
            abortControllers.delete(key);
        }

        if (error instanceof Error && error.name === 'AbortError') {
            console.log(`Request cancelled: ${key || url}`);
        }
        throw error;
    }
}

export function cancelRequest(key: string) {
    if (abortControllers.has(key)) {
        abortControllers.get(key)!.abort();
        abortControllers.delete(key);
    }
}

export async function handleResponse<T>(response: Response): Promise<T> {
    if (!response.ok) {
        const error = await response.text();
        throw new Error(error || `HTTP ${response.status}`);
    }
    return response.json();
}
