<script lang="ts">
    import { onMount } from 'svelte';
    import { fade, fly } from 'svelte/transition';
    import DetectionCard from '../components/DetectionCard.svelte';
    import SpeciesDetailModal from '../components/SpeciesDetailModal.svelte';
    import VideoPlayer from '../components/VideoPlayer.svelte';
    import DailyHistogram from '../components/DailyHistogram.svelte';
    import TopVisitors from '../components/TopVisitors.svelte';
    import LatestDetectionHero from '../components/LatestDetectionHero.svelte';
    import StatsRibbon from '../components/StatsRibbon.svelte';
    import ReclassificationOverlay from '../components/ReclassificationOverlay.svelte';
    import { detectionsStore } from '../stores/detections.svelte';
    import type { Detection, DailySummary } from '../api';
    import { getThumbnailUrl, deleteDetection, hideDetection, updateDetectionSpecies, analyzeDetection, fetchDailySummary, fetchClassifierLabels, reclassifyDetection } from '../api';
    import { settingsStore } from '../stores/settings';

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
    let llmEnabled = $derived($settingsStore?.llm_enabled ?? false);

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
        const settings = $settingsStore;
        const showCommon = settings?.display_common_names ?? true;
        const preferSci = settings?.scientific_name_primary ?? false;

        let primary: string;
        let secondary: string | null = null;

        if (!showCommon) {
            primary = (selectedEvent.scientific_name || selectedEvent.display_name) as string;
            secondary = null;
        } else if (preferSci) {
            primary = (selectedEvent.scientific_name || selectedEvent.display_name) as string;
            secondary = (selectedEvent.common_name || null) as string | null;
        } else {
            primary = (selectedEvent.common_name || selectedEvent.display_name) as string;
            secondary = (selectedEvent.scientific_name || null) as string | null;
        }

        return {
            primary,
            secondary: (secondary && secondary !== primary) ? secondary : null
        };
    });

    let modalPrimaryName = $derived(modalNaming.primary);
    let modalSubName = $derived(modalNaming.secondary);

    // Derive audio confirmations count from recent detections
    let audioConfirmations = $derived(detectionsStore.detections.filter(d => d.audio_confirmed).length);

    // Derive most seen species name based on preference
    let mostSeenName = $derived.by(() => {
        const top = summary?.top_species[0];
        if (!top) return null;
        
        const settings = $settingsStore;
        const showCommon = settings?.display_common_names ?? true;
        const preferSci = settings?.scientific_name_primary ?? false;

        if (!showCommon) return top.scientific_name || top.species;
        if (preferSci) return top.scientific_name || top.species;
        return top.common_name || top.species;
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
        try {
            await reclassifyDetection(selectedEvent.frigate_event, selectedEvent.has_clip ? 'video' : 'snapshot');
        } catch (e: any) {
            alert(e.message || 'Failed to start reclassification');
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
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div class="lg:col-span-2">
            {#if heroDetection}
                {#key heroDetection.frigate_event}
                    <div in:fly={{ y: 20, duration: 500 }}>
                        <LatestDetectionHero 
                            detection={heroDetection} 
                            onclick={() => selectedEvent = heroDetection}
                            hideProgress={selectedEvent?.frigate_event === heroDetection.frigate_event}
                        />
                    </div>
                {/key}
            {:else}
                <div class="h-80 bg-slate-100 dark:bg-slate-800 rounded-2xl flex items-center justify-center border-4 border-dashed border-slate-200 dark:border-slate-700">
                    <p class="text-slate-400">Waiting for the first visitor of the day...</p>
                </div>
            {/if}
        </div>
        <div>
            {#if summary}
                <div in:fade={{ duration: 800 }}>
                    <DailyHistogram data={summary.hourly_distribution} />
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
                        hideProgress={selectedEvent?.frigate_event === detection.frigate_event}
                    />
                </div>
            {/each}
        </div>
    </div>
</div>

<!-- Event Detail Modal -->
{#if selectedEvent}
    <div class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm" onclick={() => selectedEvent = null} onkeydown={(e) => e.key === 'Escape' && (selectedEvent = null)} role="dialog" aria-modal="true" tabindex="-1">
        <div class="relative bg-white dark:bg-slate-800 rounded-3xl shadow-2xl max-w-lg w-full max-h-[90vh] overflow-hidden border border-white/20" onclick={(e) => e.stopPropagation()} onkeydown={(e) => e.stopPropagation()} role="document" tabindex="-1">
            
            <!-- Reclassification Overlay (covers entire modal content) -->
            {#if modalReclassifyProgress}
                <ReclassificationOverlay progress={modalReclassifyProgress} />
            {/if}

            <div class="relative aspect-video bg-slate-100 dark:bg-slate-700">
                <img src={getThumbnailUrl(selectedEvent.frigate_event)} alt={selectedEvent.display_name} class="w-full h-full object-cover" />
                <div class="absolute inset-0 bg-gradient-to-t from-black/70 via-transparent to-transparent"></div>
                <div class="absolute bottom-0 left-0 right-0 p-6">
                    <h3 class="text-2xl font-black text-white drop-shadow-lg leading-tight">{modalPrimaryName}</h3>
                    {#if modalSubName && modalSubName !== modalPrimaryName}<p class="text-white/70 text-sm italic drop-shadow -mt-1 mb-1">{modalSubName}</p>{/if}
                    <p class="text-white/50 text-[10px] uppercase font-bold tracking-widest mt-2">{new Date(selectedEvent.detection_time).toLocaleString()}</p>
                </div>
                {#if selectedEvent.has_clip}
                    <button type="button" onclick={() => showVideo = true} class="absolute inset-0 flex items-center justify-center bg-black/0 hover:bg-black/20 transition-all group/play focus:outline-none"><div class="w-16 h-16 rounded-full bg-white/90 dark:bg-slate-800/90 flex items-center justify-center shadow-lg opacity-70 group-hover/play:opacity-100 transform scale-90 group-hover/play:scale-100 transition-all duration-200"><svg xmlns="http://www.w3.org/2000/svg" class="w-7 h-7 text-teal-600 dark:text-teal-400 ml-1" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg></div></button>
                {/if}
                <button onclick={() => selectedEvent = null} class="absolute top-4 right-4 w-8 h-8 rounded-full bg-black/40 text-white flex items-center justify-center hover:bg-black/60 transition-colors" aria-label="Close"><svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12" /></svg></button>
            </div>

            <div class="p-6 space-y-6">
                <div>
                    <div class="flex items-center justify-between mb-2"><span class="text-xs font-bold text-slate-500 uppercase tracking-widest">Confidence</span><span class="text-sm font-black text-slate-900 dark:text-white">{((selectedEvent.score || 0) * 100).toFixed(1)}%</span></div>
                    <div class="h-2 bg-slate-100 dark:bg-slate-700 rounded-full overflow-hidden"><div class="h-full rounded-full transition-all duration-700 {(selectedEvent.score || 0) >= 0.8 ? 'bg-emerald-500' : 'bg-teal-500'}" style="width: {(selectedEvent.score || 0) * 100}%"></div></div>
                </div>

                <div class="grid grid-cols-2 gap-4">
                    <div class="flex items-center gap-3 p-3 rounded-xl bg-slate-50 dark:bg-slate-900/40 border border-slate-100 dark:border-slate-700/50"><svg class="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg><span class="text-sm font-bold text-slate-700 dark:text-slate-300 truncate">{selectedEvent.camera_name}</span></div>
                    {#if selectedEvent.temperature !== undefined && selectedEvent.temperature !== null}<div class="flex items-center gap-3 p-3 rounded-xl bg-slate-50 dark:bg-slate-900/40 border border-slate-100 dark:border-slate-700/50"><svg class="w-4 h-4 text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" /></svg><span class="text-sm font-bold text-slate-700 dark:text-slate-300">{selectedEvent.temperature?.toFixed(1)}°C</span></div>{/if}
                </div>

                {#if llmEnabled && aiAnalysis}
                    <div class="p-4 rounded-2xl bg-teal-500/5 border border-teal-500/10 animate-in fade-in slide-in-from-top-2">
                        <p class="text-[10px] font-black text-teal-600 dark:text-teal-400 uppercase tracking-[0.2em] mb-2">AI Naturalist Insight</p>
                        <p class="text-sm text-slate-700 dark:text-slate-300 leading-relaxed">{aiAnalysis}</p>
                    </div>
                {:else if llmEnabled && !analyzingAI}
                    <button 
                        onclick={handleAIAnalysis}
                        class="w-full py-3 px-4 bg-teal-500/10 hover:bg-teal-500/20 text-teal-600 dark:text-teal-400 font-bold rounded-xl transition-all flex items-center justify-center gap-2 border border-teal-500/20"
                    >
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                        </svg>
                        Ask AI Naturalist
                    </button>
                {:else if analyzingAI}
                    <div class="w-full py-3 px-4 bg-slate-100 dark:bg-slate-800 text-slate-500 font-bold rounded-xl flex items-center justify-center gap-3 animate-pulse">
                        <div class="w-4 h-4 border-2 border-teal-500 border-t-transparent rounded-full animate-spin"></div>
                        Analyzing behavior...
                    </div>
                {/if}

                <div class="flex gap-2">
                    <button 
                        onclick={handleReclassify} 
                        class="flex-1 py-3 px-4 bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200 font-bold rounded-xl hover:bg-slate-200 transition-colors"
                    >
                        Reclassify
                    </button>
                    
                    <div class="relative flex-1">
                        <button 
                            onclick={() => showTagDropdown = !showTagDropdown} 
                            disabled={updatingTag}
                            class="w-full py-3 px-4 bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200 font-bold rounded-xl hover:bg-slate-200 transition-colors disabled:opacity-50"
                        >
                            {updatingTag ? 'Updating...' : 'Manual Tag'}
                        </button>

                        {#if showTagDropdown}
                            <div class="absolute bottom-full left-0 right-0 mb-3 bg-white dark:bg-slate-800 rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-700 max-h-80 overflow-hidden z-50 animate-in fade-in slide-in-from-bottom-2">
                                <div class="p-3 border-b border-slate-100 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50">
                                    <input 
                                        type="text" 
                                        bind:value={tagSearchQuery} 
                                        placeholder="Search species..." 
                                        class="w-full px-4 py-2 text-sm rounded-xl border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-700 text-slate-900 dark:text-white focus:ring-2 focus:ring-teal-500 focus:border-transparent outline-none"
                                        onclick={(e) => e.stopPropagation()}
                                    />
                                </div>
                                <div class="max-h-56 overflow-y-auto p-1">
                                    {#each filteredLabels as label}
                                        <button 
                                            onclick={() => handleManualTag(label)}
                                            class="w-full px-4 py-2.5 text-left text-sm font-medium rounded-lg transition-all hover:bg-teal-50 dark:hover:bg-teal-900/20 hover:text-teal-600 dark:hover:text-teal-400 {label === selectedEvent?.display_name ? 'bg-teal-500/10 text-teal-600 font-bold' : 'text-slate-600 dark:text-slate-300'}"
                                        >
                                            {label}
                                        </button>
                                    {/each}
                                    {#if filteredLabels.length === 0}
                                        <p class="px-4 py-6 text-sm text-slate-400 italic text-center">No matching species found</p>
                                    {/if}
                                </div>
                            </div>
                        {/if}
                    </div>
                </div>

                <div class="flex gap-2 pt-2">
                    <button onclick={handleDelete} class="p-3 rounded-xl bg-red-50 dark:bg-red-900/20 text-red-600 hover:bg-red-100 transition-colors" title="Delete Detection"><svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg></button>
                    <button onclick={handleHide} class="p-3 rounded-xl bg-slate-100 dark:bg-slate-700 text-slate-600 hover:bg-slate-200 transition-colors" title="Hide Detection"><svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" /></svg></button>
                    <button onclick={() => { selectedSpecies = selectedEvent?.display_name ?? null; selectedEvent = null; }} class="flex-1 bg-teal-500 hover:bg-teal-600 text-white font-black uppercase tracking-widest text-xs rounded-xl transition-all shadow-lg shadow-teal-500/20">Species Info</button>
                </div>
            </div>
        </div>
    </div>
{/if}

{#if selectedSpecies}<SpeciesDetailModal speciesName={selectedSpecies} onclose={() => selectedSpecies = null} />{/if}
{#if showVideo && selectedEvent}<VideoPlayer frigateEvent={selectedEvent.frigate_event} onClose={() => showVideo = false} />{/if}