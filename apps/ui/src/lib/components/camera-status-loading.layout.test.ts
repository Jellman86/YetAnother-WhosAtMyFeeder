import { describe, expect, it } from 'vitest';
import cameraStatusSource from './CameraStatus.svelte?raw';

describe('Camera status health and viewer behavior', () => {
    it('follows camera health from the pushed status, independently from selected-camera frames', () => {
        expect(cameraStatusSource).toContain('await loadCameras();');
        expect(cameraStatusSource).toContain('readCameraStatuses');
        expect(cameraStatusSource).toContain('followStatus();');
        expect(cameraStatusSource).toContain('systemStatusStore.subscribe(applyStatus)');
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

    it('polls no health and holds no timer while idle; only the open viewer refreshes its frame', () => {
        // startVisiblePoll cancels its timer when the tab is hidden and reads again when it is shown
        // (see app/visible-poll.test.ts); a hand-rolled interval keeps firing in a hidden tab.
        expect(cameraStatusSource).toContain("import { startVisiblePoll } from '../app/visible-poll';");
        expect(cameraStatusSource).not.toMatch(/startVisiblePoll\(\{\s*read: refreshHealth,/);
        expect(cameraStatusSource).toMatch(/startVisiblePoll\(\{ read: refreshSelectedFrame,/);
        expect(cameraStatusSource).not.toContain('setInterval');
    });

    it('starts no poll once destroyed, even when the mount bootstrap ends afterwards', () => {
        expect(cameraStatusSource).toMatch(/onDestroy\(\(\) => \{\s*destroyed = true;/);
        expect(cameraStatusSource).toMatch(/function followStatus\(\): void \{\s*if \(destroyed\) return;/);
        expect(cameraStatusSource).toMatch(/function startFrameRefresh\(\): void \{\s*if \(destroyed\) return;/);
    });

    it('uses the shared API client instead of an inline fetch', () => {
        expect(cameraStatusSource).toContain('fetchLatestCameraSnapshot');
        expect(cameraStatusSource).toContain('readCameraStatuses');
        expect(cameraStatusSource).not.toContain('fetch(`${appApiPath(');
    });
});
