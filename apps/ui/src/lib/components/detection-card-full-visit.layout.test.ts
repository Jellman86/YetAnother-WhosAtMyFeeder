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
        expect(detectionCardSource).toContain("text={$_('video_player.full_visit_ready'");
        // The marker rides on the play button now. Beside it, a 20px circle next
        // to a 44px one read as a second, broken control.
        expect(detectionCardSource).toContain('absolute -right-0.5 -top-0.5');
        expect(detectionCardSource).toContain('h-4 w-4 items-center justify-center rounded-full');
        expect(detectionCardSource).not.toContain("video_player.full_visit_badge', { default: 'Full visit' })}</span>");
        // The overlay row sits bottom-left and above the media, which is what
        // this test needs; its exact utility list is the card's business.
        expect(detectionCardSource).toMatch(/absolute bottom-3 left-3 z-20 flex[^"]*items-center/);
        expect(detectionCardSource).toContain('{#if !analysisActive}');
        expect(detectionCardSource).toContain('{#if canPlayVideo}');
        expect(detectionCardSource).toContain('inline-flex h-11 w-11 items-center justify-center rounded-full border border-white/25 bg-black/55');
        expect(detectionCardSource).not.toContain('absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100');
        expect(detectionCardSource).toContain('M7 3H5a2 2 0 00-2 2v2');

        expect(eventsPageSource).toContain('fullVisitAvailability');
        expect(eventsPageSource).toContain('fullVisitFetchState');
        expect(eventsPageSource).toContain('onFetchFullVisit');
        expect(eventsPageSource).toContain('initialFullVisitPromoted={fullVisitFetchState[videoEventId] === \'ready\'}');
        expect(eventsPageSource).not.toContain('preferredClipVariantByEvent');
        expect(eventsPageSource).not.toContain('initialClipVariant={videoClipVariant}');

        expect(dashboardPageSource).toContain('fullVisitAvailability');
        expect(dashboardPageSource).toContain('fullVisitFetchState');
        expect(dashboardPageSource).toContain('onFetchFullVisit');
        expect(dashboardPageSource).toContain('initialFullVisitPromoted={fullVisitFetchState[videoEventId] === \'ready\'}');
        expect(dashboardPageSource).not.toContain('preferredClipVariantByEvent');
        expect(dashboardPageSource).not.toContain('initialClipVariant={videoClipVariant}');
    });

    it('shows selection as a brand ring and a check badge, never a blur over the bird', () => {
        expect(detectionCardSource).toMatch(/relative[^"\n]*rounded-\[2rem\][^"\n]*transition-all/);
        expect(detectionCardSource).toContain("{selectionMode && selected && !analysisActive ? 'border-2 border-brand-600 ring-2 ring-brand-500/60");
        // Every card shows its check while selecting: filled when chosen, an empty circle when not.
        expect(detectionCardSource).toContain('{#if selectionMode && !analysisActive}');
        expect(detectionCardSource).toContain("data-detection-card-check={selected ? 'selected' : 'unselected'}");
        // A veil over the photo and the name hid what had been chosen.
        expect(detectionCardSource).not.toContain('backdrop-blur-sm"></div>');
        expect(detectionCardSource).not.toContain('bg-cyan-500/24');
        // The state is on the control, not only drawn.
        expect(detectionCardSource).toContain('aria-pressed={selectionMode ? selected : undefined}');
        expect(detectionCardSource).toContain("$_('events.row_select'");
        expect(detectionCardSource).not.toContain("$_('common.selected', { default: 'Selected' })");
    });

    it('lets active video analysis take over the card chrome and border', () => {
        expect(detectionCardSource).toContain("let analysisActive = $derived(!!reclassifyProgress);");
        expect(detectionCardSource).toContain("{analysisActive ? 'border-2 border-indigo-400/90 dark:border-indigo-300/90 ring-2 ring-indigo-500/30");
        expect(detectionCardSource).toContain('{#if analysisActive && reclassifyProgress}');
        expect(detectionCardSource).toContain('absolute inset-0 z-50 pointer-events-none rounded-2xl overflow-hidden');
        expect(detectionCardSource).toContain("import DetectionCardAnalysisOverlay from './DetectionCardAnalysisOverlay.svelte'");
        expect(detectionCardSource).toContain('<DetectionCardAnalysisOverlay progress={reclassifyProgress} />');
        expect(detectionCardSource).not.toContain("import ReclassificationOverlay from './ReclassificationOverlay.svelte'");
        expect(detectionCardSource).not.toContain('<ReclassificationOverlay');
        expect(detectionCardSource).toContain('{#if !analysisActive}');
        expect(detectionCardSource).toContain('{#if (onReclassify || onRetag) && !analysisActive}');
        expect(detectionCardSource).toContain('{#if selectionMode && !analysisActive}');
    });
});
