import { describe, expect, it } from 'vitest';
import detectionCardSource from './DetectionCard.svelte?raw';
import eventsPageSource from '../pages/Events.svelte?raw';
import dashboardPageSource from '../pages/Dashboard.svelte?raw';
import mediaApiSource from '../api/media.ts?raw';
import openerSource from './RecordDialogs.svelte?raw';

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
        // The readings line sits above the record's own button, so play keeps its action.
        expect(detectionCardSource).toMatch(/relative z-20 flex[^"]*items-center/);
        // The readings follow the name, and the date line takes the spare height: a card with a
        // captures footer is shorter inside, and readings pinned to the bottom sat higher in it
        // than in the cards beside it.
        expect(detectionCardSource).not.toMatch(/relative z-20 mt-auto flex/);
        expect(detectionCardSource).toContain('<div class="mt-auto flex items-center gap-1.5 text-2xs text-muted font-medium flex-wrap">');
        // Under an analysis the readings keep their place but are inert and hidden.
        expect(detectionCardSource).toContain('inert={analysisActive}');
        expect(detectionCardSource).toContain('{#if canPlayVideo}');
        expect(detectionCardSource).toContain('class="btn btn-secondary btn-icon rounded-full"');
        expect(detectionCardSource).not.toContain('absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100');
        expect(detectionCardSource).toContain('M7 3H5a2 2 0 00-2 2v2');

        expect(eventsPageSource).toContain('fullVisitAvailability');
        expect(eventsPageSource).toContain('fullVisitFetchState');
        expect(eventsPageSource).toContain('onFetchFullVisit');
        expect(openerSource).toContain("initialFullVisitPromoted={fullVisitStore.fetchState[video.frigateEvent] === 'ready'}");
        expect(eventsPageSource).not.toContain('preferredClipVariantByEvent');
        expect(eventsPageSource).not.toContain('initialClipVariant={videoClipVariant}');

        expect(dashboardPageSource).toContain('<RecordDialogs');
        expect(dashboardPageSource).not.toContain('preferredClipVariantByEvent');
        expect(dashboardPageSource).not.toContain('initialClipVariant={videoClipVariant}');
    });

    it('shows selection as a brand ring and a check badge, never a blur over the bird', () => {
        expect(detectionCardSource).toMatch(/relative[^"\n]*rounded-4xl[^"\n]*transition-all/);
        // A one-pixel edge in every state, so choosing or analysing a card never changes its height.
        expect(detectionCardSource).toContain("{selectionMode && selected && !analysisActive ? 'border-accent-line ring-2 ring-accent-line");
        expect(detectionCardSource).not.toMatch(/'border-2 border-accent-line/);
        // Every card shows its check while selecting: filled when chosen, an empty circle when not.
        expect(detectionCardSource).toContain('{#if selectionMode && !analysisActive}');
        expect(detectionCardSource).toContain("data-detection-card-check={selected ? 'selected' : 'unselected'}");
        // A veil over the photo and the name hid what had been chosen.
        expect(detectionCardSource).not.toContain('backdrop-blur-xs"></div>');
        expect(detectionCardSource).not.toContain('bg-cyan-500/24');
        // The state is on the control, not only drawn.
        expect(detectionCardSource).toContain('aria-pressed={selectionMode ? selected : undefined}');
        expect(detectionCardSource).toContain("$_('events.row_select'");
        expect(detectionCardSource).not.toContain("$_('common.selected', { default: 'Selected' })");
    });

    it('lets active video analysis take over the card chrome and border', () => {
        expect(detectionCardSource).toContain("let analysisActive = $derived(!!reclassifyProgress);");
        expect(detectionCardSource).toContain("{analysisActive ? 'border-accent-line ring-2 ring-accent-line");
        expect(detectionCardSource).toContain('{#if analysisActive && reclassifyProgress}');
        expect(detectionCardSource).toContain('absolute inset-0 z-50 pointer-events-none rounded-2xl overflow-hidden');
        expect(detectionCardSource).toContain("import DetectionCardAnalysisOverlay from './DetectionCardAnalysisOverlay.svelte'");
        expect(detectionCardSource).toContain('<DetectionCardAnalysisOverlay progress={reclassifyProgress} />');
        expect(detectionCardSource).not.toContain("import ReclassificationOverlay from './ReclassificationOverlay.svelte'");
        expect(detectionCardSource).not.toContain('<ReclassificationOverlay');
        // Under an analysis the readings keep their place but are inert and hidden.
        expect(detectionCardSource).toContain('inert={analysisActive}');
        expect(detectionCardSource).toContain('{#if (onReclassify || onRetag) && !analysisActive}');
        expect(detectionCardSource).toContain('{#if selectionMode && !analysisActive}');
    });
});
