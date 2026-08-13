import { describe, expect, it } from 'vitest';

import detectionModalSource from './DetectionModal.svelte?raw';
import toastSource from './Toast.svelte?raw';

describe('mobile overlay clearance', () => {
    it('keeps the manual species picker inside the visible viewport', () => {
        expect(detectionModalSource).toContain("import { intersectVisibleViewport }");
        expect(detectionModalSource).toContain("visualViewport?.addEventListener('resize'");
        expect(detectionModalSource).toContain("visualViewport?.addEventListener('scroll'");
        expect(detectionModalSource).toContain('style={manualTagViewportStyle}');
        expect(detectionModalSource).toContain('data-manual-tag-dialog');
        expect(detectionModalSource).toContain('aria-modal="true"');
        expect(detectionModalSource).toContain('max-h-full');
        expect(detectionModalSource).toContain('text-base sm:text-sm');
    });

    it('anchors the detection close action outside the scrollable content region', () => {
        const closeActionIndex = detectionModalSource.indexOf('data-detection-modal-close');
        const scrollableContentIndex = detectionModalSource.indexOf('class="flex-1 overflow-hidden flex flex-col');

        expect(closeActionIndex).toBeGreaterThan(-1);
        expect(scrollableContentIndex).toBeGreaterThan(-1);
        expect(closeActionIndex).toBeLessThan(scrollableContentIndex);
    });

    it('places phone toasts below the modal controls and within safe-area gutters', () => {
        expect(toastSource).toContain('data-toast-container');
        expect(toastSource).toContain('class="toast-container');
        expect(toastSource).toContain('env(safe-area-inset-top, 0px)');
        expect(toastSource).toContain('top: 1rem;');
        expect(toastSource).toContain('aria-live="polite"');
        expect(toastSource).toContain('aria-atomic="true"');
        expect(toastSource).toContain('bg-accent-700 border-accent-800');
        expect(toastSource).not.toContain('bg-accent-500 border-accent-600');
    });
});
