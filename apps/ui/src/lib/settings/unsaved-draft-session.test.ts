import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// The session token the mocked sign-in hands out. It must never reach a kept draft.
const TOKEN = 'tok-SECRET-session-credential-7f3a';

const api = vi.hoisted(() => ({
    token: null as string | null,
    status: { auth_required: true, is_authenticated: false, username: null as string | null }
}));

vi.mock('../api', () => ({
    createSessionCookie: vi.fn(async () => undefined),
    fetchAuthStatus: vi.fn(async () => ({ ...api.status, public_access_enabled: false })),
    getAuthToken: vi.fn(() => api.token),
    setAuthToken: vi.fn((token: string | null) => { api.token = token; }),
    login: vi.fn(async () => {
        api.token = TOKEN;
        api.status = { auth_required: true, is_authenticated: true, username: 'owner' };
    }),
    logout: vi.fn(async () => {
        api.token = null;
        api.status = { auth_required: true, is_authenticated: false, username: null };
    }),
    setInitialPassword: vi.fn(async () => undefined)
}));

const { authStore } = await import('../stores/auth.svelte');
const { currentAccessIdentity, draftFromForm, unsavedDraft } = await import('./unsaved-draft');

const saved = { mqtt_server: 'mqtt', mqtt_password: '***REDACTED***' };

function keepAnEdit(): void {
    unsavedDraft.keep(draftFromForm({ mqtt_server: 'broker.lan', mqtt_password: 'typed' }, saved, ['mqtt_server', 'mqtt_password'], currentAccessIdentity()));
}

describe('a kept draft and the signed-in session', () => {
    beforeEach(async () => {
        await authStore.login('owner', 'correct horse');
        keepAnEdit();
        expect(unsavedDraft.pendingFor(currentAccessIdentity())).toBe(true);
    });

    afterEach(() => unsavedDraft.clear());

    it('never holds the session token, or anything made from it, for a signed-in owner', () => {
        expect(authStore.token).toBe(TOKEN);
        const held = JSON.stringify(unsavedDraft) + JSON.stringify(currentAccessIdentity());
        expect(held).toContain('broker.lan');
        expect(held).not.toContain(TOKEN);
        expect(held).not.toContain('SECRET');
        expect(held).not.toContain('typed');
    });

    it('is cleared the moment the owner signs out, before Settings is visited again', async () => {
        await authStore.logout();
        expect(JSON.stringify(unsavedDraft)).not.toContain('broker.lan');
        await authStore.login('owner', 'correct horse');
        expect(unsavedDraft.take(currentAccessIdentity())).toBeNull();
    });

    it('is cleared when the session expires and a status check finds nobody signed in', async () => {
        api.token = null;
        api.status = { auth_required: true, is_authenticated: false, username: null };
        await authStore.loadStatus();
        expect(JSON.stringify(unsavedDraft)).not.toContain('broker.lan');
    });

    it('survives a routine status refresh of the same session', async () => {
        await authStore.loadStatus();
        await authStore.loadStatus();
        expect(unsavedDraft.take(currentAccessIdentity())?.values).toEqual({ mqtt_server: 'broker.lan' });
    });
});
