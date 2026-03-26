import { describe, expect, it } from 'vitest';
import detectionCardSource from './DetectionCard.svelte?raw';
import eventsPageSource from '../pages/Events.svelte?raw';
import dashboardPageSource from '../pages/Dashboard.svelte?raw';
import mediaApiSource from '../api/media.ts?raw';

describe('detection card full-visit fetch wiring', () => {
    it('threads recording availability and fetch state into the card flow', () => {
        expect(mediaApiSource).toContain('getRecordingClipUrl');
        expect(mediaApiSource).toContain('recording-clip.mp4');
        expect(mediaApiSource).toContain('X-YAWAMF-Recording-Clip-Ready');

        expect(detectionCardSource).toContain('fullVisitAvailable');
        expect(detectionCardSource).toContain('fullVisitFetched');
        expect(detectionCardSource).toContain('fullVisitFetchState');
        expect(detectionCardSource).toContain('onFetchFullVisit');
        expect(detectionCardSource).toContain('Fetch full clip');
        expect(detectionCardSource).toContain('Full visit');
        expect(detectionCardSource).toContain('absolute bottom-3 left-3 z-20 flex flex-col items-start gap-2');

        expect(eventsPageSource).toContain('fullVisitAvailability');
        expect(eventsPageSource).toContain('fullVisitFetchState');
        expect(eventsPageSource).toContain('preferredClipVariantByEvent');
        expect(eventsPageSource).toContain('onFetchFullVisit');

        expect(dashboardPageSource).toContain('fullVisitAvailability');
        expect(dashboardPageSource).toContain('fullVisitFetchState');
        expect(dashboardPageSource).toContain('preferredClipVariantByEvent');
        expect(dashboardPageSource).toContain('onFetchFullVisit');
    });
});
