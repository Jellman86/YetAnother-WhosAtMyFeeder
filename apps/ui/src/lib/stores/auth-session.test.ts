import { describe, expect, it } from 'vitest';
import { isNewSession, type SessionFacts } from './auth-session';

const owner: SessionFacts = { authRequired: true, isAuthenticated: true, username: 'owner', hasOwnerAccess: true, hasToken: true };

describe('whether the person using the app has changed', () => {
    it('is the same session when a status refresh reports the same facts', () => {
        expect(isNewSession(owner, { ...owner })).toBe(false);
    });

    it('is a new session after signing out, an expired token, or another person signing in', () => {
        expect(isNewSession(owner, { ...owner, isAuthenticated: false, hasOwnerAccess: false, username: null, hasToken: false })).toBe(true);
        expect(isNewSession(owner, { ...owner, hasToken: false })).toBe(true);
        expect(isNewSession(owner, { ...owner, username: 'neighbour' })).toBe(true);
    });

    it('is a new session when owner access becomes guest access or sign-in is switched on', () => {
        expect(isNewSession(owner, { ...owner, hasOwnerAccess: false })).toBe(true);
        const open: SessionFacts = { authRequired: false, isAuthenticated: false, username: null, hasOwnerAccess: true, hasToken: false };
        expect(isNewSession(open, { ...open, authRequired: true, hasOwnerAccess: false })).toBe(true);
    });
});
