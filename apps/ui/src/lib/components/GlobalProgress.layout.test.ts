import { describe, expect, it } from 'vitest';
import appSource from '../../App.svelte?raw';
import bannerSource from './GlobalProgress.svelte?raw';
import headerSource from './Header.svelte?raw';
import mobileTopBarSource from './MobileTopBar.svelte?raw';

describe('Global progress layout', () => {
    it('uses the shared app chrome height contract and only enables sticky positioning after scroll begins', () => {
        expect(appSource).toContain('--app-chrome-height: 4rem;');
        expect(appSource).toContain('window.scrollY > 0');
        expect(appSource).toContain("? 'sticky top-[var(--app-chrome-height)] z-30 shrink-0'");
        expect(appSource).toContain(": 'relative z-30 shrink-0 mb-2'");
        expect(appSource).toContain('<GlobalProgress onNavigate={navigate} />');
        expect(headerSource).toContain('h-[var(--app-chrome-height,4rem)]');
        expect(mobileTopBarSource).toContain('h-[var(--app-chrome-height,4rem)]');
    });

    it('caps expanded details height and limits hover expansion to hover-capable pointers', () => {
        expect(bannerSource).toContain('max-h-[40vh] overflow-auto');
        expect(bannerSource).toContain("(hover: hover) and (pointer: fine)");
    });
});
