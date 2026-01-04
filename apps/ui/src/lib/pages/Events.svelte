<script lang="ts">
    import { onMount } from 'svelte';
    import {
        fetchEvents,
        fetchEventFilters,
        getThumbnailUrl,
        hideDetection,
        deleteDetection,
        fetchClassifierLabels,
        reclassifyDetection,
        updateDetectionSpecies,
        fetchHiddenCount,
        fetchEventsCount,
        analyzeDetection,
        type Detection,
        type EventFilters
    } from '../api';
    import { detectionsStore } from '../stores/detections.svelte';
    import { settingsStore } from '../stores/settings';
    import Pagination from '../components/Pagination.svelte';
    import DetectionCard from '../components/DetectionCard.svelte';
    import SpeciesDetailModal from '../components/SpeciesDetailModal.svelte';
    import VideoPlayer from '../components/VideoPlayer.svelte';
    import ReclassificationOverlay from '../components/ReclassificationOverlay.svelte';

    let events = $state<Detection[]>([]);
    let loading = $state(true);
    let error = $state<string | null>(null);
    let deleting = $state(false);
    let hiding = $state(false);

    // Filters and state
    let showHidden = $state(false);
    let hiddenCount = $state(0);
    let currentPage = $state(1);
    let pageSize = $state(24);
    let totalCount = $state(0);
    let totalPages = $derived(Math.ceil(totalCount / pageSize));
    let availableSpecies: string[] = $state([]);
    let availableCameras: string[] = $state([]);
    type DatePreset = 'all' | 'today' | 'week' | 'month' | 'custom';
    let datePreset = $state<DatePreset>('all');
    let customStartDate = $state('');
    let customEndDate = $state('');
    let speciesFilter = $state('');
    let cameraFilter = $state('');
    let sortOrder = $state<'newest' | 'oldest' | 'confidence'>('newest');

    let selectedEvent = $state<Detection | null>(null);
    let selectedSpecies = $state<string | null>(null);
    let classifierLabels = $state<string[]>([]);
    let tagSearchQuery = $state('');
    let showTagDropdown = $state(false);
    let updatingTag = $state(false);

    let analyzingAI = $state(false);
    let aiAnalysis = $state<string | null>(null);

    // Settings state
    let llmEnabled = $derived($settingsStore?.llm_enabled ?? false);

    let filteredLabels = $derived(
        classifierLabels.filter(l => 
            l.toLowerCase().includes(tagSearchQuery.toLowerCase())
        ).slice(0, 50)
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

    let modalReclassifyProgress = $derived(selectedEvent ? detectionsStore.getReclassificationProgress(selectedEvent.frigate_event) : undefined);
    let modalPrimaryName = $derived(modalNaming.primary);
    let modalSubName = $derived(modalNaming.secondary);

    let dateRange = $derived.by(() => {
        const today = new Date();
        const fmt = (d: Date) => d.toISOString().split('T')[0];
        if (datePreset === 'today') return { start: fmt(today), end: fmt(today) };
        if (datePreset === 'week') { const d = new Date(today); d.setDate(d.getDate() - 7); return { start: fmt(d), end: fmt(today) }; }
        if (datePreset === 'month') { const d = new Date(today); d.setDate(d.getDate() - 30); return { start: fmt(d), end: fmt(today) }; }
        if (datePreset === 'custom') return { start: customStartDate || undefined, end: customEndDate || undefined };
        return { start: undefined, end: undefined };
    });

    async function loadEvents() {
        loading = true;
        try {
            const range = dateRange;
            const [newEvents, countRes] = await Promise.all([
                fetchEvents({ limit: pageSize, offset: (currentPage - 1) * pageSize, startDate: range.start, endDate: range.end, species: speciesFilter || undefined, camera: cameraFilter || undefined, sort: sortOrder, includeHidden: showHidden }),
                fetchEventsCount({ startDate: range.start, endDate: range.end, species: speciesFilter || undefined, camera: cameraFilter || undefined, includeHidden: showHidden })
            ]);
            events = newEvents;
            totalCount = countRes.count;
        } catch (e) { error = 'Failed to load events'; } finally { loading = false; }
    }

    onMount(async () => {
        const params = new URLSearchParams(window.location.search);
        if (params.get('species')) speciesFilter = params.get('species')!;
        if (params.get('date')) datePreset = params.get('date') as any;
        try {
            const [filters, labels, hidden] = await Promise.all([
                fetchEventFilters(), 
                fetchClassifierLabels().catch(() => ({labels:[]})), 
                fetchHiddenCount().catch(() => ({hidden_count:0}))
            ]);
            availableSpecies = (filters as EventFilters).species;
            availableCameras = (filters as EventFilters).cameras;
            classifierLabels = labels.labels;
            hiddenCount = hidden.hidden_count;
        } catch {}
        await loadEvents();
    });

    // Reset state when switching events
    $effect(() => {
        if (selectedEvent) {
            showTagDropdown = false;
            tagSearchQuery = '';
            aiAnalysis = null;
            analyzingAI = false;
        }
    });

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

    async function handleReclassify() {
        if (!selectedEvent) return;
        try { 
            await reclassifyDetection(selectedEvent.frigate_event, selectedEvent.has_clip ? 'video' : 'snapshot'); 
        } catch (e: any) { 
            alert(e.message || 'Failed'); 
        }
    }

    async function handleManualTag(newSpecies: string) {
        if (!selectedEvent) return;
        updatingTag = true;
        try {
            await updateDetectionSpecies(selectedEvent.frigate_event, newSpecies);
            selectedEvent.display_name = newSpecies;
            // Update local list
            events = events.map(e => e.frigate_event === selectedEvent?.frigate_event ? { ...e, display_name: newSpecies } : e);
            detectionsStore.updateDetection({ ...selectedEvent, display_name: newSpecies });
            showTagDropdown = false;
        } catch (e) {
            console.error('Failed to update species', e);
        } finally {
            updatingTag = false;
        }
    }

    async function handleHide() {
        if (!selectedEvent) return;
        hiding = true;
        try {
            const result = await hideDetection(selectedEvent.frigate_event);
            if (result.is_hidden) {
                events = events.filter(e => e.frigate_event !== selectedEvent?.frigate_event);
                detectionsStore.removeDetection(selectedEvent.frigate_event, selectedEvent.detection_time);
                selectedEvent = null;
                hiddenCount++;
            }
        } catch {} finally { hiding = false; }
    }

    async function handleDelete() {
        if (!selectedEvent || !confirm('Delete?')) return;
        deleting = true;
        try {
            await deleteDetection(selectedEvent.frigate_event);
            events = events.filter(e => e.frigate_event !== selectedEvent?.frigate_event);
            detectionsStore.removeDetection(selectedEvent.frigate_event, selectedEvent.detection_time);
            selectedEvent = null;
        } catch {} finally { deleting = false; }
    }

    let showVideo = $state(false);
</script>

<div class="space-y-6">
    <div class="flex items-center justify-between">
        <h2 class="text-2xl font-bold text-slate-900 dark:text-white">Events</h2>
        <div class="text-sm text-slate-500">{totalCount} total</div>
    </div>

    <div class="flex flex-wrap gap-3">
        <select bind:value={datePreset} onchange={loadEvents} class="px-3 py-2 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-sm">
            <option value="all">All Time</option><option value="today">Today</option><option value="week">Week</option><option value="month">Month</option><option value="custom">Custom</option>
        </select>
        <select bind:value={speciesFilter} onchange={loadEvents} class="px-3 py-2 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-sm">
            <option value="">All Species</option>{#each availableSpecies as s}<option value={s}>{s}</option>{/each}
        </select>
        <select bind:value={cameraFilter} onchange={loadEvents} class="px-3 py-2 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-sm">
            <option value="">All Cameras</option>{#each availableCameras as c}<option value={c}>{c}</option>{/each}
        </select>
    </div>

    <Pagination {currentPage} {totalPages} totalItems={totalCount} itemsPerPage={pageSize} onPageChange={(p) => {currentPage=p; loadEvents()}} onPageSizeChange={(s) => {pageSize=s; currentPage=1; loadEvents()}} />

    <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
        {#each events as event (event.frigate_event)}
            <DetectionCard 
                detection={event} 
                onclick={() => selectedEvent = event} 
                hideProgress={selectedEvent?.frigate_event === event.frigate_event}
            />
        {/each}
    </div>
</div>

{#if selectedEvent}
    <div class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm" onclick={() => selectedEvent = null} onkeydown={(e) => e.key === 'Escape' && (selectedEvent = null)} role="dialog" aria-modal="true" tabindex="-1">
        <div class="relative bg-white dark:bg-slate-800 rounded-3xl shadow-2xl max-w-lg w-full max-h-[90vh] overflow-hidden border border-white/10" onclick={(e) => e.stopPropagation()} onkeydown={(e) => e.stopPropagation()} role="document" tabindex="-1">
            
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
                <div class="flex gap-2">
                    <button onclick={handleHide} class="p-3 rounded-xl bg-slate-100 dark:bg-slate-700 text-slate-600 hover:bg-slate-200 transition-colors" title="Hide Detection"><svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" /></svg></button>
                    <button onclick={handleDelete} class="p-3 rounded-xl bg-red-50 dark:bg-red-900/20 text-red-600 hover:bg-red-100 transition-colors" title="Delete Detection"><svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg></button>
                    <button onclick={() => { selectedSpecies = selectedEvent?.display_name ?? null; selectedEvent = null; }} class="flex-1 bg-teal-500 hover:bg-teal-600 text-white font-black uppercase tracking-widest text-xs rounded-xl transition-all shadow-lg shadow-teal-500/20">Species Info</button>
                </div>
            </div>
        </div>
    </div>
{/if}
{#if selectedSpecies}<SpeciesDetailModal speciesName={selectedSpecies} onclose={() => selectedSpecies = null} />{/if}
{#if showVideo && selectedEvent}<VideoPlayer frigateEvent={selectedEvent.frigate_event} onClose={() => showVideo = false} />{/if}