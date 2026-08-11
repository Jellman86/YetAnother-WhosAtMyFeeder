<script lang="ts">
    import { onMount } from 'svelte';
    import DetectionModal from '../components/DetectionModal.svelte';
    import SpeciesDetailModal from '../components/SpeciesDetailModal.svelte';
    import VideoPlayer from '../components/VideoPlayer.svelte';
    import DailyHistogram from '../components/DailyHistogram.svelte';
    import TopVisitors from '../components/TopVisitors.svelte';
    import FieldLog from '../components/FieldLog.svelte';
    import ReviewQueueCard from '../components/ReviewQueueCard.svelte';
    import DayBar from '../components/DayBar.svelte';
    import DeskContextCards from '../components/DeskContextCards.svelte';
    import ReclassificationOverlay from '../components/ReclassificationOverlay.svelte';
    import RecentAudio from '../components/RecentAudio.svelte';
    import { detectionsStore } from '../stores/detections.svelte';
    import { toastStore } from '../stores/toast.svelte';
    import type { AudioSummaryResponse, Detection, DailySummary, SpeciesInfo } from '../api';
    import { deleteDetection, hideDetection, updateDetectionSpecies, analyzeDetection, fetchAudioSummary, fetchDailySummary, fetchClassifierLabels, reclassifyDetection, fetchSpeciesInfo } from '../api';
    import { settingsStore } from '../stores/settings.svelte';
    import { pageRefreshAction } from '../stores/page_refresh_action.svelte';
    import { fullVisitStore } from '../stores/full-visit.svelte';
    import { authStore } from '../stores/auth.svelte';
    import { _ } from 'svelte-i18n';
    import { getErrorMessage, isTransientRequestError } from '../utils/error-handling';
    import { logger } from '../utils/logger';
    import { selectReclassificationStrategy } from '../utils/reclassification';

    import { getBirdNames } from '../naming';
    import { groupDetectionsIntoVisits, withinDeskWindow } from '../utils/visit-grouping';
    import { buildReviewQueue } from '../utils/review-queue';

    interface Props {
        onnavigate?: (path: string) => void;
    }

    let { onnavigate }: Props = $props();

    /** The dashboard shows the recent slice of the day; Explorer holds the full history. */
    const VISIT_ROW_LIMIT = 12;

    let summary = $state<DailySummary | null>(null);
    let summaryLoading = $state(true);
    let topSpeciesInfo = $state<SpeciesInfo | null>(null);
    let selectedEvent = $state<Detection | null>(null);
    let selectedSpecies = $state<string | null>(null);
    let deleting = $state(false);
    let hiding = $state(false);
    let lastModalEventId = $state<string | null>(null);

    // Settings state
    let llmReady = $state(false);
    let showCommon = $state(true);
    let preferSci = $state(false);
    $effect(() => {
        llmReady = settingsStore.llmReady;
        showCommon = settingsStore.displayCommonNames;
        preferSci = settingsStore.scientificNamePrimary;
    });

    const birdnetEnabled = $derived(
        settingsStore.settings?.birdnet_enabled ?? authStore.birdnetEnabled ?? false
    );

    // AI Analysis state
    let analyzingAI = $state(false);
    let aiAnalysis = $state<string | null>(null);

    // Video playback state
    let showVideo = $state(false);
    let videoEventId = $state<string | null>(null);
    let videoPlayIntent = $state<'auto' | 'user'>('auto');
    let fullVisitAvailability = $derived(fullVisitStore.availability);
    let fullVisitFetchState = $derived(fullVisitStore.fetchState);
    let recordingClipFetchEnabled = $derived(
        (settingsStore.settings?.recording_clip_enabled ?? false) &&
        (settingsStore.settings?.clips_enabled ?? false)
    );
    let selectedEventFullVisitHandler = $derived.by(() => {
        const current = selectedEvent;
        if (!current || !recordingClipFetchEnabled) return undefined;
        return () => handleFetchFullVisit(current);
    });

    // Manual Tag state
    let classifierLabels = $state<string[]>([]);
    let tagSearchQuery = $state('');
    let showTagDropdown = $state(false);
    let updatingTag = $state(false);

    let filteredLabels = $derived(
        classifierLabels.filter(l => 
            String(l).toLowerCase().includes(tagSearchQuery.toLowerCase())
        ).slice(0, 50)
    );

    // One window for the whole desk, so the day bar, the log and the context cards agree.
    let deskDetections = $derived(withinDeskWindow(detectionsStore.detections));

    // The day reads as visits, not frames: repeat frames of one bird fold into one row.
    let visits = $derived(groupDetectionsIntoVisits(deskDetections).slice(0, VISIT_ROW_LIMIT));

    // Detections still waiting on a person, oldest first.
    let reviewQueue = $derived(buildReviewQueue(deskDetections));

    // Derive reclassification progress for the modal
    let modalReclassifyProgress = $derived(
        selectedEvent ? detectionsStore.getReclassificationProgress(selectedEvent.frigate_event) : undefined
    );

    // Derive naming logic for the modal
    let modalNaming = $derived.by(() => {
        if (!selectedEvent) return { primary: '', secondary: null };
        const showCommon = settingsStore.displayCommonNames;
        const preferSci = settingsStore.scientificNamePrimary;
        return getBirdNames(selectedEvent, showCommon, preferSci);
    });

    let modalPrimaryName = $derived(modalNaming.primary);
    let modalSubName = $derived(modalNaming.secondary);

    $effect(() => {
        if (!recordingClipFetchEnabled) return;
        for (const visit of visits) {
            void fullVisitStore.ensureAvailability(visit.best.frigate_event);
        }
    });

    $effect(() => {
        if (!recordingClipFetchEnabled || !selectedEvent) {
            return;
        }
        const eventId = selectedEvent.frigate_event;
        const isNewOpen = eventId !== lastModalEventId;
        if (isNewOpen) {
            lastModalEventId = eventId;
            // Force fresh probe: a cached 'unavailable' from a previous check may
            // now be wrong if the clip was fetched in another session or tab.
            void fullVisitStore.ensureAvailability(eventId, { refresh: true, autoFetch: true });
        } else {
            // Same event still open (SSE update to selectedEvent while modal is open).
            // Non-refresh probe respects the current cache — no redundant round-trips.
            void fullVisitStore.ensureAvailability(eventId, { autoFetch: true });
        }
    });

    function detectionSyncSignature(d: Detection): string {
        const asText = (value: unknown) => {
            if (value === null || value === undefined) return '';
            return String(value);
        };
        const asNumber = (value: unknown) => {
            const parsed = Number(value);
            return Number.isFinite(parsed) ? String(parsed) : '';
        };
        const asFlag = (value: unknown) => (value ? '1' : '0');
        return [
            asText(d.frigate_event),
            asText(d.display_name),
            asNumber(d.score),
            asFlag(d.manual_tagged),
            asFlag(d.is_hidden),
            asFlag(d.is_favorite),
            asText(d.video_classification_status),
            asText(d.video_classification_label),
            asNumber(d.video_classification_score),
            asText(d.ai_analysis),
            asText(d.ai_analysis_timestamp),
        ].join('|');
    }

    let last24hCount = $derived(summary?.total_count ?? detectionsStore.totalToday);
    let last24hSpecies = $derived(summary?.top_species.length ?? 0);
    let audioConfirmations = $derived(summary?.audio_confirmations ?? 0);

    // Derive most seen species name based on preference
    let mostSeenName = $derived.by(() => {
        const top = summary?.top_species[0];
        if (!top) return null;
        const showCommon = settingsStore.displayCommonNames;
        const preferSci = settingsStore.scientificNamePrimary;
        return getBirdNames(top, showCommon, preferSci).primary;
    });

    async function loadSummary(force = false) {
        try {
            const [summaryRes, labelsRes] = await Promise.all([
                fetchDailySummary(),
                fetchClassifierLabels().catch(() => ({ labels: [] }))
            ]);
            summary = summaryRes;
            classifierLabels = labelsRes.labels;
        } catch (e) {
            if (isTransientRequestError(e)) {
                logger.warn('Dashboard summary fetch failed (transient)', {
                    message: getErrorMessage(e)
                });
            } else {
                logger.error('Failed to load summary', e);
            }
        } finally {
            summaryLoading = false;
        }
    }

    $effect(() => {
        const topSpecies = summary?.top_species?.[0]?.species;
        if (!topSpecies || topSpecies === 'Unknown Bird') {
            topSpeciesInfo = null;
            return;
        }
        const speciesName = topSpecies;
        void (async () => {
            try {
                const info = await fetchSpeciesInfo(speciesName);
                if (summary?.top_species?.[0]?.species === speciesName) {
                    topSpeciesInfo = info;
                }
            } catch {
                if (summary?.top_species?.[0]?.species === speciesName) {
                    topSpeciesInfo = null;
                }
            }
        })();
    });

    onMount(async () => {
        await loadSummary(true);
    });

    // One audio summary for the whole desk: the day bar and the sensor card share it.
    let audioSummary = $state<AudioSummaryResponse | null>(null);

    $effect(() => {
        if (!birdnetEnabled) {
            audioSummary = null;
            return;
        }
        const controller = new AbortController();
        void (async () => {
            try {
                audioSummary = await fetchAudioSummary({ days: 1 }, controller.signal);
            } catch (e) {
                if (controller.signal.aborted) return;
                if (isTransientRequestError(e)) {
                    logger.warn('Audio summary unavailable (transient)', { message: getErrorMessage(e) });
                } else {
                    logger.error('Failed to fetch audio summary', e);
                }
            }
        })();
        return () => controller.abort();
    });

    $effect(() => {
        return pageRefreshAction.register(async () => {
            summaryLoading = true;
            await Promise.all([
                detectionsStore.loadInitial(),
                loadSummary(true)
            ]);
        });
    });

    // Reset state when switching detections
    $effect(() => {
        if (selectedEvent) {
            showVideo = false;
            aiAnalysis = null;
            showTagDropdown = false;
            tagSearchQuery = '';
        }
    });

    $effect(() => {
        if (!selectedEvent) return;
        const updated = detectionsStore.detections.find(
            (d) => d.frigate_event === selectedEvent?.frigate_event
        );
        // Avoid proxy-identity churn causing a self-triggering effect loop.
        if (updated) {
            const definedPatch = Object.fromEntries(
                Object.entries(updated).filter(([, value]) => value !== undefined)
            ) as Partial<Detection>;
            const merged = { ...selectedEvent, ...definedPatch } as Detection;
            if (detectionSyncSignature(merged) !== detectionSyncSignature(selectedEvent)) {
                selectedEvent = merged;
            }
        }
    });

    async function handleReclassify() {
        if (!selectedEvent) return;
        const eventId = selectedEvent.frigate_event;
        const requestedStrategy = selectReclassificationStrategy(
            selectedEvent.has_clip,
            fullVisitFetchState[eventId]
        );
        try {
            const result = await reclassifyDetection(eventId, requestedStrategy);

            if (result.status === 'queued') return;
            if (!result.updated) {
                toastStore.warning($_('notifications.reclassify_no_result'));
                return;
            }

            // Check if backend used a different strategy (fallback occurred)
            if (result.actual_strategy && result.actual_strategy !== requestedStrategy) {
                toastStore.warning($_('notifications.reclassify_fallback'));
            }
        } catch (error) {
            detectionsStore.dismissReclassification(eventId);
            const message = getErrorMessage(error);
            console.error('Failed to start reclassification', message, error);
            toastStore.error($_('notifications.reclassify_failed', { values: { message } }));
        }
    }

    async function handleFetchFullVisit(detection: Detection) {
        try {
            const complete = await fullVisitStore.fetchFullVisit(detection.frigate_event);
            if (complete) {
                toastStore.success($_('video_player.full_visit_ready', { default: 'Full visit clip ready' }));
            } else {
                toastStore.warning($_('video_player.partial_visit_ready', { default: 'A partial visit is ready; retry shortly for the complete clip.' }));
            }
        } catch (e) {
            const message = e instanceof Error ? e.message : $_('video_player.full_visit_failed', { default: 'Could not fetch full visit clip' });
            toastStore.error(message);
        }
    }

    async function handleManualTag(newSpecies: string) {
        if (!selectedEvent) return;
        updatingTag = true;
        try {
            const eventId = selectedEvent.frigate_event;
            await updateDetectionSpecies(eventId, newSpecies);
            selectedEvent.display_name = newSpecies;
            selectedEvent.category_name = newSpecies;
            selectedEvent.manual_tagged = true;
            // Optimistically update store
            detectionsStore.updateDetection({ ...selectedEvent, display_name: newSpecies, category_name: newSpecies, manual_tagged: true });
            if (recordingClipFetchEnabled) {
                await fullVisitStore.ensureAvailability(eventId, { refresh: true });
            }
            showTagDropdown = false;
            await loadSummary(true);
        } catch (e) {
            console.error('Failed to update species', e);
        } finally {
            updatingTag = false;
        }
    }

    async function handleDelete() {
        if (!selectedEvent) return;
        if (!confirm($_('actions.confirm_delete', { values: { species: selectedEvent.display_name } }))) return;
        deleting = true;
        try {
            await deleteDetection(selectedEvent.frigate_event);
            detectionsStore.removeDetection(selectedEvent.frigate_event, selectedEvent.detection_time);
            selectedEvent = null;
            await loadSummary(true);
        } catch (e) {
            console.error('Failed to delete detection', e);
        } finally {
            deleting = false;
        }
    }

    async function handleHide() {
        if (!selectedEvent) return;
        hiding = true;
        try {
            const result = await hideDetection(selectedEvent.frigate_event);
            if (result.is_hidden) {
                detectionsStore.removeDetection(selectedEvent.frigate_event, selectedEvent.detection_time);
                selectedEvent = null;
                await loadSummary(true);
            }
        } catch (e) {
            console.error('Failed to hide detection', e);
        } finally {
            hiding = false;
        }
    }

    function handleSpeciesSummaryClick(speciesFilter: string) {
        // Top Visitors is last-24h data; avoid forcing "today" which can hide valid events
        // around midnight boundaries. Filter by species/taxa only.
        onnavigate?.(`/events?species=${encodeURIComponent(speciesFilter)}`);
    }

    async function handleAIAnalysis() {
        if (!selectedEvent) return;
        analyzingAI = true;
        aiAnalysis = null;
        try {
            const result = await analyzeDetection(selectedEvent.frigate_event);
            aiAnalysis = result.analysis;
        } catch (e) {
            console.error('AI Analysis failed', e);
        } finally {
            analyzingAI = false;
        }
    }
