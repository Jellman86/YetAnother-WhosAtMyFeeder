import { appApiPath, normalizeBackendPath } from '../app/url-base';

export const API_BASE = appApiPath('/api');

import { discardBody, readApiErrorMessage } from './error-message';

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

function appendQueryParam(url: string, key: string, value: string): string {
    const separator = url.includes('?') ? '&' : '?';
    return `${url}${separator}${key}=${encodeURIComponent(value)}`;
}

/**
 * Media URLs for `<img>`, `<video>` and `<audio>`, which cannot send headers.
 *
 * The session is never put in the query string: every proxy in front of YA-WAMF
 * logs request URIs, and a session token there is a week of owner access per
 * thumbnail. A signed-in browser holds the session as an HttpOnly cookie that the
 * media routes accept instead (see `createSessionCookie`). Only the deprecated
 * API key, which has no cookie form, still rides in the URL.
 */
export function withAuthParams(url: string): string {
    const normalizedUrl = normalizeBackendPath(url);
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

/**
 * Who is asking, and in which language. Readings shared between views are kept per scope, so a
 * guest and the owner, or two languages, never share one. Kept in memory only.
 */
export function requestScope(): string {
    const language = typeof localStorage !== 'undefined' ? localStorage.getItem('preferred-language') ?? '' : '';
    return `${getAuthToken() ?? ''}|${apiKey ?? ''}|${language}`;
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

/**
 * One request with the caller's abort and the timeout attached, held until `read` has finished
 * with the response. Releasing at the headers, as `apiFetch` does, leaves a body that stalls
 * afterwards with no timeout and nothing to cancel it.
 */
async function guardedRequest<T>(url: string, options: ApiFetchOptions, read: (response: Response) => Promise<T>): Promise<T> {
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

    try {
        const response = await fetch(normalizeBackendPath(url), {
            ...requestOptions,
            headers: getHeaders(options.headers),
            signal: controller?.signal ?? callerSignal
        });
        if (response.status === 401 && authErrorCallback) {
            authErrorCallback();
        }
        try {
            return await read(response);
        } catch (error) {
            // A body left unread on the way out would hold the connection open with nothing timing it.
            discardBody(response);
            throw error;
        }
    } finally {
        if (timeoutId) clearTimeout(timeoutId);
        callerSignal?.removeEventListener('abort', abortFromCaller);
    }
}

/**
 * The response once its headers arrive. The timeout and the caller's abort cover the request up
 * to the headers only, so a caller that streams a long body (a download, a clip) is never cut off
 * by it; a caller that wants the whole body covered uses `apiFetchJson`.
 */
export function apiFetch(url: string, options: ApiFetchOptions = {}): Promise<Response> {
    return guardedRequest(url, options, async (response) => response);
}

/** The deadline a guarded read gets when the one it was given is not a positive, finite wait. */
const GUARDED_READ_DEFAULT_TIMEOUT_MS = 30_000;

/** Options for a guarded read: its deadline is required, so no guarded read can wait for ever. */
export interface GuardedFetchOptions extends ApiFetchOptions {
    timeoutMs: number;
}

function withDeadline(options: GuardedFetchOptions): GuardedFetchOptions {
    const { timeoutMs } = options;
    const bounded = Number.isFinite(timeoutMs) && timeoutMs > 0 ? timeoutMs : GUARDED_READ_DEFAULT_TIMEOUT_MS;
    return { ...options, timeoutMs: bounded };
}

declare const guardedRead: unique symbol;

/**
 * A read whose timeout and cancellation cover the whole response, body included. Only the guarded
 * client below makes one, and the retrying readers accept nothing else, so a read that could
 * stall after its headers (a bare `fetch`, `apiFetch`, or an `async` function) does not type-check
 * where a reader expects one.
 */
export type Guarded<T> = Promise<T> & { readonly [guardedRead]: true };

function guarded<T>(read: Promise<T>): Guarded<T> {
    return read as Guarded<T>;
}

/**
 * A step after a guarded read that makes no request of its own: it may not return a promise. A
 * result widened to `unknown` or `void` is refused too, since a promise would pass as either.
 */
type Settled<R> = unknown extends R ? never : void extends R ? never : R extends PromiseLike<unknown> ? never : R;

/**
 * Whether resolving `value` could follow it as a promise. `then` is looked up by descriptor along
 * the prototype chain and never read: a getter could answer differently when the promise reads it
 * again, so any getter or setter is refused, and so is a function.
 */
function mayBeThenable(value: unknown): boolean {
    if (value === null || (typeof value !== 'object' && typeof value !== 'function')) return false;
    for (let holder: object | null = value; holder !== null; holder = Object.getPrototypeOf(holder)) {
        const descriptor = Object.getOwnPropertyDescriptor(holder, 'then');
        if (descriptor) return 'get' in descriptor || 'set' in descriptor || typeof descriptor.value === 'function';
    }
    return false;
}

/** The run-time half of `Settled`, for a promise a cast got past the compiler. */
function settled<R>(value: R): R {
    if (mayBeThenable(value)) throw new TypeError('A step after a guarded read may not start a request of its own');
    return value;
}

/**
 * The parsed JSON body, with the timeout and the caller's abort covering the request until the
 * body has been read: a response that stalls after its headers is still timed out or cancelled.
 */
export function apiFetchJson<T>(url: string, options: GuardedFetchOptions): Guarded<T> {
    return guarded(guardedRequest(url, withDeadline(options), (response) => handleResponse<T>(response)));
}

/** A guarded read's value put to use, by a step that makes no request; failures pass to `onError`. */
export function mapGuarded<T, R>(
    read: Guarded<T>,
    next: (value: T) => Settled<R>,
    onError?: (error: unknown) => Settled<R>
): Guarded<R> {
    return guarded(read.then((value) => settled(next(value)), onError && ((error: unknown) => settled(onError(error)))));
}

/** A guarded read followed by another guarded read; failures of either pass to `onError`. */
export function chainGuarded<T, R>(
    read: Guarded<T>,
    next: (value: T) => Guarded<R>,
    onError?: (error: unknown) => Settled<R>
): Guarded<R> {
    return guarded(read.then(next).then(undefined, onError && ((error: unknown) => settled(onError(error)))));
}

/** A settled value, for a branch of a guarded read that makes no request at all. */
export function guardedValue<T>(value: Settled<T>): Guarded<T> {
    return guarded(new Promise<T>((resolve) => resolve(settled(value))));
}

const abortControllers = new Map<string, AbortController>();

/**
 * One read per `key`: a newer read with the same key cancels the older one, body included. The
 * caller's signal cancels it as well, and the timeout also covers the body.
 */
export function fetchWithAbort<T>(
    key: string | null,
    url: string,
    options: GuardedFetchOptions
): Guarded<T> {
    if (key && abortControllers.has(key)) {
        abortControllers.get(key)!.abort();
        abortControllers.delete(key);
    }

    let controller: AbortController | undefined;
    if (key) {
        controller = new AbortController();
        abortControllers.set(key, controller);
    }

    // With a key, the caller's signal is forwarded to the key's controller, so either one cancels.
    const callerSignal = options.signal ?? undefined;
    const abortFromCaller = (): void => controller?.abort(callerSignal?.reason);
    if (controller && callerSignal) {
        if (callerSignal.aborted) abortFromCaller();
        else callerSignal.addEventListener('abort', abortFromCaller, { once: true });
    }

    const release = (): void => {
        callerSignal?.removeEventListener('abort', abortFromCaller);
        if (key && abortControllers.get(key) === controller) {
            abortControllers.delete(key);
        }
    };
    return guarded(
        guardedRequest(url, withDeadline({ ...options, signal: controller?.signal ?? callerSignal }), (response) => handleResponse<T>(response)).then(
            (value) => {
                release();
                return value;
            },
            (error: unknown) => {
                release();
                if (error instanceof Error && error.name === 'AbortError') {
                    console.debug(`Request cancelled: ${key || url}`);
                }
                throw error;
            }
        )
    );
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
