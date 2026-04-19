<script lang="ts">
    import { onMount } from 'svelte';
    import { fade, fly } from 'svelte/transition';
    import DetectionCard from '../components/DetectionCard.svelte';
    import DetectionModal from '../components/DetectionModal.svelte';
    import SpeciesDetailModal from '../components/SpeciesDetailModal.svelte';
    import VideoPlayer from '../components/VideoPlayer.svelte';
    import DailyHistogram from '../components/DailyHistogram.svelte';
    import TopVisitors from '../components/TopVisitors.svelte';
    import LatestDetectionHero from '../components/LatestDetectionHero.svelte';
    import StatsRibbon from '../components/StatsRibbon.svelte';
    import ReclassificationOverlay from '../components/ReclassificationOverlay.svelte';
    import RecentAudio from '../components/RecentAudio.svelte';
    import { detectionsStore } from '../stores/detections.svelte';
    import { toastStore } from '../stores/toast.svelte';
    import type { Detection, DailySummary, SpeciesInfo } from '../api';
    import { deleteDetection, hideDetection, updateDetectionSpecies, analyzeDetection, fetchDailySummary, fetchClassifierLabels, reclassifyDetection, fetchSpeciesInfo } from '../api';
    import { settingsStore } from '../stores/settings.svelte';
    import { fullVisitStore } from '../stores/full-visit.svelte';
    import { authStore } from '../stores/auth.svelte';
    import { _ } from 'svelte-i18n';
    import { getErrorMessage, isTransientRequestError } from '../utils/error-handling';
    import { logger } from '../utils/logger';

    import { getBirdNames } from '../naming';

    interface Props {
        onnavigate?: (path: string) => void;
    }

    let { onnavigate }: Props = $props();

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

    // Derive the hero detection (latest one)
    let heroDetection = $derived(detectionsStore.detections[0] || summary?.latest_detection || null);
    let visibleFeedDetections = $derived(detectionsStore.detections.slice(1, 10));

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
        for (const detection of visibleFeedDetections) {
            void fullVisitStore.ensureAvailability(detection.frigate_event);
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
        const requestedStrategy = selectedEvent.has_clip ? 'video' : 'snapshot';
        try {
            const result = await reclassifyDetection(eventId, requestedStrategy);

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
            await fullVisitStore.fetchFullVisit(detection.frigate_event);
            toastStore.success($_('video_player.full_visit_ready', { default: 'Full visit clip ready' }));
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

<div class="space-y-8">
    <!-- Stats Ribbon -->
    {#if summary || detectionsStore.totalToday > 0}
        <div in:fly={{ y: -20, duration: 500 }}>
            <StatsRibbon
                todayCount={last24hCount}
                uniqueSpecies={last24hSpecies}
                mostSeenSpecies={mostSeenName}
                mostSeenCount={summary?.top_species[0]?.count ?? 0}
                {audioConfirmations}
                topVisitorImageUrl={topSpeciesInfo?.thumbnail_url ?? null}
            />
        </div>
    {:else if summaryLoading}
        <div class="h-20 rounded-3xl bg-slate-100/80 dark:bg-slate-800/60 border border-slate-200/60 dark:border-slate-700/60 animate-pulse"></div>
    {/if}

    <!-- Top Row: Hero & Histogram -->
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch">
        <div class="lg:col-span-7 h-full">
            {#if heroDetection}
                {#key heroDetection.frigate_event}
                    <div in:fly={{ y: 20, duration: 500 }} class="h-full">
                        <LatestDetectionHero 
                            detection={heroDetection} 
                            onclick={() => selectedEvent = heroDetection}
                            hideProgress={selectedEvent?.frigate_event === heroDetection.frigate_event}
                        />
                    </div>
                {/key}
            {:else}
                <div class="h-full min-h-[320px] card-base rounded-3xl flex items-center justify-center border-2 border-dashed border-slate-200/80 dark:border-slate-700/60">
                    <p class="text-slate-400">{$_('dashboard.waiting_first_visitor')}</p>
                </div>
            {/if}
        </div>
        <div class="lg:col-span-5 flex flex-col gap-6 h-full">
            {#if summary}
                <div in:fade={{ duration: 800 }}>
                    <DailyHistogram data={summary.hourly_distribution} />
                </div>
            {:else if summaryLoading}
                <div class="min-h-[220px] rounded-3xl bg-slate-100/80 dark:bg-slate-800/60 border border-slate-200/60 dark:border-slate-700/60 animate-pulse"></div>
            {/if}
            {#if birdnetEnabled}
                <div in:fade={{ duration: 800, delay: 200 }} class="flex-1 min-h-[300px]">
                    <RecentAudio />
                </div>
            {/if}
        </div>
    </div>

    <!-- Middle Row: Top Visitors -->
    {#if summary && summary.top_species.length > 0}
        <div in:fade={{ duration: 500, delay: 200 }}>
            <TopVisitors 
                species={summary.top_species} 
                onSpeciesClick={handleSpeciesSummaryClick}
            />
        </div>
    {:else if summaryLoading}
        <div class="min-h-[200px] rounded-3xl bg-slate-100/80 dark:bg-slate-800/60 border border-slate-200/60 dark:border-slate-700/60 animate-pulse"></div>
    {/if}

    <!-- Bottom Row: Recent Feed -->
    <div class="space-y-6">
        <div class="flex items-center justify-between border-b border-slate-200/70 dark:border-slate-700/50 pb-3">
            <div class="flex items-center gap-3">
                <h2 class="text-[11px] font-black uppercase tracking-[0.2em] text-slate-500 dark:text-slate-400">{$_('dashboard.discovery_feed')}</h2>
                <span class="text-[10px] font-semibold text-slate-600 dark:text-slate-400 bg-slate-100 dark:bg-slate-800/60 px-2.5 py-0.5 rounded-full border border-slate-200/60 dark:border-slate-700/50">{$_('dashboard.showing_last_3_days')}</span>
            </div>
            <button onclick={() => onnavigate?.('/events')} class="text-[10px] font-black uppercase tracking-widest text-teal-600 dark:text-teal-400 hover:text-teal-700 dark:hover:text-teal-300 transition-colors">{$_('dashboard.see_full_history')}</button>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
            {#if detectionsStore.detections.length > 0}
                {#each visibleFeedDetections as detection, index (detection.frigate_event || detection.id)}
                    <div in:fly={{ y: 20, duration: 400 }}>
                        <DetectionCard 
                            {detection} 
                            {index}
                            onclick={() => selectedEvent = detection} 
                            onPlay={() => {
                                videoEventId = detection.frigate_event;
                                videoPlayIntent = 'user';
                                showVideo = true;
                                selectedEvent = null;
                            }}
                            onFetchFullVisit={recordingClipFetchEnabled ? () => handleFetchFullVisit(detection) : undefined}
                            fullVisitAvailable={fullVisitAvailability[detection.frigate_event] === 'available'}
                            fullVisitFetched={fullVisitFetchState[detection.frigate_event] === 'ready'}
                            fullVisitFetchState={fullVisitFetchState[detection.frigate_event] ?? 'idle'}
                            hideProgress={selectedEvent?.frigate_event === detection.frigate_event}
                        />
                    </div>
                {/each}
            {:else if detectionsStore.isLoading}
                {#each Array(4) as _, index (index)}
                    <div class="min-h-[220px] rounded-3xl bg-slate-100/80 dark:bg-slate-800/60 border border-slate-200/60 dark:border-slate-700/60 animate-pulse"></div>
                {/each}
            {:else}
                <div class="col-span-full py-12 flex flex-col items-center justify-center text-center bg-white/50 dark:bg-slate-800/20 rounded-3xl border border-dashed border-slate-200 dark:border-slate-700/50">
                    <div class="w-16 h-16 mb-4 rounded-full bg-slate-100 dark:bg-slate-800/50 flex items-center justify-center text-slate-400 dark:text-slate-500">
                        <svg class="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                        </svg>
                    </div>
                    <p class="text-slate-500 dark:text-slate-400 font-medium">{$_('dashboard.no_detections')}</p>
                </div>
            {/if}
        </div>
    </div>
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
