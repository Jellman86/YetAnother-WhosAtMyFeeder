import { describe, expect, it } from 'vitest';
import appSource from './App.svelte?raw';

describe('App auth status failure handling', () => {
    it('does not require login unless auth status is healthy', () => {
        expect(appSource).toContain('let requiresLogin = $derived(');
        expect(appSource).toContain('authStore.statusHealthy && (');
    });

    it('renders a backend-unavailable state before the login view', () => {
        expect(appSource).toContain('{:else if !authStore.statusHealthy}');
        expect(appSource).toContain('<BackendStatusScreen');
        expect(appSource).toContain("mode=\"unavailable\"");
        expect(appSource).toContain('retrying={authStore.statusLoading}');
        expect(appSource).toContain('onRetry={() => authStore.loadStatus()}');
    });

    it('retries status automatically without starting operational polling while offline', () => {
        expect(appSource).toContain('const BACKEND_STATUS_RETRY_MS = 5_000;');
        expect(appSource).toContain('if (!authStore.statusLoaded || authStore.statusHealthy) return;');
        expect(appSource).toContain('if (!document.hidden) void authStore.loadStatus();');
        expect(appSource).toContain('if (!authStore.statusLoaded || !authStore.statusHealthy) return;');
        expect(appSource).toContain('void runOwnerSystemChecksOnce();');
        expect(appSource).toContain('if (!document.hidden && authStore.statusHealthy)');
        expect(appSource).toContain('if (authStore.statusHealthy) {\n              const accessAdjustedPath');
    });

    it('does not let operational polling subscribe to the reactive job state it updates', () => {
        expect(appSource).toContain("import { onMount, untrack } from 'svelte';");
        expect(appSource).toContain('return untrack(startOperationalPolling);');
        expect(appSource).toContain('const syncAnalysisQueueStatusOnce = createCooldownSingleFlightRunner');
        expect(appSource).toContain('const runOwnerSystemChecksOnce = createCooldownSingleFlightRunner');
        expect(appSource).toContain('if (!document.hidden) void authStore.loadStatus();');
    });

    it('rate-limits authenticated polling even if its lifecycle is retriggered', () => {
        expect(appSource).toContain('createCooldownSingleFlightRunner');
        expect(appSource).toContain('ANALYSIS_QUEUE_POLL_COOLDOWN_MS');
        expect(appSource).toContain('OWNER_SYSTEM_CHECK_COOLDOWN_MS');
    });

    it('replaces live state whenever the authenticated session identity changes', () => {
        expect(appSource).toContain('let activeAccessIdentity: string | null = null;');
        expect(appSource).toContain('const accessIdentity = `${authStore.isAuthenticated ? \'owner\' : \'guest\'}:${authStore.token ?? \'anonymous\'}`;');
        expect(appSource).toContain('if (!appInitialized || activeAccessIdentity !== accessIdentity)');
        expect(appSource).toContain('closeLiveConnection();');
        expect(appSource).toContain('settingsStore.clear();');
    });

    it('uses one adaptive analysis polling path and pauses network work in hidden tabs', () => {
        expect(appSource).toContain('const ANALYSIS_QUEUE_IDLE_POLL_MS = 30_000;');
        expect(appSource).toContain('analysisQueueStatusStore.ingest(status);');
        expect(appSource).toContain('document.hidden ? ANALYSIS_QUEUE_IDLE_POLL_MS');
        expect(appSource).not.toContain('const analysisInterval = window.setInterval');
    });
});
