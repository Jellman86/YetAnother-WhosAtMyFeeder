import { appApiPath, normalizeBackendPath } from '../app/url-base';

export const API_BASE = appApiPath('/api');

import { readApiErrorMessage } from './error-message';

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
    const normalizedUrl = normalizeBackendPath(url);
    const token = getAuthToken();
    if (token) {
        return appendQueryParam(normalizedUrl, 'token', token);
    }
    if (apiKey) {
        return appendQueryParam(normalizedUrl, 'api_key', apiKey);
    }
    return normalizedUrl;
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

    if (typeof Intl !== 'undefined') {
        const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
        if (tz) {
            headers['X-Timezone'] = tz;
        }
    }

    return headers;
}

let authErrorCallback: (() => void) | null = null;

export function setAuthErrorCallback(callback: () => void) {
    authErrorCallback = callback;
}

export interface ApiFetchOptions extends RequestInit {
    /** Abort the request after this many milliseconds. Omit for user-driven, long-running operations. */
    timeoutMs?: number;
}

export async function apiFetch(url: string, options: ApiFetchOptions = {}): Promise<Response> {
    const { timeoutMs, signal: callerSignal, ...requestOptions } = options;
    const controller = typeof timeoutMs === 'number' || callerSignal ? new AbortController() : null;
    let timeoutId: ReturnType<typeof setTimeout> | null = null;
    const abortFromCaller = () => controller?.abort(callerSignal?.reason);

    if (controller && callerSignal) {
        if (callerSignal.aborted) abortFromCaller();
        else callerSignal.addEventListener('abort', abortFromCaller, { once: true });
    }
    if (controller && typeof timeoutMs === 'number' && timeoutMs > 0) {
        timeoutId = setTimeout(() => {
            controller.abort(new DOMException(`Request timed out after ${timeoutMs}ms`, 'AbortError'));
        }, timeoutMs);
    }

    let response: Response;
    try {
        response = await fetch(normalizeBackendPath(url), {
            ...requestOptions,
            headers: getHeaders(options.headers),
            signal: controller?.signal ?? callerSignal
        });
    } finally {
        if (timeoutId) clearTimeout(timeoutId);
        callerSignal?.removeEventListener('abort', abortFromCaller);
    }

    if (response.status === 401 && authErrorCallback) {
        authErrorCallback();
    }

    return response;
}

const abortControllers = new Map<string, AbortController>();

export async function fetchWithAbort<T>(
    key: string | null,
    url: string,
    options: ApiFetchOptions = {}
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
        const fetchOptions: ApiFetchOptions = {
            ...options,
            signal: controller?.signal ?? options.signal
        };

        const response = await apiFetch(url, fetchOptions);

        if (key && abortControllers.get(key) === controller) {
            abortControllers.delete(key);
        }

        return await handleResponse<T>(response);
    } catch (error) {
        if (key && abortControllers.get(key) === controller) {
            abortControllers.delete(key);
        }

        if (error instanceof Error && error.name === 'AbortError') {
            console.debug(`Request cancelled: ${key || url}`);
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

/** A failed API response, keeping the HTTP status so callers can tell
 * "this thing does not exist" (404) apart from "the request broke". */
export class ApiRequestError extends Error {
    readonly status: number;

    constructor(message: string, status: number) {
        super(message);
        this.name = 'ApiRequestError';
        this.status = status;
    }
}

export async function handleResponse<T>(response: Response): Promise<T> {
    if (!response.ok) {
        const error = await readApiErrorMessage(response, `HTTP ${response.status}`);
        throw new ApiRequestError(error, response.status);
    }
    return response.json();
}
