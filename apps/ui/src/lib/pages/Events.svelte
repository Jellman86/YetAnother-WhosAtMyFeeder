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
        type EventFilters,
        type EventFilterSpecies
    } from '../api';
    import { detectionsStore } from '../stores/detections.svelte';
    import { settingsStore } from '../stores/settings.svelte';
    import { authStore } from '../stores/auth.svelte';
    import { toastStore } from '../stores/toast.svelte';
    import { _ } from 'svelte-i18n';
    import Pagination from '../components/Pagination.svelte';
    import DetectionCard from '../components/DetectionCard.svelte';
    import SpeciesDetailModal from '../components/SpeciesDetailModal.svelte';
    import VideoPlayer from '../components/VideoPlayer.svelte';
    import DetectionModal from '../components/DetectionModal.svelte';
    import ReclassificationOverlay from '../components/ReclassificationOverlay.svelte';

    import { getBirdNames } from '../naming';

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
    let availableSpecies: EventFilterSpecies[] = $state([]);
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

    let llmEnabled = $state(false);
    $effect(() => {
        llmEnabled = settingsStore.settings?.llm_enabled ?? authStore.llmEnabled ?? false;
    });

    // Naming logic
    let naming = $derived.by(() => {
        if (!selectedEvent) return { primary: '', secondary: null };
        const showCommon = settingsStore.displayCommonNames;
        const preferSci = settingsStore.scientificNamePrimary;
        return getBirdNames(selectedEvent, showCommon, preferSci);
    });

    let modalReclassifyProgress = $derived(selectedEvent ? detectionsStore.getReclassificationProgress(selectedEvent.frigate_event) : undefined);
    let modalPrimaryName = $derived(naming.primary);
    let modalSubName = $derived(naming.secondary);

    function formatSpeciesLabel(item: EventFilterSpecies) {
        const showCommon = settingsStore.displayCommonNames;
        const preferSci = settingsStore.scientificNamePrimary;
        const naming = getBirdNames({
            display_name: item.display_name,
            scientific_name: item.scientific_name ?? undefined,
            common_name: item.common_name ?? undefined
        } as any, showCommon, preferSci);
        return naming.secondary ? `${naming.primary} (${naming.secondary})` : naming.primary;
    }

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
        } catch (e) { error = $_('events.load_failed'); } finally { loading = false; }
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

            if (speciesFilter && !speciesFilter.startsWith('taxa:')) {
                const normalized = speciesFilter.toLowerCase();
                const match = availableSpecies.find((s) => {
                    const display = (s.display_name || '').toLowerCase();
                    const sci = (s.scientific_name || '').toLowerCase();
                    const common = (s.common_name || '').toLowerCase();
                    return display === normalized || sci === normalized || common === normalized;
                });
                if (match) speciesFilter = match.value;
            }
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

    $effect(() => {
        if (!selectedEvent) return;
        const updated = detectionsStore.detections.find(
            (d) => d.frigate_event === selectedEvent?.frigate_event
        );
        if (updated && updated !== selectedEvent) {
            selectedEvent = updated;
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
        const requestedStrategy = selectedEvent.has_clip ? 'video' : 'snapshot';
        try {
            const result = await reclassifyDetection(selectedEvent.frigate_event, requestedStrategy);

            // Check if backend used a different strategy (fallback occurred)
            if (result.actual_strategy && result.actual_strategy !== requestedStrategy) {
                toastStore.warning($_('notifications.reclassify_fallback'));
            }
        } catch (e: any) {
            console.error('Failed to start reclassification', e.message);
            toastStore.error($_('notifications.reclassify_failed', { values: { message: e.message || 'Unknown error' } }));
        }
    }

    async function handleManualTag(newSpecies: string) {
        if (!selectedEvent) return;
        updatingTag = true;
        try {
            await updateDetectionSpecies(selectedEvent.frigate_event, newSpecies);
            selectedEvent.display_name = newSpecies;
            selectedEvent.manual_tagged = true;
            // Update local list
            events = events.map(e => e.frigate_event === selectedEvent?.frigate_event ? { ...e, display_name: newSpecies } : e);
            detectionsStore.updateDetection({ ...selectedEvent, display_name: newSpecies, manual_tagged: true });
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
        if (!selectedEvent || !confirm($_('actions.confirm_delete', { values: { species: selectedEvent.display_name } }))) return;
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
        <h2 class="text-2xl font-bold text-slate-900 dark:text-white">{$_('events.title')}</h2>
        <div class="text-sm text-slate-500">{$_('events.total_count', { values: { count: totalCount } })}</div>
    </div>

    <div class="card-base rounded-2xl p-4 flex flex-wrap gap-3">
        <select bind:value={datePreset} onchange={loadEvents} class="select-base min-w-[10rem]">
            <option value="all">{$_('events.filters.all_time')}</option><option value="today">{$_('common.today')}</option><option value="week">{$_('events.filters.week')}</option><option value="month">{$_('events.filters.month')}</option><option value="custom">{$_('events.filters.custom')}</option>
        </select>
        <select bind:value={speciesFilter} onchange={loadEvents} class="select-base min-w-[12rem]">
            <option value="">{$_('events.filters.all_species')}</option>{#each availableSpecies as s}<option value={s.value}>{formatSpeciesLabel(s)}</option>{/each}
        </select>
        <select bind:value={cameraFilter} onchange={loadEvents} class="select-base min-w-[12rem]">
            <option value="">{$_('events.filters.all_cameras')}</option>{#each availableCameras as c}<option value={c}>{c}</option>{/each}
        </select>
    </div>

    <Pagination {currentPage} {totalPages} totalItems={totalCount} itemsPerPage={pageSize} onPageChange={(p) => {currentPage=p; loadEvents()}} onPageSizeChange={(s) => {pageSize=s; currentPage=1; loadEvents()}} />

    {#if !loading && events.length === 0}
        <div class="card-base rounded-3xl p-10 text-center">
            <div class="text-5xl mb-3">🪶</div>
            <h3 class="text-lg font-semibold text-slate-900 dark:text-white">{$_('events.empty_title')}</h3>
            <p class="text-sm text-slate-500 dark:text-slate-400 mt-2">{$_('events.empty_desc')}</p>
        </div>
    {:else}
        <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
            {#each events as event (event.frigate_event)}
                <DetectionCard 
                    detection={event} 
                    onclick={() => selectedEvent = event} 
                    onPlay={() => { selectedEvent = event; showVideo = true; }}
                    hideProgress={selectedEvent?.frigate_event === event.frigate_event}
                />
            {/each}
        </div>
    {/if}
</div>

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
