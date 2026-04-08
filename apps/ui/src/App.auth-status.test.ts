import { describe, expect, it } from 'vitest';
import appSource from './App.svelte?raw';

describe('App auth status failure handling', () => {
    it('does not require login unless auth status is healthy', () => {
        expect(appSource).toContain('let requiresLogin = $derived(');
        expect(appSource).toContain('authStore.statusHealthy && (');
    });

    it('renders a backend-unavailable state before the login view', () => {
        expect(appSource).toContain('{:else if !authStore.statusHealthy}');
        expect(appSource).toContain("Unable to reach the YA-WAMF backend.");
        expect(appSource).toContain("If the container is still starting or restarting after model changes, wait a moment and retry.");
        expect(appSource).toContain("onclick={() => void authStore.loadStatus()}");
    });
});
