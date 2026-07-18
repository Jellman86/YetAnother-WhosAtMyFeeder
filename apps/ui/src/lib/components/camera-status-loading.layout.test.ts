import { describe, expect, it } from 'vitest';
import cameraStatusSource from './CameraStatus.svelte?raw';

describe('Camera status background loading', () => {
    it('loads frames only while the camera popover is open', () => {
        expect(cameraStatusSource).toContain('await loadCameras();');
        expect(cameraStatusSource).not.toContain('await refreshAll();\n        // Refresh frames every 15s while the page is open');
        expect(cameraStatusSource).toContain('if (popoverOpen) return;');
        expect(cameraStatusSource).toContain('startFrameRefresh();');
        expect(cameraStatusSource).toContain('stopFrameRefresh();');
    });

    it('uses the shared API client instead of an inline fetch', () => {
        expect(cameraStatusSource).toContain('fetchLatestCameraSnapshot');
        expect(cameraStatusSource).not.toContain('fetch(`${appApiPath(');
    });
});
