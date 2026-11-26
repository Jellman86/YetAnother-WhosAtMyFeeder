<script lang="ts">
    import { _ } from 'svelte-i18n';
    import LazyModal from './LazyModal.svelte';
    import { loadDetectionModal, loadVideoPlayer } from './lazy-dialogs';
    import type { RecordVideo } from './record-video';
    import { videoHeadingFor } from './video-heading';
    import type { Detection } from '../api';
    import { reclassifyDetection } from '../api';
    import { birdNames } from '../naming';
    import { authStore } from '../stores/auth.svelte';
    import { detectionsStore } from '../stores/detections.svelte';
    import { fullVisitStore } from '../stores/full-visit.svelte';
    import { publicSettingsStore } from '../stores/public_settings.svelte';
    import { settingsStore } from '../stores/settings.svelte';
    import { toastStore } from '../stores/toast.svelte';
    import { withLiveFields } from '../utils/detection-sync';
    import { fetchFullVisitAndReport } from '../utils/full-visit-fetch';
    import { getErrorMessage } from '../utils/error-handling';
    import { logger } from '../utils/logger';
    import { canWatchRecordVideo, recordingClipsOn } from '../utils/record-access';
    import { selectReclassificationStrategy } from '../utils/reclassification';

    /**
     * The one way a page opens a record and its video. The record offers the same controls and
     * information wherever it opens; only access decides what is shown. A page supplies what is truly
     * its own, such as dropping a row from its list after a delete.
     */
    interface Props {
        record: Detection | null;
        video: RecordVideo | null;
        onViewSpecies: (speciesName: string) => void;
        onDeleteSuccess?: (frigateEvent: string, detectionTime?: string) => void | Promise<void>;
        onHideSuccess?: (frigateEvent: string, detectionTime: string | undefined, isHidden: boolean) => void | Promise<void>;
        /** A bird correction, exclusion or recount, for a page that shows counts the server keeps. */
        onbirdschanged?: () => void;
    }

    let {
        record = $bindable(),
        video = $bindable(),
        onViewSpecies,
        onDeleteSuccess,
        onHideSuccess,
        onbirdschanged
    }: Props = $props();

    const fullVisitsOn = $derived(
        recordingClipsOn(settingsStore.settings, publicSettingsStore.settings) && canWatchRecordVideo(authStore)
    );
    const fullVisitHandler = $derived.by(() => {
        const current = record;
        if (!current || !fullVisitsOn) return undefined;
        return () => fetchFullVisitAndReport(current.frigate_event);
    });

    // Not view state: it only tells a new open from a live update to the record already open.
    let probedEventId: string | null = null;
    $effect(() => {
        if (!fullVisitsOn || !record) return;
        const eventId = record.frigate_event;
        if (eventId !== probedEventId) {
            probedEventId = eventId;
            // A cached 'unavailable' may be wrong now if the clip was fetched in another tab.
            void fullVisitStore.ensureAvailability(eventId, { refresh: true, autoFetch: true });
        } else {
            void fullVisitStore.ensureAvailability(eventId, { autoFetch: true });
        }
    });

    // A reclassification or correction reaches `detectionsStore` from the server's event stream while
    // the record is open. This stays an effect, not a `$derived` copy, because the dialog edits the
    // bound record in place (a species change, an AI note): a derived merge would hand it a fresh,
    // unproxied object on every store change and lose those edits. `withLiveFields` keeps the same
    // object when nothing shown changed, so this never writes back what it just read.
    $effect(() => {
        const current = record;
        if (!current) return;
        const updated = detectionsStore.detections.find((d) => d.frigate_event === current.frigate_event);
        const next = withLiveFields(current, updated);
        if (next !== current) record = next;
    });

    function play(frigateEvent: string, playIntent: 'auto' | 'user' = 'auto'): void {
        const shown = record;
        video = {
            frigateEvent,
            heading: shown ? videoHeadingFor(shown, settingsStore.displayCommonNames, settingsStore.scientificNamePrimary, $birdNames) : null,
            shareToken: null,
            playIntent
        };
        // One overlay at a time: the player replaces the record.
        record = null;
    }

    function viewSpecies(speciesName: string): void {
        record = null;
        onViewSpecies(speciesName);
    }

    async function reclassify(detection: Detection): Promise<void> {
        const eventId = detection.frigate_event;
        const requestedStrategy = selectReclassificationStrategy(detection.has_clip, fullVisitStore.fetchState[eventId]);
        try {
            const result = await reclassifyDetection(eventId, requestedStrategy);
            if (result.status === 'queued') return;
            if (!result.updated) {
                toastStore.warning($_('notifications.reclassify_no_result'));
                return;
            }
            if (result.actual_strategy && result.actual_strategy !== requestedStrategy) {
                toastStore.warning($_('notifications.reclassify_fallback'));
            }
        } catch (error) {
            detectionsStore.dismissReclassification(eventId);
            const message = getErrorMessage(error);
            logger.error('Failed to start reclassification', error);
            toastStore.error($_('notifications.reclassify_failed', { values: { message } }));
        }
    }

</script>

{#if record}
    <LazyModal loader={loadDetectionModal} onclose={() => (record = null)}>
        {#snippet children(DetectionModal)}
            {#if record}
                <DetectionModal
                    detection={record}
                    llmReady={settingsStore.llmReady}
                    fullVisitAvailable={fullVisitStore.availability[record.frigate_event] === 'available'}
                    fullVisitFetched={fullVisitStore.fetchState[record.frigate_event] === 'ready'}
                    fullVisitFetchState={fullVisitStore.fetchState[record.frigate_event] ?? 'idle'}
                    onClose={() => (record = null)}
                    onReclassify={reclassify}
                    onFetchFullVisit={fullVisitHandler}
                    onPlayVideo={play}
                    onViewSpecies={viewSpecies}
                    {onDeleteSuccess}
                    {onHideSuccess}
                    {onbirdschanged}
                />
            {/if}
        {/snippet}
    </LazyModal>
{/if}

{#if video}
    <LazyModal loader={loadVideoPlayer} onclose={() => (video = null)}>
        {#snippet children(VideoPlayer)}
            {#if video}
                <VideoPlayer
                    frigateEvent={video.frigateEvent}
                    heading={video.heading}
                    shareToken={video.shareToken}
                    playIntent={video.playIntent}
                    initialFullVisitPromoted={fullVisitStore.fetchState[video.frigateEvent] === 'ready'}
                    onClose={() => (video = null)}
                />
            {/if}
        {/snippet}
    </LazyModal>
{/if}
