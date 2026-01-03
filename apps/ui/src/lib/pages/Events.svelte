<script lang="ts">
    import { onMount } from 'svelte';
    import {
        fetchEvents,
        fetchEventFilters,
        getThumbnailUrl,
        hideDetection,
        deleteDetection,
        fetchSpecies,
        checkClipAvailable,
        fetchClassifierLabels,
        reclassifyDetection,
        updateDetectionSpecies,
        fetchHiddenCount,
        fetchEventsCount,
        analyzeDetection,
        classifyWildlife,
        type WildlifeClassification,
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

    // Reactive state for settings
    let preferScientific = $state(false);
    $effect(() => {
        const unsubscribe = settingsStore.subscribe(s => {
            preferScientific = s?.scientific_name_primary ?? false;
        });
        return unsubscribe;
    });

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
    let quickRetagEvent = $state<Detection | null>(null);
    let quickRetagSearchQuery = $state('');
    let quickReclassifying = $state<string | null>(null);
    let classifyingWildlife = $state(false);
    let showWildlifeResults = $state(false);
    let wildlifeResults = $state<WildlifeClassification[]>([]);
    let aiAnalysis = $state<string | null>(null);
    let showVideo = $state(false);

    let modalReclassifyProgress = $derived(selectedEvent ? detectionsStore.getReclassificationProgress(selectedEvent.frigate_event) : undefined);
    let modalPrimaryName = $derived(selectedEvent ? (preferScientific ? (selectedEvent.scientific_name || selectedEvent.display_name) : (selectedEvent.common_name || selectedEvent.display_name)) : '');
    let modalSubName = $derived(selectedEvent ? (preferScientific ? selectedEvent.common_name : selectedEvent.scientific_name) : null);

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
            const [filters, labels, hidden] = await Promise.all([fetchEventFilters(), fetchClassifierLabels().catch(() => ({labels:[]})), fetchHiddenCount().catch(() => ({hidden_count:0}))]);
            availableSpecies = (filters as EventFilters).species;
            availableCameras = (filters as EventFilters).cameras;
            classifierLabels = labels.labels;
            hiddenCount = hidden.hidden_count;
        } catch {}
        await loadEvents();
    });

    async function handleReclassify() {
        if (!selectedEvent) return;
        try { await reclassifyDetection(selectedEvent.frigate_event, selectedEvent.has_clip ? 'video' : 'snapshot'); } catch (e: any) { alert(e.message || 'Failed'); }
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
            <DetectionCard detection={event} onclick={() => selectedEvent = event} />
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
                    <div class="flex items-center justify-between mb-2"><span class="text-xs font-bold text-slate-500 uppercase tracking-widest">Confidence</span><span class="text-sm font-black text-slate-900 dark:text-white">{(selectedEvent.score * 100).toFixed(1)}%</span></div>
                    <div class="h-2 bg-slate-100 dark:bg-slate-700 rounded-full overflow-hidden"><div class="h-full rounded-full transition-all duration-700 {selectedEvent.score >= 0.8 ? 'bg-emerald-500' : 'bg-teal-500'}" style="width: {selectedEvent.score * 100}%"></div></div>
                </div>
                <div class="flex gap-2">
                    <button onclick={handleReclassify} class="flex-1 py-3 px-4 bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200 font-bold rounded-xl hover:bg-slate-200 transition-colors">Reclassify</button>
                    <button onclick={handleHide} class="p-3 bg-slate-100 dark:bg-slate-700 text-slate-600 rounded-xl hover:bg-slate-200"><svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" /></svg></button>
                    <button onclick={handleDelete} class="p-3 bg-red-50 dark:bg-red-900/20 text-red-600 rounded-xl hover:bg-red-100"><svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg></button>
                </div>
            </div>
        </div>
    </div>
{/if}
{#if selectedSpecies}<SpeciesDetailModal speciesName={selectedSpecies} onclose={() => selectedSpecies = null} />{/if}
{#if showVideo && selectedEvent}<VideoPlayer frigateEvent={selectedEvent.frigate_event} onClose={() => showVideo = false} />{/if}