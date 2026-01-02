<script lang="ts">
    import DetectionCard from '../components/DetectionCard.svelte';
    import SpeciesDetailModal from '../components/SpeciesDetailModal.svelte';
    import VideoPlayer from '../components/VideoPlayer.svelte';
    import type { Detection, WildlifeClassification } from '../api';
    import { getThumbnailUrl, deleteDetection, hideDetection, classifyWildlife, updateDetectionSpecies, analyzeDetection } from '../api';
    import { settingsStore } from '../stores/settings';

    interface Props {
        detections: Detection[];
        totalDetectionsToday?: number;
        ondelete?: (eventId: string) => void;
        onhide?: (eventId: string) => void;
        onnavigate?: (path: string) => void;
    }

    let { detections, totalDetectionsToday = 0, ondelete, onhide, onnavigate }: Props = $props();

    let selectedEvent = $state<Detection | null>(null);
    let selectedSpecies = $state<string | null>(null);
    let deleting = $state(false);
    let hiding = $state(false);
    let classifyingWildlife = $state(false);
    let showWildlifeResults = $state(false);
    let wildlifeResults = $state<WildlifeClassification[]>([]);
    let applyingWildlife = $state(false);

    // AI Analysis state
    let analyzingAI = $state(false);
    let aiAnalysis = $state<string | null>(null);

    // Video playback state
    let showVideo = $state(false);

    // Derive hasClip from selected event
    let selectedHasClip = $derived(selectedEvent?.has_clip ?? false);

    // Reset wildlife results and video when switching detections
    $effect(() => {
        if (selectedEvent) {
            showWildlifeResults = false;
            wildlifeResults = [];
            showVideo = false;
            aiAnalysis = null;
        }
    });

    // Compute stats from current detections
    let topSpecies = $derived.by(() => {
        const counts: Record<string, number> = {};
        detections.forEach(d => {
            counts[d.display_name] = (counts[d.display_name] || 0) + 1;
        });
        const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]);
        return sorted.length > 0 ? sorted[0][0] : null;
    });

    let uniqueSpeciesCount = $derived.by(() => {
        return new Set(detections.map(d => d.display_name)).size;
    });

    async function handleDelete() {
        if (!selectedEvent) return;
        if (!confirm(`Delete this ${selectedEvent.display_name} detection?`)) return;

        deleting = true;
        try {
            await deleteDetection(selectedEvent.frigate_event);
            const eventId = selectedEvent.frigate_event;
            selectedEvent = null;
            ondelete?.(eventId);
        } catch (e) {
            console.error('Failed to delete detection', e);
            alert('Failed to delete detection');
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
                // Remove from view when hidden (dashboard doesn't show hidden detections)
                const eventId = selectedEvent.frigate_event;
                selectedEvent = null;
                onhide?.(eventId);
            }
        } catch (e) {
            console.error('Failed to hide detection', e);
            alert('Failed to hide detection');
        } finally {
            hiding = false;
        }
    }

    function viewAllEvents() {
        onnavigate?.('/events');
    }

    async function handleClassifyWildlife() {
        if (!selectedEvent) return;

        classifyingWildlife = true;
        showWildlifeResults = false;
        wildlifeResults = [];

        try {
            const result = await classifyWildlife(selectedEvent.frigate_event);
            wildlifeResults = result.classifications;
            showWildlifeResults = true;
        } catch (e) {
            console.error('Failed to classify wildlife', e);
            alert('Failed to identify animal. Make sure the wildlife model is downloaded.');
        } finally {
            classifyingWildlife = false;
        }
    }

    async function applyWildlifeResult(label: string) {
        if (!selectedEvent) return;

        applyingWildlife = true;
        try {
            await updateDetectionSpecies(selectedEvent.frigate_event, label);
            // Update the local detection
            selectedEvent.display_name = label;
            showWildlifeResults = false;
            wildlifeResults = [];
        } catch (e) {
            console.error('Failed to apply wildlife classification', e);
            alert('Failed to update species');
        } finally {
            applyingWildlife = false;
        }
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
            alert('AI Analysis failed. Make sure your API key is configured in Settings.');
        } finally {
            analyzingAI = false;
        }
    }
</script>

