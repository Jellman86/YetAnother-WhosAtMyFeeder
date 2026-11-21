import { ApiRequestError } from '../api/core';

/** Why a sign-in did not go through, as far as the person signing in can act on it. */
export type SignInFailure = 'wrong_credentials' | 'rate_limited' | 'unreachable' | 'server';

/**
 * Sort a failed sign-in by what the person should do next. The server's own wording
 * ("Invalid credentials") names a category, not a cause or a remedy, so it is never shown.
 */
export function signInFailure(error: unknown): SignInFailure {
    if (error instanceof ApiRequestError) {
        if (error.status === 401) return 'wrong_credentials';
        if (error.status === 429) return 'rate_limited';
        return 'server';
    }
    // fetch rejects with a TypeError when no answer came back at all.
    return error instanceof TypeError ? 'unreachable' : 'server';
}
