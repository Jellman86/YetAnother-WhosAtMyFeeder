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

    // AI Analysis state
    let analyzingAI = $state(false);
    let aiAnalysis = $state<string | null>(null);

    // Hidden detections state
    let showHidden = $state(false);
    let hiddenCount = $state(0);

    // Pagination state
    let currentPage = $state(1);
    let pageSize = $state(24);
    let totalCount = $state(0);
    let totalPages = $derived(Math.ceil(totalCount / pageSize));

    // Filter options from server
    let availableSpecies: string[] = $state([]);
    let availableCameras: string[] = $state([]);

    // Date filters
    type DatePreset = 'all' | 'today' | 'week' | 'month' | 'custom';
    let datePreset = $state<DatePreset>('all');
    let customStartDate = $state('');
    let customEndDate = $state('');

    // Filters - now server-side
    let speciesFilter = $state('');
    let cameraFilter = $state('');
    let sortOrder = $state<'newest' | 'oldest' | 'confidence'>('newest');

    // Selected event for modal
    let selectedEvent = $state<Detection | null>(null);
    let selectedSpecies = $state<string | null>(null);

    // Mobile filter panel state
    let showMobileFilters = $state(false);

    // Reclassify and manual tag state
    let reclassifying = $state(false);
    let showTagDropdown = $state(false);
    let classifierLabels = $state<string[]>([]);
    let tagSearchQuery = $state('');
    let updatingTag = $state(false);

    // Quick action state (for overlay buttons)
    let quickRetagEvent = $state<Detection | null>(null);
    let quickRetagSearchQuery = $state('');
    let quickReclassifying = $state<string | null>(null); // frigate_event id being reclassified
    let preferScientific = $state(false);

    // Sync settings store to reactive state
    $effect(() => {
        const unsubscribe = settingsStore.subscribe(s => {
            preferScientific = s?.scientific_name_primary ?? false;
        });
        return unsubscribe;
    });

    // Wildlife classification state
