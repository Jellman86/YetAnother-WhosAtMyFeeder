import { describe, expect, it } from 'vitest';
import appSource from '../../App.svelte?raw';
import bannerSource from './GlobalProgress.svelte?raw';

describe('Global progress layout', () => {
    it('renders the global progress banner inside a sticky app-shell wrapper', () => {
        expect(appSource).toContain('class="sticky top-0 z-30 shrink-0"');
        expect(appSource).toContain('<GlobalProgress onNavigate={navigate} />');
    });

    it('caps expanded details height so a sticky banner does not consume the viewport', () => {
        expect(bannerSource).toContain('max-h-[40vh] overflow-auto');
    });
});