</script>

<div class="space-y-6">
    <DayBar
        visitCount={last24hCount}
        speciesCount={last24hSpecies}
        unresolvedCount={reviewQueue.total}
        audioCalls={audioSummary?.total ?? null}
        {audioConfirmations}
        connected={detectionsStore.connected}
    />

    <!-- Field desk: the day reads as one chronological log, with the outstanding work docked beside it. -->
    <section
        data-dashboard-field-desk
        class="grid grid-cols-1 items-start gap-8 xl:grid-cols-[minmax(0,1.55fr)_minmax(18rem,0.7fr)]"
    >
        <FieldLog
            visits={visits}
            loading={detectionsStore.isLoading}
            onselect={(detection) => selectedEvent = detection}
            onidentify={(detection) => selectedEvent = detection}
            onseeall={() => onnavigate?.('/events')}
        />

        <aside class="flex flex-col gap-7 xl:border-l xl:border-slate-200 xl:pl-8 dark:xl:border-slate-700">
            <ReviewQueueCard
                queue={reviewQueue}
                onreview={(detection) => selectedEvent = detection}
                onreviewall={() => onnavigate?.('/events')}
            />

            <DeskContextCards
                detections={deskDetections}
                {birdnetEnabled}
                {audioSummary}
            />

            {#if summary}
                <DailyHistogram data={summary.hourly_distribution} />
            {:else if summaryLoading}
                <div class="min-h-[210px] animate-pulse border-y border-slate-200/60 bg-slate-100/60 dark:border-slate-700/60 dark:bg-slate-800/40"></div>
            {/if}

            {#if birdnetEnabled}
                <RecentAudio onNavigate={onnavigate} />
            {/if}
        </aside>
    </section>

    <!-- Top visitors needs the full width; it does not compress into the rail. -->
    <section data-dashboard-top-visitors>
        {#if summary && summary.top_species.length > 0}
            <TopVisitors
                species={summary.top_species}
                onSpeciesClick={handleSpeciesSummaryClick}
            />
        {:else if summaryLoading}
            <div class="min-h-[150px] animate-pulse border-y border-slate-200/60 bg-slate-100/60 dark:border-slate-700/60 dark:bg-slate-800/40"></div>
        {/if}
    </section>
</div>

<!-- Event Detail Modal -->
{#if selectedEvent}
    <DetectionModal
        detection={selectedEvent}
        {classifierLabels}
        llmReady={llmReady}
        showVideoButton={true}
        fullVisitAvailable={selectedEvent ? fullVisitAvailability[selectedEvent.frigate_event] === 'available' : false}
        fullVisitFetched={selectedEvent ? fullVisitFetchState[selectedEvent.frigate_event] === 'ready' : false}
        fullVisitFetchState={selectedEvent ? (fullVisitFetchState[selectedEvent.frigate_event] ?? 'idle') : 'idle'}
        onClose={() => selectedEvent = null}
        onReclassify={handleReclassify}
        onFetchFullVisit={selectedEventFullVisitHandler}
        onPlayVideo={(frigateEvent: string, playIntent: 'auto' | 'user' = 'auto') => {
            videoEventId = frigateEvent;
            videoPlayIntent = playIntent;
            showVideo = true;
            selectedEvent = null;
        }}
        onViewSpecies={(species: string) => { selectedSpecies = species; selectedEvent = null; }}
    />
{/if}


{#if selectedSpecies}<SpeciesDetailModal speciesName={selectedSpecies} onclose={() => selectedSpecies = null} />{/if}
{#if showVideo && videoEventId}
    <VideoPlayer
        frigateEvent={videoEventId}
        playIntent={videoPlayIntent}
        initialFullVisitPromoted={fullVisitFetchState[videoEventId] === 'ready'}
        onClose={() => {
            showVideo = false;
            videoEventId = null;
        }}
    />
{/if}
