import { describe, expect, it } from 'vitest';
import appSource from '../../App.svelte?raw';
import settingsPageSource from '../pages/Settings.svelte?raw';
import appearanceSettingsSource from './settings/AppearanceSettings.svelte?raw';
import bannerSource from './GlobalProgress.svelte?raw';
import headerSource from './Header.svelte?raw';
import mobileTopBarSource from './MobileTopBar.svelte?raw';

describe('Global progress layout', () => {
    it('uses the shared app chrome height contract in the single sidebar layout and only enables sticky positioning after scroll begins', () => {
        expect(appSource).toContain('--app-chrome-height');
        expect(appSource).toContain("style=\"--app-chrome-height: {isMobile ? '4rem' : '0rem'};\"");
        expect(appSource).toContain('window.scrollY > 0');
        expect(appSource).toContain("? 'sticky top-[var(--app-chrome-height)] z-30 shrink-0'");
        expect(appSource).toContain(": 'relative z-30 shrink-0 mb-2'");
        expect(appSource).toContain('<GlobalProgress onNavigate={navigate} />');
        expect(appSource).toContain('<Sidebar {currentRoute} onNavigate={navigate} {mobileSidebarOpen} onMobileClose={() => mobileSidebarOpen = false}>');
        expect(appSource).not.toContain("effectiveLayout === 'horizontal'");
        expect(mobileTopBarSource).toContain('h-[var(--app-chrome-height,4rem)]');
    });

    it('caps expanded details height and limits hover expansion to hover-capable pointers', () => {
        expect(bannerSource).toContain('max-h-[40vh] overflow-auto');
        expect(bannerSource).toContain("(hover: hover) and (pointer: fine)");
    });

    it('removes desktop header route tabs and the appearance layout picker', () => {
        expect(headerSource).not.toContain('<!-- Desktop Navigation -->');
        expect(headerSource).not.toContain('class="hidden md:flex items-center gap-1"');
        expect(appearanceSettingsSource).not.toContain("{$_('theme.layout')}");
        expect(appearanceSettingsSource).not.toContain("setLayout(");
        expect(settingsPageSource).not.toContain('let currentLayout');
        expect(settingsPageSource).not.toContain('function setLayout');
    });
});
