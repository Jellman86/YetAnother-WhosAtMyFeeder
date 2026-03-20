import { describe, expect, it } from 'vitest';
import appSource from './App.svelte?raw';

describe('App dashboard navigation refresh', () => {
    it('bumps a dashboard refresh key when navigating to the dashboard route that is already active', () => {
        expect(appSource).toContain('let dashboardRefreshKey = $state(0);');
        expect(appSource).toContain("const isDashboardRefresh = targetPath === '/' && currentRoute === '/' && !opts.replace;");
        expect(appSource).toContain('if (isDashboardRefresh) {');
        expect(appSource).toContain('dashboardRefreshKey += 1;');
    });

    it('keys the dashboard component by that refresh counter', () => {
        expect(appSource).toContain('{#key dashboardRefreshKey}');
        expect(appSource).toContain('<Dashboard onnavigate={navigate} />');
    });
});