<!-- Header with stats -->
<div class="mb-6">
    <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
        <h2 class="text-2xl font-bold text-slate-900 dark:text-white">Live Detections</h2>
        <button
            onclick={viewAllEvents}
            class="inline-flex items-center gap-2 text-sm font-medium text-teal-600 dark:text-teal-400
                   hover:text-teal-700 dark:hover:text-teal-300 transition-colors"
        >
            View all detections
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
            </svg>
        </button>
    </div>

    <!-- Stats Cards -->
    <div class="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
        <div class="bg-white dark:bg-slate-800 rounded-xl p-4 border border-slate-200 dark:border-slate-700 shadow-sm relative overflow-hidden">
            <div class="absolute top-2 right-2 text-teal-500/10 dark:text-teal-400/10">
                <svg class="w-12 h-12" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
            </div>
            <p class="text-2xl font-bold text-teal-600 dark:text-teal-400 relative z-10">{totalDetectionsToday}</p>
            <p class="text-sm text-slate-500 dark:text-slate-400 relative z-10">Today's Detections</p>
        </div>
        <div class="bg-white dark:bg-slate-800 rounded-xl p-4 border border-slate-200 dark:border-slate-700 shadow-sm relative overflow-hidden">
            <div class="absolute top-2 right-2 text-slate-500/10 dark:text-slate-400/10">
                <svg class="w-12 h-12" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" /></svg>
            </div>
            <p class="text-2xl font-bold text-slate-900 dark:text-white relative z-10">{detections.length}</p>
            <p class="text-sm text-slate-500 dark:text-slate-400 relative z-10">Showing Recent</p>
        </div>
        <div class="bg-white dark:bg-slate-800 rounded-xl p-4 border border-slate-200 dark:border-slate-700 shadow-sm relative overflow-hidden">
            <div class="absolute top-2 right-2 text-slate-500/10 dark:text-slate-400/10">
                <svg class="w-12 h-12" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 20l4-16m2 16l4-16M6 9h14M4 15h14" /></svg>
            </div>
            <p class="text-2xl font-bold text-slate-900 dark:text-white relative z-10">{uniqueSpeciesCount}</p>
            <p class="text-sm text-slate-500 dark:text-slate-400 relative z-10">Species Seen</p>
        </div>
        <div class="bg-white dark:bg-slate-800 rounded-xl p-4 border border-slate-200 dark:border-slate-700 shadow-sm relative overflow-hidden">
            <div class="absolute top-2 right-2 text-slate-500/10 dark:text-slate-400/10">
                <svg class="w-12 h-12" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z" /></svg>
            </div>
            <p class="text-lg font-bold text-slate-900 dark:text-white truncate relative z-10" title={topSpecies || 'N/A'}>
                {topSpecies || 'N/A'}
            </p>
            <p class="text-sm text-slate-500 dark:text-slate-400 relative z-10">Most Common</p>
        </div>
    </div>
</div>

