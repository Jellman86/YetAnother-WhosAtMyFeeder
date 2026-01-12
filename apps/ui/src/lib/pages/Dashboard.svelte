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
    import type { Detection, DailySummary } from '../api';
    import { getThumbnailUrl, deleteDetection, hideDetection, updateDetectionSpecies, analyzeDetection, fetchDailySummary, fetchClassifierLabels, reclassifyDetection } from '../api';
    import { settingsStore } from '../stores/settings.svelte';

    import { getBirdNames } from '../naming';

    interface Props {
        onnavigate?: (path: string) => void;
    }

    let { onnavigate }: Props = $props();

    let summary = $state<DailySummary | null>(null);
    let selectedEvent = $state<Detection | null>(null);
    let selectedSpecies = $state<string | null>(null);
    let deleting = $state(false);
    let hiding = $state(false);

    // Settings state
    let llmEnabled = $state(false);
    let showCommon = $state(true);
    let preferSci = $state(false);
    $effect(() => {
        llmEnabled = settingsStore.settings?.llm_enabled ?? false;
        showCommon = settingsStore.settings?.display_common_names ?? true;
        preferSci = settingsStore.settings?.scientific_name_primary ?? false;
    });

    // AI Analysis state
    let analyzingAI = $state(false);
    let aiAnalysis = $state<string | null>(null);

    // Video playback state
    let showVideo = $state(false);

    // Manual Tag state
    let classifierLabels = $state<string[]>([]);
    let tagSearchQuery = $state('');
    let showTagDropdown = $state(false);
    let updatingTag = $state(false);

    let filteredLabels = $derived(
        classifierLabels.filter(l => 
            l.toLowerCase().includes(tagSearchQuery.toLowerCase())
        ).slice(0, 50)
    );

    // Derive the hero detection (latest one)
    let heroDetection = $derived(detectionsStore.detections[0] || summary?.latest_detection || null);

    // Derive reclassification progress for the modal
    let modalReclassifyProgress = $derived(
        selectedEvent ? detectionsStore.getReclassificationProgress(selectedEvent.frigate_event) : undefined
    );

    // Derive naming logic for the modal
    let modalNaming = $derived.by(() => {
        if (!selectedEvent) return { primary: '', secondary: null };
        const showCommon = settingsStore.settings?.display_common_names ?? true;
        const preferSci = settingsStore.settings?.scientific_name_primary ?? false;
        return getBirdNames(selectedEvent, showCommon, preferSci);
    });

    let modalPrimaryName = $derived(modalNaming.primary);
    let modalSubName = $derived(modalNaming.secondary);

    // Derive audio confirmations count from recent detections
    let audioConfirmations = $derived(detectionsStore.detections.filter(d => d.audio_confirmed).length);

    // Derive most seen species name based on preference
    let mostSeenName = $derived.by(() => {
        const top = summary?.top_species[0];
        if (!top) return null;
        const showCommon = settingsStore.settings?.display_common_names ?? true;
        const preferSci = settingsStore.settings?.scientific_name_primary ?? false;
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
            console.error('Failed to load summary', e);
        }
    }

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

    async function handleReclassify() {
        if (!selectedEvent) return;
        const requestedStrategy = selectedEvent.has_clip ? 'video' : 'snapshot';
        try {
            const result = await reclassifyDetection(selectedEvent.frigate_event, requestedStrategy);

            // Check if backend used a different strategy (fallback occurred)
            if (result.actual_strategy && result.actual_strategy !== requestedStrategy) {
                toastStore.warning(`⚠️ Video not available - snapshot used instead`);
            }
        } catch (e: any) {
            console.error('Failed to start reclassification', e.message);
            toastStore.error(`Failed to reclassify: ${e.message || 'Unknown error'}`);
        }
    }

    async function handleManualTag(newSpecies: string) {
        if (!selectedEvent) return;
        updatingTag = true;
        try {
            await updateDetectionSpecies(selectedEvent.frigate_event, newSpecies);
            selectedEvent.display_name = newSpecies;
            // Optimistically update store
            detectionsStore.updateDetection({ ...selectedEvent, display_name: newSpecies });
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
        if (!confirm(`Delete this ${selectedEvent.display_name} detection?`)) return;
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

    function handleSpeciesSummaryClick(species: string) {
        onnavigate?.(`/events?species=${encodeURIComponent(species)}&date=today`);
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
                todayCount={detectionsStore.totalToday}
                uniqueSpecies={summary?.top_species.length ?? 0}
                mostSeenSpecies={mostSeenName}
                mostSeenCount={summary?.top_species[0]?.count ?? 0}
                {audioConfirmations}
            />
        </div>
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
                <div class="h-full min-h-[320px] bg-slate-100 dark:bg-slate-800 rounded-3xl flex items-center justify-center border-4 border-dashed border-slate-200 dark:border-slate-700">
                    <p class="text-slate-400">Waiting for the first visitor of the day...</p>
                </div>
            {/if}
        </div>
        <div class="lg:col-span-5 grid grid-cols-1 gap-6">
            {#if summary}
                <div in:fade={{ duration: 800 }}>
                    <DailyHistogram data={summary.hourly_distribution} />
                </div>
            {/if}
            {#if settingsStore.settings?.birdnet_enabled}
                <div in:fade={{ duration: 800, delay: 200 }}>
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
    {/if}

    <!-- Bottom Row: Recent Feed -->
    <div class="space-y-6">
        <div class="flex items-center justify-between">
            <h3 class="text-sm font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400"> Discovery Feed </h3>
            <button onclick={() => onnavigate?.('/events')} class="text-xs font-medium text-teal-600 dark:text-teal-400 hover:underline"> See full history </button>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
            {#each detectionsStore.detections.slice(1) as detection (detection.frigate_event || detection.id)}
                <div in:fly={{ y: 20, duration: 400 }}>
                    <DetectionCard 
                        {detection} 
                        onclick={() => selectedEvent = detection} 
                        onPlay={() => { selectedEvent = detection; showVideo = true; }}
                        hideProgress={selectedEvent?.frigate_event === detection.frigate_event}
                    />
                </div>
            {/each}
        </div>
    </div>
</div>

<!-- Event Detail Modal -->
{#if selectedEvent}
    <DetectionModal
        detection={selectedEvent}
        {classifierLabels}
        {llmEnabled}
        showVideoButton={true}
        onClose={() => selectedEvent = null}
        onReclassify={handleReclassify}
        onPlayVideo={() => showVideo = true}
        onViewSpecies={(species) => { selectedSpecies = species; selectedEvent = null; }}
    />
{/if}


{#if selectedSpecies}<SpeciesDetailModal speciesName={selectedSpecies} onclose={() => selectedSpecies = null} />{/if}
{#if showVideo && selectedEvent}<VideoPlayer frigateEvent={selectedEvent.frigate_event} onClose={() => showVideo = false} />{/if}