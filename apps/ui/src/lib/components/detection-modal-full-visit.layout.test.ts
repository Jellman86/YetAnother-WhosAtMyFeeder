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
        expect(detectionModalSource).toContain('inline-flex h-10 w-10 items-center justify-center rounded-full bg-teal-500/95');
        expect(detectionModalSource).not.toContain("video_player.full_visit_badge', { default: 'Full visit' })}</span>");
        expect(detectionModalSource).toContain('bottom-4 left-4 z-30 flex items-end gap-2 mt-3');
        expect(detectionModalSource).toContain('{#if canPlayVideo && !snapshotRepairOpen}\n                            <div class="flex items-center gap-2">');
        expect(detectionModalSource).not.toContain('absolute inset-0 flex items-center justify-center pointer-events-none');
        expect(detectionModalSource).toContain('inline-flex items-center gap-2 rounded-full border border-white/25 bg-black/55');
        expect(detectionModalSource).toContain('M7 3H5a2 2 0 00-2 2v2');
        expect(detectionModalSource).not.toContain('img src={getThumbnailUrl(detection.frigate_event)}');
        expect(detectionModalSource).toContain("title={videoFailureInsight.summary}");
        expect(detectionModalSource).toContain('inline-flex h-10 w-10 items-center justify-center rounded-full border border-rose-200/85 bg-rose-100/92');
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

    it('wires an owner-only HQ crop action into the snapshot hero', () => {
        expect(detectionModalSource).toContain('fetchSnapshotStatus');
        expect(detectionModalSource).toContain('fetchSnapshotCandidates');
        expect(detectionModalSource).toContain('applySnapshotCandidate');
        expect(detectionModalSource).toContain('generateHighQualityBirdCropSnapshot');
        expect(detectionModalSource).toContain('showSnapshotRepairAction');
        expect(detectionModalSource).toContain('hasSnapshotRepairCandidates');
        expect(detectionModalSource).toContain('hasSnapshotRepairWork');
        expect(detectionModalSource).toContain("currentSnapshotSource?.startsWith('hq_candidate_')");
        expect(detectionModalSource).toContain('handleSnapshotRepairToggle');
        expect(detectionModalSource).toContain('handleGenerateSnapshotCandidates');
        expect(detectionModalSource).toContain("Change snapshot");
        expect(detectionModalSource).toContain("Save snapshot");
        expect(detectionModalSource).toContain("Generate HQ snapshot");
        expect(detectionModalSource).toContain("Snapshot sources");
        expect(detectionModalSource).toContain("Candidate frames");
        expect(detectionModalSource).toContain("Original Frigate crop");
        expect(detectionModalSource).toContain("Full snapshot");
        expect(detectionModalSource).toContain("No model-crop frames were found for this detection.");
        expect(detectionModalSource).not.toContain("Snapshot repair");
        expect(detectionModalSource).toContain('handleApplySnapshot');
        expect(detectionModalSource).toContain('</div>\n        </div>\n\n        {#if snapshotRepairOpen}');
        expect(detectionModalSource).toContain('{#if authStore.canModify && !readOnly && !snapshotRepairOpen}');
        expect(detectionModalSource).toContain('{#if showSnapshotRepairAction && !snapshotRepairOpen}');
        expect(detectionModalSource).toContain('{#if canPlayVideo && !snapshotRepairOpen}');
        expect(detectionModalSource).toContain('{#if frigateIssueBadgeVisible && !snapshotRepairOpen}');
    });

    it('normalizes media overlay circular controls to a consistent size', () => {
        expect(detectionModalSource).toContain('inline-flex h-10 w-10 items-center justify-center rounded-full bg-teal-500/95');
        expect(detectionModalSource).toContain('class="absolute top-4 right-4 z-40 inline-flex h-10 w-10 items-center justify-center rounded-full');
        expect(detectionModalSource).toContain('class="absolute top-4 right-16 z-40 inline-flex h-10 w-10 items-center justify-center rounded-full');
        expect(detectionModalSource).toContain('inline-flex h-10 w-10 items-center justify-center rounded-full border border-rose-200/85');
    });

    it('persists generated AI analysis back into the current detection state', () => {
        expect(detectionModalSource).toContain('result.analysis_timestamp');
        expect(detectionModalSource).toContain('detection.ai_analysis = result.analysis;');
        expect(detectionModalSource).toContain('detection.ai_analysis_timestamp = result.analysis_timestamp;');
        expect(detectionModalSource).toContain('detectionsStore.updateDetection({');
        expect(detectionModalSource).toContain('ai_analysis: result.analysis');
        expect(detectionModalSource).toContain('ai_analysis_timestamp: result.analysis_timestamp');
        expect(detectionModalSource).toContain('detection.ai_analysis = null;');
        expect(detectionModalSource).toContain('detection.ai_analysis_timestamp = null;');
        expect(dashboardPageSource).toContain('asText(d.ai_analysis)');
        expect(dashboardPageSource).toContain('asText(d.ai_analysis_timestamp)');
    });
});
