import { describe, expect, it } from 'vitest';
import appSource from '../../App.svelte?raw';
import connectionStatusSource from './ConnectionStatus.svelte?raw';
import sidebarSource from './Sidebar.svelte?raw';

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
        expect(appSource).toContain('variant="sidebar"');
        expect(sidebarSource).toContain('data-sidebar-status');
        expect(connectionStatusSource).toContain("variant?: 'compact' | 'sidebar'");
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
});
