import { describe, expect, it } from 'vitest';
import detectionModalSource from './DetectionModal.svelte?raw';
import aiAnalysisSource from './record/RecordAiAnalysis.svelte?raw';
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
        // The accent fill carries its own ink, which holds AA in every mode (KIT-02).
        expect(detectionModalSource).toContain("fullVisitFetched ? 'gap-2 border-on-media-accent/30 bg-accent px-3 text-accent-fg");
        expect(detectionModalSource).not.toContain("video_player.full_visit_badge', { default: 'Full visit' })}</span>");
        expect(detectionModalSource).not.toContain('bottom-4 left-4 z-30 flex items-end gap-2 mt-3');
        expect(detectionModalSource).not.toContain('{#if fullVisitFetched}\n                                    <div');
        expect(detectionModalSource).not.toContain('absolute inset-0 flex items-center justify-center pointer-events-none');
        expect(detectionModalSource).toContain('inline-flex min-h-11 items-center gap-2 rounded-full border border-on-media/25 bg-media/55');
        expect(detectionModalSource).toContain("video_player.full_visit_action', { default: 'Full visit' }");
        expect(detectionModalSource).not.toContain('img src={getThumbnailUrl(detection.frigate_event)}');
        expect(detectionModalSource).toContain("title={videoFailureInsight.summary}");
        expect(detectionModalSource).toContain('inline-flex h-11 w-11 items-center justify-center rounded-full border border-on-media-fail/70 bg-media/55 text-on-media-fail');
        expect(detectionModalSource).not.toContain("<span>{$_('detection.frigate_badge', { default: 'Frigate' })}</span>");

        expect(eventsPageSource).toContain("fullVisitAvailable={fullVisitAvailability[selectedEvent.frigate_event] === 'available'}");
        expect(eventsPageSource).toContain('selectedEventFullVisitHandler');
        expect(eventsPageSource).toContain('onFetchFullVisit={selectedEventFullVisitHandler}');
        expect(eventsPageSource).toContain('initialFullVisitPromoted={fullVisitFetchState[videoEventId] === \'ready\'}');
        expect(eventsPageSource).not.toContain('preferredClipVariantByEvent');
        expect(eventsPageSource).toContain("autoFetch: true");
        expect(dashboardPageSource).toContain("autoFetch: true");

        expect(dashboardPageSource).toContain("fullVisitAvailable={fullVisitAvailability[selectedEvent.frigate_event] === 'available'}");
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
        expect(detectionModalSource).toContain('handleUseMoment');
        expect(detectionModalSource).toContain('handleGenerateSnapshotCandidates');
        expect(detectionModalSource).toContain('handleApplySnapshot');
        // The moment strip and its "as recorded" moment live in FrameStrip.svelte (#256).
        expect(detectionModalSource).toContain('<FrameStrip');
        expect(detectionModalSource).not.toContain("Save this frame");
        expect(detectionModalSource).not.toContain("Preview, not saved");
        expect(detectionModalSource).toContain('{#if canShowFavoriteAction}');
        expect(detectionModalSource).not.toContain('snapshotRepairOpen');
        expect(detectionModalSource).not.toContain('handleSnapshotRepairToggle');
        expect(detectionModalSource).not.toContain("Crop Type");
        expect(detectionModalSource).not.toContain("Scored Frames");
    });

    it('normalizes media overlay circular controls to a consistent size', () => {
        expect(detectionModalSource).toContain('pointer-events-auto inline-flex h-11 min-w-11 items-center justify-center rounded-full');
        expect(detectionModalSource).toContain("closeData={{ 'data-detection-modal-close': true }}");
        expect(detectionModalSource).toContain('inline-flex h-11 w-11 items-center justify-center rounded-full border border-on-media-fail/70');
    });

    it('persists generated AI analysis back into the current detection state', () => {
        // The note is the record's own field, so writing it back is what shows it.
        expect(aiAnalysisSource).toContain('result.analysis_timestamp');
        expect(aiAnalysisSource).toContain('detection.ai_analysis = result.analysis;');
        expect(aiAnalysisSource).toContain('detection.ai_analysis_timestamp = result.analysis_timestamp;');
        expect(aiAnalysisSource).toContain('detectionsStore.updateDetection({');
        expect(aiAnalysisSource).toContain('ai_analysis: result.analysis');
        expect(aiAnalysisSource).toContain('ai_analysis_timestamp: result.analysis_timestamp');
        expect(aiAnalysisSource).toContain('(detection.ai_analysis ?? null)');
        expect(detectionModalSource).toContain('const nextDetection = applyManualTagResult(detection, result);');
        expect(detectionModalSource).toContain('Object.assign(detection, nextDetection);');
        expect(dashboardPageSource).toContain('asText(d.ai_analysis)');
        expect(dashboardPageSource).toContain('asText(d.ai_analysis_timestamp)');
    });
});
