import { describe, expect, it } from 'vitest';
import appSource from '../../App.svelte?raw';
import connectionStatusSource from './ConnectionStatus.svelte?raw';
import statusMappingSource from '../utils/system-status.ts?raw';
import sidebarSource from './Sidebar.svelte?raw';
import telemetryGraphSource from './SystemTelemetryGraph.svelte?raw';

describe('Sidebar hybrid refresh', () => {
    it('keeps the large brand mark centred above the navigation, and beside its name on a short window', () => {
        expect(sidebarSource).toContain('data-sidebar-brand');
        expect(sidebarSource).toContain("sizes={collapsed ? '40px' : '64px'}");
        expect(sidebarSource).toContain("collapsed ? 'h-10 w-10' : 'h-16 w-16 compact-height:h-10 compact-height:w-10'");
        expect(sidebarSource).toContain('items-center text-center');
        expect(sidebarSource).toContain("{collapsed ? '' : 'compact-height:flex-row compact-height:text-left'}");
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
        // The unused compact header variant is gone; the status list is the only shape.
        expect(connectionStatusSource).not.toContain('variant');
        // The rows and their words come from one tested mapping, never from the markup.
        expect(connectionStatusSource).toContain('[feedRow(feed), audioRow(birdnetEnabled, feed), alertsRow(notificationsActive)]');
        // The Frigate events row says what was measured: the broker session, not only the page's stream.
        expect(statusMappingSource).toContain("text('feed_live'");
        expect(statusMappingSource).toContain("text('feed_broker_down'");
        expect(statusMappingSource).toContain("text('feed_app_only'");
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
        // A guest cannot read the owner's settings, so the Alerts row is left out, not guessed.
        expect(appSource).toContain('if (!s) return null;');
        expect(connectionStatusSource).toContain('notificationsActive?: boolean | null;');
        expect(statusMappingSource).toContain('if (active === null) return null;');
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
        // On a short window the brand sits beside its mark, the status readings give way inside the card
        // with the Health link pinned at its foot, and only past that do the places and the status scroll
        // together. The controls below never scroll, so the language menu is never clipped.
        expect(sidebarSource).toContain('<div class="flex min-h-0 flex-1 flex-col overflow-y-auto" data-sidebar-scroll>');
        expect(sidebarSource).toContain('<nav class="shrink-0 px-3 py-4"');
        expect(sidebarSource).toContain('data-sidebar-status class="mt-auto flex flex-col');
        expect(sidebarSource).toMatch(/class="focus-ring" role="group" tabindex="0" aria-labelledby="sidebar-status-title" data-sidebar-status-readings/);
        // Only at the usual text size (the column at least 30 rem tall) do the readings give way.
        expect(sidebarSource).toContain('container: sidebar-scroll / size;');
        expect(sidebarSource).toMatch(/@container sidebar-scroll \(height >= 30rem\) \{[\s\S]*?\[data-sidebar-status-readings\] \{\s*min-height: 3rem;\s*overflow-y: auto;/);
        expect(sidebarSource).toContain('flex min-h-7 shrink-0 items-center justify-between');
        expect(sidebarSource.indexOf('data-sidebar-scroll')).toBeLessThan(sidebarSource.indexOf('<LanguageSelector'));
        // An owner with sign-in off has no account to show, so no empty band.
        expect(sidebarSource).toMatch(/\{#if authStore\.isAuthenticated \|\| authStore\.isGuest\}\s*<div class="shrink-0 border-t border-line-soft p-3" data-sidebar-account-band>/);
    });

    it('states resource readings as one plain line in the card, on a neutral surface', () => {
        expect(sidebarSource).toContain("import SystemTelemetryGraph from './SystemTelemetryGraph.svelte'");
        expect(sidebarSource).toContain('<SystemTelemetryGraph />');
        // The readings are text in the card's own flow: nothing is drawn behind the rows, and
        // nothing is positioned over them, so the rows and the link can grow or wrap freely.
        expect(telemetryGraphSource).not.toContain('absolute');
        expect(telemetryGraphSource).not.toContain('use:portal');
        expect(telemetryGraphSource).toContain('tabular-nums');
        expect(telemetryGraphSource).toContain('min-h-4');
        // Muted body ink, not link or series colours: a reading is not something to click.
        expect(telemetryGraphSource).not.toMatch(/text-(?:brand|indigo)-/);
        const card = sidebarSource.slice(sidebarSource.indexOf('data-sidebar-status class'));
        expect(card).not.toMatch(/bg-gradient|bg-linear|from-|overflow-hidden/);
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
