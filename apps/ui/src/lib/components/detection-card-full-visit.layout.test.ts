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
        expect(detectionCardSource).toContain("title={$_('video_player.full_visit_ready'");
        expect(detectionCardSource).toContain('inline-flex h-7 w-7 items-center justify-center rounded-full bg-teal-500/95');
        expect(detectionCardSource).not.toContain("video_player.full_visit_badge', { default: 'Full visit' })}</span>");
        expect(detectionCardSource).toContain('absolute bottom-3 left-3 z-20 flex flex-col items-start gap-2');
        expect(detectionCardSource).toContain('{#if canPlayVideo}\n                <div class="flex items-center gap-2">');
        expect(detectionCardSource).toContain('inline-flex h-9 items-center gap-2 rounded-xl border border-white/25 bg-black/55');
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

    it('uses an icon-only edge selector and stronger cyan framing in selection mode', () => {
        expect(detectionCardSource).toContain("relative rounded-[2rem] transition-all duration-300 ease-out");
        expect(detectionCardSource).toContain("{selectionMode && selected ? 'border-2 border-cyan-300 dark:border-cyan-300/90 ring-2 ring-cyan-500/35");
        expect(detectionCardSource).toContain("{#if selectionMode && selected}");
        expect(detectionCardSource).toContain("absolute inset-0 z-40 overflow-hidden rounded-3xl pointer-events-none");
        expect(detectionCardSource).toContain("bg-cyan-500/24 backdrop-blur-sm");
        expect(detectionCardSource).toContain("absolute inset-0 z-50 flex items-center justify-center");
        expect(detectionCardSource).toContain("class=\"h-16 w-16 text-white drop-shadow-[0_6px_18px_rgba(8,47,73,0.45)]\"");
        expect(detectionCardSource).not.toContain('absolute -left-1.5 -top-1.5 z-30 pointer-events-none');
        expect(detectionCardSource).not.toContain("$_('common.selected', { default: 'Selected' })");
        expect(detectionCardSource).not.toContain("$_('common.select', { default: 'Select' })");
    });
});
