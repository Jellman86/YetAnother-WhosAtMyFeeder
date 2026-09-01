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
        expect(detectionModalSource).toContain("fullVisitFetchState === 'failed'");
        expect(detectionModalSource).toContain('Fetch full clip');
        expect(detectionModalSource).toContain('Full visit');
        expect(detectionModalSource).toContain('getSnapshotUrl(detection.frigate_event)');
        expect(detectionModalSource).toContain("title={fullVisitFetched ? $_('video_player.full_visit_ready'");
        expect(detectionModalSource).toContain("fullVisitFetched ? 'gap-2 border-brand-300/30 bg-brand-500/95");
        expect(detectionModalSource).not.toContain("video_player.full_visit_badge', { default: 'Full visit' })}</span>");
        expect(detectionModalSource).not.toContain('bottom-4 left-4 z-30 flex items-end gap-2 mt-3');
        expect(detectionModalSource).not.toContain('{#if fullVisitFetched}\n                                    <div');
        expect(detectionModalSource).not.toContain('absolute inset-0 flex items-center justify-center pointer-events-none');
        expect(detectionModalSource).toContain('inline-flex min-h-11 items-center gap-2 rounded-full border border-white/25 bg-black/55');
        expect(detectionModalSource).toContain("video_player.full_visit_action', { default: 'Full visit' }");
        expect(detectionModalSource).not.toContain('img src={getThumbnailUrl(detection.frigate_event)}');
        expect(detectionModalSource).toContain("title={videoFailureInsight.summary}");
        expect(detectionModalSource).toContain('inline-flex h-11 w-11 items-center justify-center rounded-full border border-rose-200/85 bg-rose-100/92');
        expect(detectionModalSource).not.toContain("<span>{$_('detection.frigate_badge', { default: 'Frigate' })}</span>");

        expect(eventsPageSource).toContain('fullVisitAvailable={selectedEvent ?');
        expect(eventsPageSource).toContain('selectedEventFullVisitHandler');
        expect(eventsPageSource).toContain('onFetchFullVisit={selectedEventFullVisitHandler}');
        expect(eventsPageSource).toContain('initialFullVisitPromoted={fullVisitFetchState[videoEventId] === \'ready\'}');
        expect(eventsPageSource).not.toContain('preferredClipVariantByEvent');
        expect(eventsPageSource).toContain("autoFetch: true");
        expect(dashboardPageSource).toContain("autoFetch: true");

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

    it('replaces the owner-only HQ crop overlay with the inline frame rail', () => {
        expect(detectionModalSource).toContain('fetchSnapshotStatus');
        expect(detectionModalSource).toContain('fetchSnapshotCandidates');
        expect(detectionModalSource).toContain('applySnapshotCandidate');
        expect(detectionModalSource).toContain('generateHighQualityBirdCropSnapshot');
        expect(detectionModalSource).toContain('showInlineFramePicker');
        expect(detectionModalSource).toContain('data-detection-inline-frame-picker');
        expect(detectionModalSource).toContain('previewSnapshotCandidate');
        expect(detectionModalSource).toContain('cancelSnapshotPreview');
        expect(detectionModalSource).toContain('handleGenerateSnapshotCandidates');
        expect(detectionModalSource).toContain("Save this frame");
        expect(detectionModalSource).toContain("Regenerate snapshots");
        expect(detectionModalSource).toContain("Preview, not saved");
        expect(detectionModalSource).toContain("snapshot_framing_as_recorded");
        expect(detectionModalSource).toContain('handleApplySnapshot');
        expect(detectionModalSource).toContain('{#if canShowFavoriteAction}');
        expect(detectionModalSource).not.toContain('snapshotRepairOpen');
        expect(detectionModalSource).not.toContain('handleSnapshotRepairToggle');
        expect(detectionModalSource).not.toContain("Crop Type");
        expect(detectionModalSource).not.toContain("Scored Frames");
    });

    it('normalizes media overlay circular controls to a consistent size', () => {
        expect(detectionModalSource).toContain('pointer-events-auto inline-flex h-11 min-w-11 items-center justify-center rounded-full');
        expect(detectionModalSource).toContain('class="absolute top-4 right-4 z-40 inline-flex h-11 w-11 items-center justify-center rounded-full');
        expect(detectionModalSource).toContain('inline-flex h-11 w-11 items-center justify-center rounded-full border border-rose-200/85');
    });

    it('persists generated AI analysis back into the current detection state', () => {
        expect(detectionModalSource).toContain('result.analysis_timestamp');
        expect(detectionModalSource).toContain('detection.ai_analysis = result.analysis;');
        expect(detectionModalSource).toContain('detection.ai_analysis_timestamp = result.analysis_timestamp;');
        expect(detectionModalSource).toContain('detectionsStore.updateDetection({');
        expect(detectionModalSource).toContain('ai_analysis: result.analysis');
        expect(detectionModalSource).toContain('ai_analysis_timestamp: result.analysis_timestamp');
        expect(detectionModalSource).toContain('const nextDetection = applyManualTagResult(detection, result);');
        expect(detectionModalSource).toContain('Object.assign(detection, nextDetection);');
        expect(dashboardPageSource).toContain('asText(d.ai_analysis)');
        expect(dashboardPageSource).toContain('asText(d.ai_analysis_timestamp)');
    });
});
