import { describe, expect, it } from 'vitest';
import appSource from '../../App.svelte?raw';
import connectionStatusSource from './ConnectionStatus.svelte?raw';
import statusMappingSource from '../utils/system-status.ts?raw';
import sidebarSource from './Sidebar.svelte?raw';
import loadMetersSource from './SystemLoadMeters.svelte?raw';

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
        // The window's height still hides the icon rail's status, which has no readings to measure; the
        // labelled card is measured against the room the column really has (see below).
        expect(sidebarSource).toContain("{collapsed ? '[@media(max-height:42rem)]:hidden' : ''}");
        expect(sidebarSource).toContain('[@media(max-height:42rem)]:py-3');
        // On a short window the brand sits beside its mark, the status readings give way inside the card
        // with the Health link pinned at its foot, the card gives way entirely where not even that fits,
        // and only when the places themselves do not fit do the places and the status scroll together.
        // The controls below never scroll, so the language menu is never clipped.
        expect(sidebarSource).toContain('<div class="flex min-h-0 flex-1 flex-col overflow-y-auto" data-sidebar-scroll>');
        expect(sidebarSource).toContain('<nav class="shrink-0 px-3 py-4"');
        expect(sidebarSource).toContain('data-sidebar-status class="mt-auto flex flex-col');
        expect(sidebarSource).toMatch(/class="focus-ring"\s+role="group"\s+tabindex="0"\s+aria-labelledby="sidebar-status-title"\s+data-sidebar-status-readings/);
        // No box of the card may shrink below its content: the readings' height is set in whole lines,
        // and a card with no room for its floor is taken out of view rather than squashed.
        expect(sidebarSource).not.toMatch(/\[data-sidebar-status(?:-card)?\][^{]*\{[^}]*min-height: 0/);
        expect(sidebarSource).toMatch(/\[data-sidebar-status-readings\] \{\s*overflow-y: auto;/);
        expect(sidebarSource).toMatch(/\[data-sidebar-status\]:global\(\[data-whole-lines='none'\]\) \{[^}]*position: absolute;[^}]*bottom: 100%;[^}]*visibility: hidden;/);
        expect(sidebarSource).toContain('flex min-h-7 shrink-0 items-center justify-between');
        expect(sidebarSource.indexOf('data-sidebar-scroll')).toBeLessThan(sidebarSource.indexOf('<LanguageSelector'));
        // An owner with sign-in off has no account to show, so no empty band.
        expect(sidebarSource).toMatch(/\{#if authStore\.isAuthenticated \|\| authStore\.isGuest\}\s*<div class="shrink-0 border-t border-line-soft p-3" data-sidebar-account-band>/);
    });

    it('shows the load as labelled meters in the card, on a neutral surface', () => {
        expect(sidebarSource).toContain("import SystemLoadMeters from './SystemLoadMeters.svelte'");
        expect(sidebarSource).toContain('<SystemLoadMeters />');
        // The readings are text in the card's own flow: nothing is drawn behind the rows, and
        // nothing is positioned over them, so the rows and the link can grow or wrap freely.
        expect(loadMetersSource).not.toContain('absolute');
        expect(loadMetersSource).not.toContain('use:portal');
        expect(loadMetersSource).toContain('tabular-nums');
        expect(loadMetersSource).toContain('min-h-4');
        // Each meter is named in words and says its figure; the bar wears the Health chart's series
        // colour as a fill, never as text, and never a link or status colour.
        expect(loadMetersSource).toContain('<dt class="text-muted">{meter.label}</dt>');
        expect(loadMetersSource).toContain('{meter.shown}');
        expect(loadMetersSource).toContain('{meter.fill}');
        expect(loadMetersSource).not.toMatch(/text-(?:brand|indigo|accent|status|series)-|bg-status-/);
        const card = sidebarSource.slice(sidebarSource.indexOf('data-sidebar-status class'));
        expect(card).not.toMatch(/bg-gradient|bg-linear|from-|overflow-hidden/);
    });

    it('samples telemetry only while the status card is actually visible', () => {
        expect(loadMetersSource).toContain('IntersectionObserver');
        expect(loadMetersSource).toContain('return inViewport && !document.hidden;');
        expect(loadMetersSource).toContain('history = []');
        expect(loadMetersSource).not.toContain('setInterval');
    });

    it('paces telemetry to the visitor budget and keeps a failed reading marked as not current', () => {
        expect(loadMetersSource).toContain('telemetrySampleDelayMs({');
        expect(loadMetersSource).toContain('guest: authStore.isGuest');
        expect(loadMetersSource).toContain('cap: authStore.publicAccessRateLimitPerMinute');
        const failure = loadMetersSource.slice(loadMetersSource.indexOf('} catch {'), loadMetersSource.indexOf('} finally {'));
        expect(failure).toContain('stale = history.length > 0;');
        expect(failure).not.toContain('history = []');
        expect(loadMetersSource).toContain("system_telemetry.last_reading");
    });

    it('shows the status readings in whole lines at rest, instead of cutting a line of words', () => {
        // Never fewer than the heading and the first reading.
        expect(sidebarSource).toContain("use:snapToWholeLines={{ lines: ':scope > *, li', floor: '[data-status-row]', container: '[data-sidebar-scroll]' }}");
        // Nothing is drawn over the readings: a mask on them, a tab stop, clipped their focus ring, and a fade
        // or an edge over a line reads as cut or underlined text.
        expect(sidebarSource).not.toContain('mask-image');
        expect(sidebarSource).not.toContain('[data-sidebar-status-readings]::after');
    });

    it('lets a wrapped status state start under its label, not right-aligned under nothing', () => {
        // Beside its label, justify-between keeps it at the right edge; alone on its line, at the start
        // (status-feed.spec.ts measures both).
        expect(connectionStatusSource).toContain('flex min-w-0 flex-wrap items-baseline justify-between');
        expect(connectionStatusSource).not.toContain('ml-auto text-right');
    });

    it('says a failed sample\'s figures are old before they are read, and mutes them', () => {
        expect(loadMetersSource.indexOf('data-telemetry-last-reading')).toBeLessThan(loadMetersSource.indexOf('data-telemetry-readout'));
        expect(loadMetersSource).toContain("stale || !meter.measured ? 'text-muted' : 'text-ink'");
    });

    it('sets the rows in one weight, and only a state that needs a person apart', () => {
        expect(connectionStatusSource).toContain("row.tone === 'attention' ? 'font-semibold text-status-attention' : 'text-ink'");
        // The way to Health is the card's foot: its own words, at the start of the row, in body ink.
        const link = sidebarSource.slice(sidebarSource.indexOf('data-sidebar-status-link\n                            data-health-attention'));
        expect(sidebarSource).toMatch(/flex min-h-7 shrink-0 items-center justify-between gap-x-2 rounded-md border-t border-line-soft px-1 pt-2 text-xs leading-4 text-ink/);
        expect(link).toContain("<span>{$_('status.open_health', { default: 'Health' })}</span>");
        expect(link).not.toContain('ml-auto');
    });
});
