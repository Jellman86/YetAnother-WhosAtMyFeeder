import { describe, expect, it } from 'vitest';
import authStoreSource from './auth.svelte.ts?raw';

describe('authStore owner access contract', () => {
    it('defines owner access as status-loaded and successfully fetched auth state', () => {
        expect(authStoreSource).toContain('statusHealthy = $state(false);');
        expect(authStoreSource).toContain('hasOwnerAccess = $derived(this.statusLoaded && this.statusHealthy && (this.isAuthenticated || !this.authRequired));');
        expect(authStoreSource).toContain('canModify = $derived(this.hasOwnerAccess);');
        expect(authStoreSource).toContain('showSettings = $derived(this.hasOwnerAccess);');
    });

    it('fails closed when auth status cannot be loaded', () => {
        expect(authStoreSource).toContain("this.authRequired = true;");
        expect(authStoreSource).toContain("this.publicAccessEnabled = false;");
        expect(authStoreSource).toContain("this.isAuthenticated = false;");
        expect(authStoreSource).toContain("this.statusHealthy = false;");
        expect(authStoreSource).toContain('// Fail closed on auth-status errors so owner-only UI never leaks.');
    });

    it('keeps guest access dependent on loaded healthy auth state', () => {
        expect(authStoreSource).toContain('isGuest = $derived(this.statusLoaded && this.statusHealthy && this.authRequired && !this.isAuthenticated && this.publicAccessEnabled);');
        expect(authStoreSource).toContain('canViewAiConversation = $derived(this.hasOwnerAccess || (this.isGuest && this.publicAccessShowAiConversation));');
    });
});
