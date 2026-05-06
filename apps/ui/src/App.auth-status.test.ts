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

    it('uses valid themed classes for the backend-unavailable error surface', () => {
        expect(appSource).not.toContain('bg-surface-50');
        expect(appSource).not.toContain('dark:bg-surface-900');
        expect(appSource).toContain('role="alert"');
        expect(appSource).toContain('dark:bg-slate-900/95');
        expect(appSource).toContain('dark:text-amber-100');
    });
});
