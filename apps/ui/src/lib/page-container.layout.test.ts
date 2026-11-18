// @ts-expect-error -- node:fs resolves at runtime, not in the app tsconfig
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import appSource from '../App.svelte?raw';
import footerSource from './components/Footer.svelte?raw';

const appCss: string = readFileSync(new URL('../app.css', import.meta.url), 'utf8');

describe('the page container', () => {
    it('lets a page use the width up to a desktop, then centres it with growing gutters', () => {
        // One container for every page and the footer under it, so their edges line up at 2560 px.
        expect(appCss).toContain('--container-shell: 104rem;');
        expect(appSource).toMatch(/<main id="main-content" class="[^"]*\bmx-auto\b[^"]*\bmax-w-shell\b/);
        expect(footerSource).toMatch(/<div class="mx-auto flex max-w-shell /);
    });
});
