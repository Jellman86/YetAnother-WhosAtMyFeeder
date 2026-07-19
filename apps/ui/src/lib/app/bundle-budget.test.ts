import { describe, expect, it } from 'vitest';

import viteConfigSource from '../../../vite.config.ts?raw';

describe('frontend performance budget', () => {
    it('fails production builds if the complete initial import graph becomes monolithic again', () => {
        expect(viteConfigSource).toContain('const INITIAL_JAVASCRIPT_BUDGET_BYTES = 500 * 1024;');
        expect(viteConfigSource).toContain('enforceInitialJavaScriptBudget(INITIAL_JAVASCRIPT_BUDGET_BYTES)');
        expect(viteConfigSource).toContain('pending.push(...loadedChunk.imports);');
        expect(viteConfigSource).toContain('initialBytes > maxBytes');
    });
});
