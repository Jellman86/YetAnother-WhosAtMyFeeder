import { describe, expect, it } from 'vitest';
import appSource from '../../App.svelte?raw';
import connectionStatusSource from './ConnectionStatus.svelte?raw';
import sidebarSource from './Sidebar.svelte?raw';
import telemetryGraphSource from './SystemTelemetryGraph.svelte?raw';

describe('Sidebar hybrid refresh', () => {
    it('keeps the large brand mark centred above the navigation', () => {
        expect(sidebarSource).toContain('data-sidebar-brand');
        expect(sidebarSource).toContain("sizes={collapsed ? '40px' : '64px'}");
        expect(sidebarSource).toContain("collapsed ? 'h-10 w-10' : 'h-16 w-16'");
        expect(sidebarSource).toContain('items-center text-center');
    });

    it('groups observation and management routes with a stronger active state', () => {
        expect(sidebarSource).toContain("section: 'observe'");
        expect(sidebarSource).toContain("section: 'manage'");
        expect(sidebarSource).toContain("$_('nav.observe')");
        expect(sidebarSource).toContain("$_('nav.manage')");
        expect(sidebarSource).toContain('data-sidebar-section');
        expect(sidebarSource).toContain('sidebar-nav-active');
    });

    it('shows truthful operational status rows in the expanded sidebar', () => {
        expect(sidebarSource).toContain('data-sidebar-status');
        // The unused compact header variant is gone; the sidebar tiles are the only shape.
        expect(connectionStatusSource).not.toContain('variant');
        expect(connectionStatusSource).toContain("$_('status.live_updates')");
        expect(connectionStatusSource).toContain("$_('status.audio_analysis')");
        expect(connectionStatusSource).toContain("$_('status.notifications')");
        expect(connectionStatusSource).toContain("$_('status.online')");
        expect(connectionStatusSource).toContain("$_('status.offline')");
    });

    it('uses an account card when expanded while preserving compact auth actions', () => {
        expect(sidebarSource).toContain('data-sidebar-account');
        expect(sidebarSource).toContain('authStore.username');
        expect(sidebarSource).toContain('accountInitial');
        expect(sidebarSource).toContain("$_('auth.public_view')");
        expect(sidebarSource).toContain("$_('auth.logout')");
        expect(sidebarSource).toContain("$_('auth.login')");
    });

    it('never tells a guest that notifications are off', () => {
        // A guest cannot read the owner's settings, so the Alerts tile is left out, not guessed.
        expect(appSource).toContain('if (!s) return null;');
        expect(connectionStatusSource).toContain('notificationsActive?: boolean | null;');
        expect(connectionStatusSource).toContain('...(notificationsActive === null');
    });

    it('is a wordmark, not a heading, so each page owns its single h1', () => {
        expect(sidebarSource).not.toContain('<h1');
    });

    it('takes the closed phone drawer out of the tab order and makes the open one modal', () => {
        expect(sidebarSource).toContain('id="app-sidebar"');
        expect(sidebarSource).toContain('inert={drawerClosed}');
        expect(sidebarSource).toContain('const release = trapFocus(asideEl);');
        expect(sidebarSource).toContain(`nav [aria-current="page"]`);
        expect(sidebarSource).toContain('<svelte:window onkeydown={handleWindowKeydown} />');
        expect(appSource).toContain('menuOpen={mobileSidebarOpen}');
        expect(appSource).toContain('menuControls="app-sidebar"');
    });

    it('keeps navigation and bottom controls reachable on short viewports', () => {
        expect(sidebarSource).toContain('[@media(max-height:42rem)]:hidden');
        expect(sidebarSource).toContain('[@media(max-height:42rem)]:py-3');
    });

    it('layers a lightweight live telemetry graph behind the status content', () => {
        expect(sidebarSource).toContain("import SystemTelemetryGraph from './SystemTelemetryGraph.svelte'");
        expect(sidebarSource).toContain('<SystemTelemetryGraph readoutClass=');
        // The readout has a row of its own, above the System health link when there is one.
        expect(sidebarSource).toContain('<span class="mt-1 block h-4" aria-hidden="true"></span>');
        expect(sidebarSource).toContain('relative overflow-hidden');
        expect(sidebarSource).toContain('relative z-10');
    });

    it('samples telemetry only while the status card is actually visible', () => {
        expect(telemetryGraphSource).toContain('IntersectionObserver');
        expect(telemetryGraphSource).toContain('return inViewport && !document.hidden;');
        expect(telemetryGraphSource).toContain('history = []');
        expect(telemetryGraphSource).not.toContain('setInterval');
    });

    it('paces telemetry to the visitor budget and keeps a failed reading marked as not current', () => {
        expect(telemetryGraphSource).toContain('telemetrySampleDelayMs({');
        expect(telemetryGraphSource).toContain('guest: authStore.isGuest');
        expect(telemetryGraphSource).toContain('cap: authStore.publicAccessRateLimitPerMinute');
        const failure = telemetryGraphSource.slice(telemetryGraphSource.indexOf('} catch {'), telemetryGraphSource.indexOf('} finally {'));
        expect(failure).toContain('stale = history.length > 0;');
        expect(failure).not.toContain('history = []');
        expect(telemetryGraphSource).toContain("system_telemetry.last_reading");
    });
});
