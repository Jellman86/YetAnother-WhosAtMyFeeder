/**
 * What the app knows about who is using it, without any credential: the token itself is reduced
 * to whether one is held, so nothing built from these facts can carry it.
 */
export interface SessionFacts {
    authRequired: boolean;
    isAuthenticated: boolean;
    username: string | null;
    hasOwnerAccess: boolean;
    hasToken: boolean;
}

/**
 * Whether a status check describes a different session from the last one: someone signed out or
 * in, a token expired, another person is signed in, or owner access came or went. A refresh
 * that reports the same facts is the same session.
 */
export function isNewSession(before: SessionFacts, after: SessionFacts): boolean {
    return before.authRequired !== after.authRequired
        || before.isAuthenticated !== after.isAuthenticated
        || before.username !== after.username
        || before.hasOwnerAccess !== after.hasOwnerAccess
        || before.hasToken !== after.hasToken;
}
