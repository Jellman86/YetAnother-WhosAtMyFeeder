import { describe, expect, it } from 'vitest';
import detectionModalSource from './DetectionModal.svelte?raw';
import eventsPageSource from '../pages/Events.svelte?raw';
import dashboardPageSource from '../pages/Dashboard.svelte?raw';

describe('detection modal full-visit fetch wiring', () => {
    it('threads full-visit state and actions into the details modal', () => {
        expect(detectionModalSource).toContain('onFetchFullVisit');
        expect(detectionModalSource).toContain('fullVisitAvailable');
        expect(detectionModalSource).toContain('fullVisitFetched');
        expect(detectionModalSource).toContain('fullVisitFetchState');
        expect(detectionModalSource).toContain('Fetch full clip');
        expect(detectionModalSource).toContain('Full visit');
        expect(detectionModalSource).toContain('getSnapshotUrl(detection.frigate_event)');
        expect(detectionModalSource).toContain("title={$_('video_player.full_visit_ready'");
        expect(detectionModalSource).toContain('inline-flex h-8 w-8 items-center justify-center rounded-full bg-teal-500/95');
        expect(detectionModalSource).not.toContain("video_player.full_visit_badge', { default: 'Full visit' })}</span>");
        expect(detectionModalSource).toContain('bottom-4 left-4 z-30 flex items-end gap-2 mt-3');
        expect(detectionModalSource).toContain('{#if canPlayVideo}\n                            <div class="flex items-center gap-2">');
        expect(detectionModalSource).not.toContain('absolute inset-0 flex items-center justify-center pointer-events-none');
        expect(detectionModalSource).toContain('inline-flex items-center gap-2 rounded-full border border-white/25 bg-black/55');
        expect(detectionModalSource).toContain('M7 3H5a2 2 0 00-2 2v2');
        expect(detectionModalSource).not.toContain('img src={getThumbnailUrl(detection.frigate_event)}');
        expect(detectionModalSource).toContain("title={videoFailureInsight.summary}");
        expect(detectionModalSource).toContain('inline-flex h-9 w-9 items-center justify-center rounded-full border border-rose-200/85 bg-rose-100/92');
        expect(detectionModalSource).not.toContain("<span>{$_('detection.frigate_badge', { default: 'Frigate' })}</span>");

        expect(eventsPageSource).toContain('fullVisitAvailable={selectedEvent ?');
        expect(eventsPageSource).toContain('selectedEventFullVisitHandler');
        expect(eventsPageSource).toContain('onFetchFullVisit={selectedEventFullVisitHandler}');
        expect(eventsPageSource).toContain('initialFullVisitPromoted={fullVisitFetchState[videoEventId] === \'ready\'}');
        expect(eventsPageSource).not.toContain('preferredClipVariantByEvent');

        expect(dashboardPageSource).toContain('fullVisitAvailable={selectedEvent ?');
        expect(dashboardPageSource).toContain('selectedEventFullVisitHandler');
        expect(dashboardPageSource).toContain('onFetchFullVisit={selectedEventFullVisitHandler}');
        expect(dashboardPageSource).toContain('initialFullVisitPromoted={fullVisitFetchState[videoEventId] === \'ready\'}');
        expect(dashboardPageSource).not.toContain('preferredClipVariantByEvent');
    });

    it('gates owner-only detection actions behind explicit owner access', () => {
        expect(detectionModalSource).toContain('const hasOwnerDetectionActions = $derived(authStore.hasOwnerAccess && !readOnly);');
        expect(detectionModalSource).toContain('{#if hasOwnerDetectionActions}');
        expect(detectionModalSource).toContain('{#if hasOwnerDetectionActions && showTagDropdown}');
        expect(detectionModalSource).toContain('if (!authStore.hasOwnerAccess) return;');
        expect(detectionModalSource).not.toContain('{#if authStore.canModify}\n                <div class="flex gap-2">');
    });
});