// ...
    // Derive naming logic for the modal
    let modalPrimaryName = $derived(
        selectedEvent ? (preferScientific ? (selectedEvent.scientific_name || selectedEvent.display_name) : (selectedEvent.common_name || selectedEvent.display_name)) : ''
    );
    let modalSubName = $derived(
        selectedEvent ? (preferScientific ? selectedEvent.common_name : selectedEvent.scientific_name) : null
    );


    // Computed date range based on preset
    let dateRange = $derived.by(() => {
        const today = new Date();
        const formatDate = (d: Date) => d.toISOString().split('T')[0];

        switch (datePreset) {
            case 'today':
                return { start: formatDate(today), end: formatDate(today) };
            case 'week': {
                const weekAgo = new Date(today);
                weekAgo.setDate(weekAgo.getDate() - 7);
                return { start: formatDate(weekAgo), end: formatDate(today) };
            }
            case 'month': {
                const monthAgo = new Date(today);
                monthAgo.setDate(monthAgo.getDate() - 30);
                return { start: formatDate(monthAgo), end: formatDate(today) };
            }
            case 'custom':
                return { start: customStartDate || undefined, end: customEndDate || undefined };
            default:
                return { start: undefined, end: undefined };
        }
    });

    // Reset wildlife results and video when switching detections
    $effect(() => {
        if (selectedEvent) {
            showWildlifeResults = false;
            wildlifeResults = [];
            showVideo = false;
            aiAnalysis = null;
        }
    });

    // Read URL params on mount
    function parseUrlParams() {
        const params = new URLSearchParams(window.location.search);

        const page = params.get('page');
        if (page) currentPage = Math.max(1, parseInt(page) || 1);

        const size = params.get('size');
        if (size) pageSize = [12, 24, 48].includes(parseInt(size)) ? parseInt(size) : 24;

        const species = params.get('species');
        if (species) speciesFilter = species;

        const camera = params.get('camera');
        if (camera) cameraFilter = camera;

        const sort = params.get('sort');
        if (sort && ['newest', 'oldest', 'confidence'].includes(sort)) {
            sortOrder = sort as typeof sortOrder;
        }

        const preset = params.get('date');
        if (preset && ['all', 'today', 'week', 'month', 'custom'].includes(preset)) {
            datePreset = preset as DatePreset;
        } else if (preset === 'today') {
            // Handle explicit today passed from Dashboard
            datePreset = 'today';
        }

        const start = params.get('start');
        if (start) customStartDate = start;

        const end = params.get('end');
        if (end) customEndDate = end;
    }

    // Update URL with current state
    function updateUrl() {
        const params = new URLSearchParams();

        if (currentPage > 1) params.set('page', currentPage.toString());
        if (pageSize !== 24) params.set('size', pageSize.toString());
        if (speciesFilter) params.set('species', speciesFilter);
        if (cameraFilter) params.set('camera', cameraFilter);
        if (sortOrder !== 'newest') params.set('sort', sortOrder);
        if (datePreset !== 'all') params.set('date', datePreset);
        if (datePreset === 'custom' && customStartDate) params.set('start', customStartDate);
        if (datePreset === 'custom' && customEndDate) params.set('end', customEndDate);

        const search = params.toString();
        const newUrl = search ? `${window.location.pathname}?${search}` : window.location.pathname;
        window.history.replaceState(null, '', newUrl);
    }

    onMount(async () => {
        parseUrlParams();

        try {
            const [filters, labelsResponse, hiddenResponse] = await Promise.all([
                fetchEventFilters(),
                fetchClassifierLabels().catch(() => ({ labels: [] })),
                fetchHiddenCount().catch(() => ({ hidden_count: 0 }))
            ]);
            availableSpecies = (filters as EventFilters).species;
            availableCameras = (filters as EventFilters).cameras;
            classifierLabels = labelsResponse.labels;
            hiddenCount = hiddenResponse.hidden_count;
        } catch (e) {
            console.error('Failed to load filters', e);
        }

        await loadEvents();
    });

    async function loadEvents() {
        loading = true;
        error = null;
        try {
            const range = dateRange;
            const offset = (currentPage - 1) * pageSize;

            const [newEvents, countResponse] = await Promise.all([
                fetchEvents({
                    limit: pageSize,
                    offset,
                    startDate: range.start,
                    endDate: range.end,
                    species: speciesFilter || undefined,
                    camera: cameraFilter || undefined,
                    sort: sortOrder,
                    includeHidden: showHidden
                }),
                fetchEventsCount({
                    startDate: range.start,
                    endDate: range.end,
                    species: speciesFilter || undefined,
                    camera: cameraFilter || undefined,
                    includeHidden: showHidden
                })
            ]);

            events = newEvents;
            totalCount = countResponse.count;

            const maxPage = Math.max(1, Math.ceil(totalCount / pageSize));
            if (currentPage > maxPage) {
                currentPage = maxPage;
                await loadEvents();
                return;
            }

            updateUrl();
        } catch (e) {
            error = 'Failed to load events';
            console.error(e);
        } finally {
            loading = false;
        }
    }

    function handlePageChange(page: number) {
        currentPage = page;
        loadEvents();
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    function handlePageSizeChange(size: number) {
        pageSize = size;
        currentPage = 1;
        loadEvents();
    }

    function handleFilterChange() {
        currentPage = 1;
        loadEvents();
    }

    function handleDatePresetChange(preset: DatePreset) {
        datePreset = preset;
        currentPage = 1;
        loadEvents();
    }

    function applyCustomDateRange() {
        datePreset = 'custom';
        currentPage = 1;
        loadEvents();
    }

    function clearFilters() {
        speciesFilter = '';
        cameraFilter = '';
        sortOrder = 'newest';
        datePreset = 'all';
        customStartDate = '';
        customEndDate = '';
        currentPage = 1;
        loadEvents();
    }

    let hasActiveFilters = $derived(
        speciesFilter !== '' || cameraFilter !== '' || sortOrder !== 'newest' || datePreset !== 'all'
    );

    async function handleDelete() {
        if (!selectedEvent) return;
        if (!confirm(`Delete this ${selectedEvent.display_name} detection?`)) return;

        deleting = true;
        try {
            await deleteDetection(selectedEvent.frigate_event);
            const eventId = selectedEvent.frigate_event;
            events = events.filter(e => e.frigate_event !== eventId);
            totalCount = Math.max(0, totalCount - 1);
            // Update global store
            detectionsStore.removeDetection(eventId, selectedEvent.detection_time);
            selectedEvent = null;
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
            const isHidden = result.is_hidden;
            selectedEvent = { ...selectedEvent, is_hidden: isHidden };
            
            // Update local list
            events = events.map(e =>
                e.frigate_event === selectedEvent?.frigate_event
                    ? { ...e, is_hidden: isHidden }
                    : e
            );

            // Sync with global store
            if (isHidden) {
                detectionsStore.removeDetection(selectedEvent.frigate_event, selectedEvent.detection_time);
            } else {
                detectionsStore.updateDetection({ ...selectedEvent, is_hidden: isHidden });
            }

            if (isHidden) {
                hiddenCount++;
                if (!showHidden) {
                    events = events.filter(e => e.frigate_event !== selectedEvent?.frigate_event);
                    totalCount = Math.max(0, totalCount - 1);
                    selectedEvent = null;
                }
            } else {
                hiddenCount = Math.max(0, hiddenCount - 1);
            }
        } catch (e) {
            console.error('Failed to hide detection', e);
            alert('Failed to hide detection');
        } finally {
            hiding = false;
        }
    }

    function handleShowHiddenToggle() {
        showHidden = !showHidden;
        currentPage = 1;
        loadEvents();
    }

    async function handleReclassify() {
        if (!selectedEvent) return;

        reclassifying = true;
        const strategy = selectedHasClip ? 'video' : 'snapshot';
        
        try {
            const result = await reclassifyDetection(selectedEvent.frigate_event, strategy);
            if (result.updated) {
                selectedEvent = { ...selectedEvent, display_name: result.new_species, score: result.new_score };
                events = events.map(e =>
                    e.frigate_event === selectedEvent?.frigate_event
                        ? { ...e, display_name: result.new_species, score: result.new_score }
                        : e
                );
                // Update global store
                detectionsStore.updateDetection({ ...selectedEvent });
            }
        } catch (e: any) {
            console.error('Failed to reclassify', e);
            alert(e.message || 'Failed to reclassify detection');
        } finally {
            reclassifying = false;
        }
    }

    async function handleManualTag(newSpecies: string) {
        if (!selectedEvent || !newSpecies.trim()) return;

        updatingTag = true;
        try {
            const result = await updateDetectionSpecies(selectedEvent.frigate_event, newSpecies.trim());
            if (result.status === 'updated') {
                selectedEvent = { ...selectedEvent, display_name: newSpecies.trim() };
                events = events.map(e =>
                    e.frigate_event === selectedEvent?.frigate_event
                        ? { ...e, display_name: newSpecies.trim() }
                        : e
                );
                // Update global store
                detectionsStore.updateDetection({ ...selectedEvent });
            }
            showTagDropdown = false;
            tagSearchQuery = '';
        } catch (e: any) {
            console.error('Failed to update species', e);
            alert(e.message || 'Failed to update species');
        } finally {
            updatingTag = false;
        }
    }

    let filteredLabels = $derived.by(() =>
        tagSearchQuery.trim()
            ? classifierLabels.filter(label =>
                label.toLowerCase().includes(tagSearchQuery.toLowerCase())
              ).slice(0, 20)
            : classifierLabels.slice(0, 20)
    );

    let quickFilteredLabels = $derived.by(() =>
        quickRetagSearchQuery.trim()
            ? classifierLabels.filter(label =>
                label.toLowerCase().includes(quickRetagSearchQuery.toLowerCase())
              ).slice(0, 15)
            : classifierLabels.slice(0, 15)
    );

    async function handleQuickReclassify(detection: Detection) {
        if (quickReclassifying) return;

        quickReclassifying = detection.frigate_event;
        try {
            // Use video strategy if clip is available for better accuracy and progress visualization
            const strategy = detection.has_clip ? 'video' : 'snapshot';
            const result = await reclassifyDetection(detection.frigate_event, strategy);
            if (result.updated) {
                events = events.map(e =>
                    e.frigate_event === detection.frigate_event
                        ? { ...e, display_name: result.new_species, score: result.new_score }
                        : e
                );
                // Update global store
                const updated = events.find(e => e.frigate_event === detection.frigate_event);
                if (updated) detectionsStore.updateDetection(updated);
            }
        } catch (e: any) {
            console.error('Failed to reclassify', e);
            alert(e.message || 'Failed to reclassify detection');
        } finally {
            quickReclassifying = null;
        }
    }

    function handleQuickRetag(detection: Detection) {
        quickRetagEvent = detection;
        quickRetagSearchQuery = '';
    }

    async function applyQuickRetag(newSpecies: string) {
        if (!quickRetagEvent || !newSpecies.trim()) return;

        const eventId = quickRetagEvent.frigate_event;
        try {
            const result = await updateDetectionSpecies(eventId, newSpecies.trim());
            if (result.status === 'updated') {
                events = events.map(e =>
                    e.frigate_event === eventId
                        ? { ...e, display_name: newSpecies.trim() }
                        : e
                );
                // Update global store
                const updated = events.find(e => e.frigate_event === eventId);
                if (updated) detectionsStore.updateDetection(updated);
            }
            quickRetagEvent = null;
            quickRetagSearchQuery = '';
        } catch (e: any) {
            console.error('Failed to update species', e);
            alert(e.message || 'Failed to update species');
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

    async function handleClassifyWildlife() {
        if (!selectedEvent) return;

        classifyingWildlife = true;
        showWildlifeResults = false;
        wildlifeResults = [];

        try {
            const result = await classifyWildlife(selectedEvent.frigate_event);
            wildlifeResults = result.classifications;
            showWildlifeResults = true;
        } catch (e: any) {
            console.error('Failed to classify wildlife', e);
            if (e.message?.includes('503') || e.message?.includes('not available')) {
                alert('Wildlife model not available. Please download it from Settings.');
            } else {
                alert(e.message || 'Failed to classify as wildlife');
            }
        } finally {
            classifyingWildlife = false;
        }
    }

    async function applyWildlifeResult(label: string) {
        if (!selectedEvent) return;

        updatingTag = true;
        try {
            const result = await updateDetectionSpecies(selectedEvent.frigate_event, label);
            if (result.status === 'updated') {
                selectedEvent = { ...selectedEvent, display_name: label };
                events = events.map(e =>
                    e.frigate_event === selectedEvent?.frigate_event
                        ? { ...e, display_name: label }
                        : e
                );
                // Update global store
                detectionsStore.updateDetection({ ...selectedEvent });
            }
            showWildlifeResults = false;
            wildlifeResults = [];
        } catch (e: any) {
            console.error('Failed to apply wildlife result', e);
            alert(e.message || 'Failed to apply species');
        } finally {
            updatingTag = false;
        }
    }
</script>

<div class="space-y-6">
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <h2 class="text-2xl font-bold text-slate-900 dark:text-white">Events</h2>

        <div class="flex items-center gap-3 text-sm text-slate-500 dark:text-slate-400">
            <span class="font-medium text-slate-900 dark:text-white">{totalCount.toLocaleString()}</span>
            <span>total detections</span>
            {#if hasActiveFilters}
                <button
                    onclick={clearFilters}
                    class="text-teal-500 hover:text-teal-600 flex items-center gap-1"
                >
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                    Clear filters
                </button>
            {/if}
        </div>
    </div>

    <!-- Mobile Filter Toggle -->
    <button
        onclick={() => showMobileFilters = !showMobileFilters}
        class="sm:hidden w-full flex items-center justify-between px-4 py-3 rounded-xl
               bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700
               text-slate-700 dark:text-slate-300"
    >
        <span class="flex items-center gap-2">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                      d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
            </svg>
            Filters & Sort
            {#if hasActiveFilters}
                <span class="px-2 py-0.5 rounded-full bg-teal-100 dark:bg-teal-900/30 text-teal-700 dark:text-teal-300 text-xs font-medium">
                    Active
                </span>
            {/if}
        </span>
        <svg
            class="w-5 h-5 transition-transform duration-200 {showMobileFilters ? 'rotate-180' : ''}"
            fill="none" stroke="currentColor" viewBox="0 0 24 24"
        >
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
        </svg>
    </button>

    <!-- Filter Panel (collapsible on mobile) -->
    <div class="{showMobileFilters ? 'block' : 'hidden'} sm:block space-y-4">
        <!-- Date Filters -->
        <div class="flex flex-wrap items-center gap-2">
            <span class="text-sm text-slate-500 dark:text-slate-400 w-full sm:w-auto mb-1 sm:mb-0">Date:</span>
            <div class="flex flex-wrap gap-2">
                {#each [
                    { value: 'all', label: 'All Time' },
                    { value: 'today', label: 'Today' },
                    { value: 'week', label: 'Week' },
                    { value: 'month', label: 'Month' },
                ] as preset}
                    <button
                        onclick={() => handleDatePresetChange(preset.value as DatePreset)}
                        class="px-3 py-1.5 rounded-lg text-sm font-medium transition-colors
                               {datePreset === preset.value
                                   ? 'bg-teal-500 text-white'
                                   : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700'}"
                    >
                        {preset.label}
                    </button>
                {/each}
                <button
                    onclick={() => datePreset = 'custom'}
                    class="px-3 py-1.5 rounded-lg text-sm font-medium transition-colors
                           {datePreset === 'custom'
                               ? 'bg-teal-500 text-white'
                               : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700'}"
                >
                    Custom
                </button>
            </div>
        </div>

        <!-- Custom Date Range -->
        {#if datePreset === 'custom'}
            <div class="flex flex-col sm:flex-row flex-wrap items-start sm:items-center gap-3 p-3 bg-slate-50 dark:bg-slate-800/50 rounded-lg">
                <div class="flex items-center gap-2 w-full sm:w-auto">
                    <label for="date-from" class="text-sm text-slate-600 dark:text-slate-400 w-12 sm:w-auto">From:</label>
                    <input
                        id="date-from"
                        type="date"
                        bind:value={customStartDate}
                        class="flex-1 sm:flex-none px-3 py-1.5 rounded-lg border border-slate-300 dark:border-slate-600
                               bg-white dark:bg-slate-800 text-slate-900 dark:text-white text-sm"
                    />
                </div>
                <div class="flex items-center gap-2 w-full sm:w-auto">
                    <label for="date-to" class="text-sm text-slate-600 dark:text-slate-400 w-12 sm:w-auto">To:</label>
                    <input
                        id="date-to"
                        type="date"
                        bind:value={customEndDate}
                        class="flex-1 sm:flex-none px-3 py-1.5 rounded-lg border border-slate-300 dark:border-slate-600
                               bg-white dark:bg-slate-800 text-slate-900 dark:text-white text-sm"
                    />
                </div>
                <button
                    onclick={applyCustomDateRange}
                    class="w-full sm:w-auto px-4 py-1.5 rounded-lg text-sm font-medium bg-teal-500 text-white hover:bg-teal-600 transition-colors"
                >
                    Apply
                </button>
            </div>
        {/if}

        <!-- Species/Camera/Sort Filters -->
        <div class="grid grid-cols-1 sm:flex sm:flex-wrap gap-3">
            <select
                bind:value={speciesFilter}
                onchange={handleFilterChange}
                class="w-full sm:w-auto px-3 py-2.5 sm:py-2 rounded-lg border border-slate-300 dark:border-slate-600
                       bg-white dark:bg-slate-800 text-slate-900 dark:text-white text-sm
                       focus:ring-2 focus:ring-teal-500 focus:border-transparent"
            >
                <option value="">All Species ({availableSpecies.length})</option>
                {#each availableSpecies as species}
                    <option value={species}>{species}</option>
                {/each}
            </select>

            <select
                bind:value={cameraFilter}
                onchange={handleFilterChange}
                class="w-full sm:w-auto px-3 py-2.5 sm:py-2 rounded-lg border border-slate-300 dark:border-slate-600
                       bg-white dark:bg-slate-800 text-slate-900 dark:text-white text-sm
                       focus:ring-2 focus:ring-teal-500 focus:border-transparent"
            >
                <option value="">All Cameras ({availableCameras.length})</option>
                {#each availableCameras as camera}
                    <option value={camera}>{camera}</option>
                {/each}
            </select>

            <select
                bind:value={sortOrder}
                onchange={handleFilterChange}
                class="w-full sm:w-auto px-3 py-2.5 sm:py-2 rounded-lg border border-slate-300 dark:border-slate-600
                       bg-white dark:bg-slate-800 text-slate-900 dark:text-white text-sm
                       focus:ring-2 focus:ring-teal-500 focus:border-transparent"
            >
                <option value="newest">Newest First</option>
                <option value="oldest">Oldest First</option>
                <option value="confidence">Highest Confidence</option>
            </select>

            <!-- Show Ignored Toggle -->
            {#if hiddenCount > 0 || showHidden}
                <button
                    onclick={handleShowHiddenToggle}
                    class="w-full sm:w-auto px-3 py-2.5 sm:py-2 rounded-lg text-sm font-medium transition-colors
                           flex items-center justify-center gap-2
                           {showHidden
                               ? 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 border border-amber-300 dark:border-amber-700'
                               : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700 border border-slate-300 dark:border-slate-600'}"
                >
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        {#if showHidden}
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                                  d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                                  d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                        {:else}
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                                  d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                        {/if}
                    </svg>
                    {showHidden ? 'Showing' : 'Show'} ignored ({hiddenCount})
                </button>
            {/if}
        </div>
    </div>

    {#if error}
        <div class="p-4 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 border border-red-200 dark:border-red-800">
            {error}
            <button onclick={() => loadEvents()} class="ml-2 underline">Retry</button>
        </div>
    {/if}

    {#if loading && events.length === 0}
        <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
            {#each [1, 2, 3, 4, 5, 6, 7, 8] as _}
                <div class="aspect-[4/3] bg-slate-100 dark:bg-slate-800 rounded-xl animate-pulse"></div>
            {/each}
        </div>
    {:else if events.length === 0}
        <div class="text-center py-16 bg-white/80 dark:bg-slate-800/50 rounded-2xl border border-slate-200/80 dark:border-slate-700/50">
            <div class="w-16 h-16 mx-auto mb-4 rounded-full bg-slate-100 dark:bg-slate-700/50 flex items-center justify-center">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-8 w-8 text-slate-400 dark:text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
            </div>
            <h3 class="text-lg font-semibold text-slate-900 dark:text-white mb-2">No events found</h3>
            <p class="text-slate-500 dark:text-slate-400 mb-4">
                {#if hasActiveFilters}
                    No detections match your current filters.
                {:else}
                    No bird detections have been recorded yet.
                {/if}
            </p>
            {#if hasActiveFilters}
                <button
                    onclick={clearFilters}
                    class="px-4 py-2 rounded-lg text-sm font-medium bg-teal-500 text-white hover:bg-teal-600 transition-colors"
                >
                    Clear all filters
                </button>
            {/if}
        </div>
    {:else}
        <!-- Top pagination -->
        <Pagination
            {currentPage}
            {totalPages}
            totalItems={totalCount}
            itemsPerPage={pageSize}
            onPageChange={handlePageChange}
            onPageSizeChange={handlePageSizeChange}
        />

        <!-- Loading overlay for filter changes -->
        <div class="relative">
            {#if loading}
                <div class="absolute inset-0 bg-white/50 dark:bg-slate-900/50 z-10 flex items-center justify-center rounded-xl">
                    <div class="w-8 h-8 border-4 border-teal-500 border-t-transparent rounded-full animate-spin"></div>
                </div>
            {/if}

            <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
                {#each events as event (event.frigate_event)}
                    <DetectionCard
                        detection={event}
                        onclick={() => selectedEvent = event}
                        onReclassify={handleQuickReclassify}
                        onRetag={handleQuickRetag}
                    />
                {/each}
            </div>
        </div>

        <!-- Bottom pagination -->
        <Pagination
            {currentPage}
            {totalPages}
            totalItems={totalCount}
            itemsPerPage={pageSize}
            onPageChange={handlePageChange}
            onPageSizeChange={handlePageSizeChange}
        />
    {/if}
</div>

<!-- Detail Modal -->
{#if selectedEvent}
    <div
        class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
        onclick={() => selectedEvent = null}
        onkeydown={(e) => e.key === 'Escape' && (selectedEvent = null)}
        role="dialog"
        tabindex="-1"
    >
        <div
            class="bg-white dark:bg-slate-800 rounded-2xl shadow-2xl max-w-lg w-full max-h-[90vh] overflow-hidden
                   border border-slate-200 dark:border-slate-700"
            onclick={(e) => e.stopPropagation()}
            onkeydown={(e) => e.stopPropagation()}
            role="document"
            tabindex="-1"
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
                        {modalPrimaryName}
                    </h3>
                    {#if modalSubName && modalSubName !== modalPrimaryName}
                        <p class="text-white/70 text-sm italic drop-shadow -mt-1 mb-1">{modalSubName}</p>
                    {/if}
                    <p class="text-white/80 text-[10px] uppercase font-bold tracking-wider">
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

                <!-- Reclassification Overlay -->
                {#if modalReclassifyProgress}
                    <ReclassificationOverlay progress={modalReclassifyProgress} />
                {/if}
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

                <!-- Action buttons - Row 1 -->
                <div class="flex gap-2 mb-2">
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
                        class="px-4 py-2.5 text-sm font-medium rounded-lg transition-colors
                               disabled:opacity-50 disabled:cursor-not-allowed
                               flex items-center justify-center gap-2
                               {selectedEvent.is_hidden
                                   ? 'text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 hover:bg-amber-100 dark:hover:bg-amber-900/40'
                                   : 'text-slate-600 dark:text-slate-400 bg-slate-100 dark:bg-slate-700 hover:bg-slate-200 dark:hover:bg-slate-600'}"
                    >
                        {#if hiding}
                            <svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                            </svg>
                        {:else}
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                {#if selectedEvent.is_hidden}
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                                          d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                                          d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                                {:else}
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                                          d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                                {/if}
                            </svg>
                        {/if}
                        {hiding ? 'Updating...' : (selectedEvent.is_hidden ? 'Unhide' : 'Hide')}
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

                <!-- Action buttons - Row 2: Reclassify & Manual Tag -->
                <div class="flex gap-2">
                    <button
                        onclick={handleReclassify}
                        disabled={reclassifying}
                        class="flex-1 px-4 py-2.5 text-sm font-medium text-slate-700 dark:text-slate-300
                               bg-slate-100 dark:bg-slate-700 rounded-lg
                               hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors
                               disabled:opacity-50 disabled:cursor-not-allowed
                               flex items-center justify-center gap-2"
                    >
                        {#if reclassifying}
                            <svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                            </svg>
                        {:else}
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                                      d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                            </svg>
                        {/if}
                        {reclassifying ? 'Reclassifying...' : 'Reclassify'}
                    </button>
                    <div class="relative flex-1">
                        <button
                            onclick={() => showTagDropdown = !showTagDropdown}
                            disabled={updatingTag}
                            class="w-full px-4 py-2.5 text-sm font-medium text-slate-700 dark:text-slate-300
                                   bg-slate-100 dark:bg-slate-700 rounded-lg
                                   hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors
                                   disabled:opacity-50 disabled:cursor-not-allowed
                                   flex items-center justify-center gap-2"
                        >
                            {#if updatingTag}
                                <svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                </svg>
                            {:else}
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                                          d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" />
                                </svg>
                            {/if}
                            {updatingTag ? 'Updating...' : 'Manual Tag'}
                        </button>

                        <!-- Tag Dropdown -->
                        {#if showTagDropdown}
                            <div class="absolute bottom-full left-0 right-0 mb-2 bg-white dark:bg-slate-800
                                        rounded-lg shadow-xl border border-slate-200 dark:border-slate-700
                                        max-h-64 overflow-hidden z-10">
                                <div class="p-2 border-b border-slate-200 dark:border-slate-700">
                                    <input
                                        type="text"
                                        bind:value={tagSearchQuery}
                                        placeholder="Search species..."
                                        class="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-600
                                               bg-white dark:bg-slate-700 text-slate-900 dark:text-white
                                               focus:ring-2 focus:ring-teal-500 focus:border-transparent"
                                    />
                                </div>
                                <div class="max-h-48 overflow-y-auto">
                                    {#each filteredLabels as label}
                                        <button
                                            onclick={() => handleManualTag(label)}
                                            class="w-full px-3 py-2 text-left text-sm text-slate-700 dark:text-slate-300
                                                   hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors
                                                   {label === selectedEvent?.display_name ? 'bg-teal-50 dark:bg-teal-900/20 text-teal-700 dark:text-teal-300' : ''}"
                                        >
                                            {label}
                                        </button>
                                    {/each}
                                    {#if filteredLabels.length === 0}
                                        <p class="px-3 py-2 text-sm text-slate-500 dark:text-slate-400 italic">
                                            No matching species found
                                        </p>
                                    {/if}
                                </div>
                            </div>
                        {/if}
                    </div>
                </div>

                <!-- Action buttons - Row 3: Identify Animal (Wildlife) -->
                <div class="relative mt-3">
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
                                      d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
                            </svg>
                        {/if}
                        {classifyingWildlife ? 'Identifying...' : 'Identify Animal'}
                    </button>

                    <!-- Wildlife Results Dropdown -->
                    {#if showWildlifeResults && wildlifeResults.length > 0}
                        <div class="absolute bottom-full left-0 right-0 mb-2 bg-white dark:bg-slate-800
                                    rounded-lg shadow-xl border border-amber-200 dark:border-amber-700
                                    overflow-hidden z-10">
                            <div class="p-2 border-b border-amber-200 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/20">
                                <p class="text-xs font-medium text-amber-700 dark:text-amber-300">Wildlife Classification Results</p>
                            </div>
                            <div class="max-h-48 overflow-y-auto">
                                {#each wildlifeResults as result}
                                    <button
                                        onclick={() => applyWildlifeResult(result.label)}
                                        disabled={updatingTag}
                                        class="w-full px-3 py-2 text-left text-sm flex items-center justify-between
                                               hover:bg-amber-50 dark:hover:bg-amber-900/20 transition-colors
                                               disabled:opacity-50"
                                    >
                                        <span class="text-slate-700 dark:text-slate-300">{result.label}</span>
                                        <span class="text-xs font-medium px-2 py-0.5 rounded-full
                                                     {result.score >= 0.7 ? 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300' :
                                                      result.score >= 0.4 ? 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300' :
                                                      'bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-400'}">
                                            {(result.score * 100).toFixed(0)}%
                                        </span>
                                    </button>
                                {/each}
                            </div>
                            <div class="p-2 border-t border-amber-200 dark:border-amber-700">
                                <button
                                    onclick={() => { showWildlifeResults = false; wildlifeResults = []; }}
                                    class="w-full text-xs text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300"
                                >
                                    Close
                                </button>
                            </div>
                        </div>
                    {/if}
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

<!-- Quick Retag Modal -->
{#if quickRetagEvent}
    <div
        class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
        onclick={() => { quickRetagEvent = null; quickRetagSearchQuery = ''; }}
        onkeydown={(e) => e.key === 'Escape' && (quickRetagEvent = null)}
        role="dialog"
        tabindex="-1"
    >
        <div
            class="bg-white dark:bg-slate-800 rounded-2xl shadow-2xl w-full max-w-md overflow-hidden
                   border border-slate-200 dark:border-slate-700"
            onclick={(e) => e.stopPropagation()}
            onkeydown={(e) => e.stopPropagation()}
            role="document"
            tabindex="-1"
        >
            <!-- Header with thumbnail -->
            <div class="relative h-32 bg-slate-100 dark:bg-slate-700">
                <img
                    src={getThumbnailUrl(quickRetagEvent.frigate_event)}
                    alt={quickRetagEvent.display_name}
                    class="w-full h-full object-cover"
                />
                <div class="absolute inset-0 bg-gradient-to-t from-black/70 via-transparent to-transparent"></div>
                <div class="absolute bottom-0 left-0 right-0 p-4">
                    <p class="text-sm text-white/80">Current tag:</p>
                    <h3 class="text-lg font-bold text-white">{quickRetagEvent.display_name}</h3>
                </div>
                <button
                    onclick={() => { quickRetagEvent = null; quickRetagSearchQuery = ''; }}
                    class="absolute top-2 right-2 w-8 h-8 rounded-full bg-black/40 text-white/90
                           flex items-center justify-center hover:bg-black/60 transition-colors"
                    aria-label="Close"
                >
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                </button>
            </div>

            <!-- Search and labels -->
            <div class="p-4">
                <div class="mb-3">
                    <input
                        type="text"
                        bind:value={quickRetagSearchQuery}
                        placeholder="Search bird species..."
                        class="w-full px-4 py-2.5 text-sm rounded-lg border border-slate-300 dark:border-slate-600
                               bg-white dark:bg-slate-700 text-slate-900 dark:text-white
                               focus:ring-2 focus:ring-teal-500 focus:border-transparent"
                    />
                </div>
                <div class="max-h-64 overflow-y-auto space-y-1">
                    {#each quickFilteredLabels as label}
                        <button
                            onclick={() => applyQuickRetag(label)}
                            class="w-full px-3 py-2 text-left text-sm rounded-lg transition-colors
                                   hover:bg-slate-100 dark:hover:bg-slate-700
                                   {label === quickRetagEvent?.display_name
                                       ? 'bg-teal-50 dark:bg-teal-900/20 text-teal-700 dark:text-teal-300 font-medium'
                                       : 'text-slate-700 dark:text-slate-300'}"
                        >
                            {label}
                        </button>
                    {/each}
                    {#if quickFilteredLabels.length === 0}
                        <p class="px-3 py-4 text-sm text-slate-500 dark:text-slate-400 italic text-center">
                            No matching species found
                        </p>
                    {/if}
                </div>
            </div>
        </div>
    </div>
{/if}

<!-- Video Player Modal -->
{#if showVideo && selectedEvent}
    <VideoPlayer
        frigateEvent={selectedEvent.frigate_event}
        onClose={() => showVideo = false}
    />
{/if}