<div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
    {#each detections as detection (detection.frigate_event || detection.id)}
        <DetectionCard {detection} onclick={() => selectedEvent = detection} />
    {/each}

    {#if detections.length === 0}
        <div class="col-span-full text-center py-16 text-slate-500 dark:text-slate-400 bg-white/80 dark:bg-slate-800/50 rounded-2xl shadow-card dark:shadow-card-dark border border-slate-200/80 dark:border-slate-700/50 backdrop-blur-sm">
            <div class="flex flex-col items-center justify-center">
                <div class="w-16 h-16 mb-4 rounded-full bg-slate-100 dark:bg-slate-700/50 flex items-center justify-center">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-8 w-8 text-slate-400 dark:text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
                    </svg>
                </div>
                <p class="text-lg font-semibold text-slate-700 dark:text-slate-300">No detections yet</p>
                <p class="text-sm mt-1">Waiting for birds to visit...</p>
            </div>
        </div>
    {/if}
</div>

<!-- Event Detail Modal -->
{#if selectedEvent}
    <div
        class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
        onclick={() => selectedEvent = null}
        onkeydown={(e) => e.key === 'Escape' && (selectedEvent = null)}
        role="dialog"
        aria-modal="true"
        tabindex="-1"
    >
        <div
            class="bg-white dark:bg-slate-800 rounded-2xl shadow-2xl max-w-lg w-full max-h-[90vh] overflow-hidden
                   border border-slate-200 dark:border-slate-700"
            onclick={(e) => e.stopPropagation()}
            role="document"
        >
            <!-- Image with overlay -->
            <div class="relative aspect-video bg-slate-100 dark:bg-slate-700">
                <img
                    src={getThumbnailUrl(selectedEvent.frigate_event)}
                    alt={selectedEvent.display_name}
                    class="w-full h-full object-cover"
                />
                <!-- Gradient overlay with species name -->
                <div class="absolute inset-0 bg-gradient-to-t from-black/70 via-transparent to-transparent"></div>
                <div class="absolute bottom-0 left-0 right-0 p-4">
                    <h3 class="text-2xl font-bold text-white drop-shadow-lg">
                        {selectedEvent.display_name}
                    </h3>
                    <p class="text-white/80 text-sm mt-1">
                        {new Date(selectedEvent.detection_time).toLocaleDateString(undefined, {
                            weekday: 'short', month: 'short', day: 'numeric', year: 'numeric'
                        })} at {new Date(selectedEvent.detection_time).toLocaleTimeString(undefined, {
                            hour: '2-digit', minute: '2-digit'
                        })}
                    </p>
                </div>
                <!-- Play Video Button (shows when clip is available) -->
                {#if selectedHasClip}
                    <button
                        type="button"
                        onclick={() => showVideo = true}
                        class="absolute inset-0 flex items-center justify-center
                               bg-black/0 hover:bg-black/30 transition-colors duration-200
                               group/play focus:outline-none"
                        aria-label="Play video clip"
                    >
                        <div class="w-16 h-16 rounded-full bg-white/90 dark:bg-slate-800/90
                                    flex items-center justify-center shadow-lg
                                    opacity-70 group-hover/play:opacity-100
                                    transform scale-90 group-hover/play:scale-100
                                    transition-all duration-200">
                            <svg xmlns="http://www.w3.org/2000/svg" class="w-7 h-7 text-teal-600 dark:text-teal-400 ml-1" viewBox="0 0 24 24" fill="currentColor">
                                <path d="M8 5v14l11-7z"/>
                            </svg>
                        </div>
                    </button>
                {/if}
                <!-- Close button -->
                <button
                    onclick={() => selectedEvent = null}
                    class="absolute top-3 right-3 w-8 h-8 rounded-full bg-black/40 text-white/90
                           flex items-center justify-center hover:bg-black/60 transition-colors"
                    aria-label="Close"
                >
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                </button>
            </div>

            <div class="p-5">
                <!-- Confidence bar -->
                <div class="mb-4">
                    <div class="flex items-center justify-between mb-1.5">
                        <span class="text-sm font-medium text-slate-600 dark:text-slate-400">Confidence</span>
                        <span class="text-sm font-bold text-slate-900 dark:text-white">
                            {(selectedEvent.score * 100).toFixed(1)}%
                        </span>
                    </div>
                    <div class="h-2 bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden">
                        <div
                            class="h-full rounded-full transition-all duration-500
                                   {selectedEvent.score >= 0.8 ? 'bg-emerald-500' :
                                    selectedEvent.score >= 0.6 ? 'bg-teal-500' :
                                    selectedEvent.score >= 0.4 ? 'bg-amber-500' : 'bg-red-500'}"
                            style="width: {selectedEvent.score * 100}%"
                        ></div>
                    </div>
                </div>

                <!-- Camera info -->
                <div class="flex items-center justify-between mb-5">
                    <div class="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                                  d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                        </svg>
                        <span class="font-medium">{selectedEvent.camera_name}</span>
                    </div>
                    
                    {#if selectedEvent.temperature !== undefined && selectedEvent.temperature !== null}
                        <div class="flex items-center gap-1 text-sm text-slate-500 dark:text-slate-400">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                            </svg>
                            <span>{selectedEvent.temperature.toFixed(1)}°C</span>
                            {#if selectedEvent.weather_condition}
                                <span class="opacity-70 ml-1">• {selectedEvent.weather_condition}</span>
                            {/if}
                        </div>
                    {/if}
                </div>

                <!-- AI Analysis Button -->
                {#if $settingsStore?.llm_enabled}
                    <div class="mb-5">
                        {#if !aiAnalysis}
                            <button
                                onclick={handleAIAnalysis}
                                disabled={analyzingAI}
                                class="w-full px-4 py-2.5 text-sm font-medium text-teal-700 dark:text-teal-300
                                       bg-teal-50 dark:bg-teal-900/20 rounded-lg
                                       hover:bg-teal-100 dark:hover:bg-teal-900/40 transition-colors
                                       disabled:opacity-50 disabled:cursor-not-allowed
                                       flex items-center justify-center gap-2"
                            >
                                {#if analyzingAI}
                                    <svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                    </svg>
                                    AI is analyzing...
                                {:else}
                                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                                              d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.989-2.386l-.548-.547z" />
                                    </svg>
                                    Ask AI Naturalist
                                {/if}
                            </button>
                        {:else}
                            <div class="bg-teal-50 dark:bg-teal-900/10 rounded-xl p-4 border border-teal-100 dark:border-teal-900/30 animate-in fade-in slide-in-from-top-2">
                                <div class="flex items-center gap-2 mb-2 text-teal-700 dark:text-teal-400">
                                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.989-2.386l-.548-.547z" />
                                    </svg>
                                    <span class="text-sm font-bold uppercase tracking-wider">AI Analysis</span>
                                </div>
                                <p class="text-sm text-slate-700 dark:text-slate-300 leading-relaxed whitespace-pre-wrap">
                                    {aiAnalysis}
                                </p>
                                <button
                                    onclick={() => aiAnalysis = null}
                                    class="mt-3 text-xs text-teal-600 dark:text-teal-400 hover:underline font-medium"
                                >
                                    Reset Analysis
                                </button>
                            </div>
                        {/if}
                    </div>
                {/if}

                <!-- Wildlife Classification Section -->
                <div class="mb-5">
                    <button
                        onclick={handleClassifyWildlife}
                        disabled={classifyingWildlife}
                        class="w-full px-4 py-2.5 text-sm font-medium text-amber-700 dark:text-amber-300
                               bg-amber-50 dark:bg-amber-900/20 rounded-lg
                               hover:bg-amber-100 dark:hover:bg-amber-900/40 transition-colors
                               disabled:opacity-50 disabled:cursor-not-allowed
                               flex items-center justify-center gap-2"
                    >
                        {#if classifyingWildlife}
                            <svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                            </svg>
                            Identifying...
                        {:else}
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                                      d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                            </svg>
                            Identify Animal
                        {/if}
                    </button>

                    <!-- Wildlife Results Dropdown -->
                    {#if showWildlifeResults && wildlifeResults.length > 0}
                        <div class="mt-2 bg-slate-50 dark:bg-slate-700/50 rounded-lg p-3 border border-slate-200 dark:border-slate-600">
                            <p class="text-xs font-medium text-slate-500 dark:text-slate-400 mb-2">
                                Click a result to apply it as the species:
                            </p>
                            <div class="space-y-1">
                                {#each wildlifeResults as result}
                                    <button
                                        onclick={() => applyWildlifeResult(result.label)}
                                        disabled={applyingWildlife}
                                        class="w-full text-left px-3 py-2 text-sm rounded-md
                                               bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-600
                                               hover:border-amber-400 dark:hover:border-amber-500 hover:bg-amber-50 dark:hover:bg-amber-900/20
                                               transition-colors disabled:opacity-50 disabled:cursor-not-allowed
                                               flex items-center justify-between"
                                    >
                                        <span class="font-medium text-slate-700 dark:text-slate-200">{result.label}</span>
                                        <span class="text-xs text-slate-500 dark:text-slate-400">
                                            {(result.score * 100).toFixed(1)}%
                                        </span>
                                    </button>
                                {/each}
                            </div>
                            <button
                                onclick={() => { showWildlifeResults = false; wildlifeResults = []; }}
                                class="mt-2 text-xs text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
                            >
                                Dismiss results
                            </button>
                        </div>
                    {/if}
                </div>

                <!-- Action buttons -->
                <div class="flex gap-2">
                    <button
                        onclick={() => {
                            selectedSpecies = selectedEvent?.display_name ?? null;
                            selectedEvent = null;
                        }}
                        class="flex-1 px-4 py-2.5 text-sm font-medium text-white
                               bg-teal-500 hover:bg-teal-600 rounded-lg transition-colors
                               flex items-center justify-center gap-2"
                    >
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                                  d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        Species Info
                    </button>
                    <button
                        onclick={handleHide}
                        disabled={hiding}
                        class="px-4 py-2.5 text-sm font-medium text-slate-600 dark:text-slate-400
                               bg-slate-100 dark:bg-slate-700 rounded-lg
                               hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors
                               disabled:opacity-50 disabled:cursor-not-allowed
                               flex items-center justify-center gap-2"
                    >
                        {#if hiding}
                            <svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                            </svg>
                        {:else}
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                                      d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                            </svg>
                        {/if}
                        {hiding ? 'Hiding...' : 'Hide'}
                    </button>
                    <button
                        onclick={handleDelete}
                        disabled={deleting}
                        class="px-4 py-2.5 text-sm font-medium text-red-600 dark:text-red-400
                               bg-red-50 dark:bg-red-900/20 rounded-lg
                               hover:bg-red-100 dark:hover:bg-red-900/40 transition-colors
                               disabled:opacity-50 disabled:cursor-not-allowed
                               flex items-center justify-center gap-2"
                    >
                        {#if deleting}
                            <svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                            </svg>
                        {:else}
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                                      d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                            </svg>
                        {/if}
                        {deleting ? 'Deleting...' : 'Delete'}
                    </button>
                </div>
            </div>
        </div>
    </div>
{/if}

<!-- Species Detail Modal -->
{#if selectedSpecies}
    <SpeciesDetailModal
        speciesName={selectedSpecies}
        onclose={() => selectedSpecies = null}
    />
{/if}

<!-- Video Player Modal -->
{#if showVideo && selectedEvent}
    <VideoPlayer
        frigateEvent={selectedEvent.frigate_event}
        onClose={() => showVideo = false}
    />
{/if}