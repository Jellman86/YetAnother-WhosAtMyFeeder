import { describe, expect, it } from 'vitest';
import appSource from '../App.svelte?raw';
import dashboardSource from './pages/Dashboard.svelte?raw';
import eventsSource from './pages/Events.svelte?raw';
import healthSource from './pages/Errors.svelte?raw';

describe('status the shell only claims once measured', () => {
    it('feeds the live tile and the day bar from the page stream and the measured connections', () => {
        expect(appSource).toContain('feed={liveFeedState(detectionsStore.connected, serviceConnectionsStore.connections)}');
        expect(dashboardSource).toContain('feed={liveFeedState(detectionsStore.connected, serviceConnectionsStore.connections)}');
    });

    it('reads the connections for owners only, and forgets them when access changes', () => {
        expect(appSource).toContain('if (authStore.showSettings) void serviceConnectionsStore.refresh();');
        expect(appSource).toContain('onServiceConnectionsChanged: () => refreshOwnerConnections()');
        expect(appSource.match(/serviceConnectionsStore\.clear\(\)/g)?.length).toBe(2);
    });

    it('bases the Health verdict on the connections the workspace measured', () => {
        expect(healthSource).toContain('healthVerdict(overallStatus(), connections)');
        expect(healthSource).toContain('data-health-card="frigate"');
        expect(healthSource).not.toContain("'No recent workspace snapshot yet.'");
    });

    it('makes every owner Explorer read wait for a successful settings read', () => {
        const load = eventsSource.indexOf('async function loadEvents()');
        // The settings store decides whether settings are known; the Explorer asks it and stops when they are not.
        const guard = eventsSource.indexOf('const settingsKnown = await settingsStore.read().then(() => true, () => false);', load);
        const firstRequest = eventsSource.indexOf('fetchGardenVisits({', load);
        expect(guard).toBeGreaterThan(load);
        expect(guard).toBeLessThan(firstRequest);
        expect(eventsSource).toContain("events.settings_unavailable");
    });
});
