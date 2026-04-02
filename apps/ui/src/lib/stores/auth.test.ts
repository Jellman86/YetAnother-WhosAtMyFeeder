import { describe, expect, it } from 'vitest';
import authStoreSource from './auth.svelte.ts?raw';

describe('authStore owner access contract', () => {
    it('defines owner access as status-loaded auth success or auth-disabled access', () => {
        expect(authStoreSource).toContain('hasOwnerAccess = $derived(this.statusLoaded && (this.isAuthenticated || !this.authRequired));');
        expect(authStoreSource).toContain('canModify = $derived(this.hasOwnerAccess);');
        expect(authStoreSource).toContain('showSettings = $derived(this.hasOwnerAccess);');
    });

    it('keeps guest access dependent on loaded auth state', () => {
        expect(authStoreSource).toContain('isGuest = $derived(this.statusLoaded && this.authRequired && !this.isAuthenticated && this.publicAccessEnabled);');
        expect(authStoreSource).toContain('canViewAiConversation = $derived(this.hasOwnerAccess || (this.isGuest && this.publicAccessShowAiConversation));');
    });
});
