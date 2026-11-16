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
        expect(appSource).toContain('void reconcileReclassificationsOnce();');
        expect(appSource).toContain('if (!document.hidden && authStore.statusHealthy)');
        expect(appSource).toContain('if (authStore.statusHealthy) {\n              const accessAdjustedPath');
    });

    it('does not let operational polling subscribe to the reactive job state it updates', () => {
        expect(appSource).toContain("import { onMount, untrack } from 'svelte';");
        expect(appSource).toContain('return untrack(startOperationalPolling);');
        expect(appSource).toContain('if (!document.hidden) void authStore.loadStatus();');
    });

    it('replaces live state whenever the authenticated session identity changes', () => {
        expect(appSource).toContain('let activeAccessIdentity: string | null = null;');
        expect(appSource).toContain('const accessIdentity = `${authStore.isAuthenticated ? \'owner\' : \'guest\'}:${authStore.token ?? \'anonymous\'}`;');
        expect(appSource).toContain('if (!appInitialized || activeAccessIdentity !== accessIdentity)');
        expect(appSource).toContain('closeLiveConnection();');
        expect(appSource).toContain('settingsStore.clear();');
        expect(appSource).toContain('untrack(() => detectionsStore.resetForAccessChange());');
        // Owner status never outlives the session that read it.
        expect(appSource.match(/untrack\(\(\) => systemStatusStore\.clear\(\)\)/g)?.length).toBe(2);
        expect(appSource.match(/untrack\(\(\) => serverJobsStore\.clear\(\)\)/g)?.length).toBe(2);
        expect(appSource).toContain("{#key `${authStore.isAuthenticated ? 'owner' : 'guest'}:${authStore.token ?? 'anonymous'}`}");
    });

    it('takes the owner status from one pushed snapshot instead of polling each part of it', () => {
        expect(appSource).toContain('systemStatusStore.subscribe((snapshot, previous) => {');
        expect(appSource).toContain('serverJobsStore.ingest(snapshot.jobs);');
        expect(appSource).toContain('analysisQueueStatusStore.ingest(snapshot.analysis);');
        expect(appSource).toContain('serviceConnectionsStore.ingest(snapshot.connections);');
        expect(appSource).toContain('liveUpdates.applySystemStatus(snapshot, previous);');
        // Nothing in the shell reads the status parts on a timer any more.
        expect(appSource).not.toContain('ANALYSIS_QUEUE_IDLE_POLL_MS');
        expect(appSource).not.toContain('ownerSystemChecks');
        expect(appSource).not.toContain('refreshOwnerConnections');
    });

    it('reads the status once a minute only while the live stream is down', () => {
        expect(appSource).toContain('systemStatusStore.setStreamLive(authStore.showSettings);');
        expect(appSource).toContain('systemStatusStore.setStreamLive(false);');
    });
});
