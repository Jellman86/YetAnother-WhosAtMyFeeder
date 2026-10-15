import { describe, expect, it } from 'vitest';
import source from './GardenPhotoCheckDialog.svelte?raw';

describe('Garden advisory photo check presentation', () => {
    it('uses the shared accessible diagnostic dialog with an advisory result', () => {
        expect(source).toContain('<DiagnosticDialog');
        expect(source).toContain("state: busy ? 'running' : error ? 'failed' : 'warning'");
        expect(source).toContain('This photo only');
        expect(source).toContain('data-garden-check-input');
    });
});
