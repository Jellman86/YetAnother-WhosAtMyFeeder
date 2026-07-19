import { describe, expect, it } from 'vitest';
import cameraStatusSource from './CameraStatus.svelte?raw';

describe('Camera status health and viewer behavior', () => {
    it('polls lightweight health independently from selected-camera frames', () => {
        expect(cameraStatusSource).toContain('await loadCameras();');
        expect(cameraStatusSource).toContain('fetchCameraStatuses');
        expect(cameraStatusSource).toContain('startHealthRefresh(false);');
        expect(cameraStatusSource).toContain('if (!popoverOpen) return;');
        expect(cameraStatusSource).toContain('refreshSelectedFrame');
        expect(cameraStatusSource).not.toContain('refreshAll');
        expect(cameraStatusSource).not.toContain('Promise.all(cameras.map');
    });

    it('opens on click and loops through cameras with accessible controls', () => {
        expect(cameraStatusSource).toContain('if (popoverOpen) return;');
        expect(cameraStatusSource).toContain('startFrameRefresh();');
        expect(cameraStatusSource).toContain('stopFrameRefresh();');
        expect(cameraStatusSource).toContain('(selectedIndex + offset + cameras.length) % cameras.length');
        expect(cameraStatusSource).toContain("event.key === 'ArrowLeft'");
        expect(cameraStatusSource).toContain("event.key === 'ArrowRight'");
        expect(cameraStatusSource).toContain('aria-haspopup="dialog"');
        expect(cameraStatusSource).not.toContain('onmouseenter');
        expect(cameraStatusSource).not.toContain('onmouseleave');
    });

    it('uses the shared API client instead of an inline fetch', () => {
        expect(cameraStatusSource).toContain('fetchLatestCameraSnapshot');
        expect(cameraStatusSource).toContain('fetchCameraStatuses');
        expect(cameraStatusSource).not.toContain('fetch(`${appApiPath(');
    });
});
