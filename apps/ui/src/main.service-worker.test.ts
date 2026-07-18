import { describe, expect, it } from 'vitest';
import mainSource from './main.ts?raw';

describe('service worker deployment updates', () => {
    it('keys service-worker registration to the exact frontend build', () => {
        expect(mainSource).toContain("encodeURIComponent(__APP_VERSION__)");
        expect(mainSource).toContain("navigator.serviceWorker.register(`/sw.js?v=${serviceWorkerBuild}`");
        expect(mainSource).toContain("updateViaCache: 'none'");
        expect(mainSource).toContain('await registration.update()');
    });
});
