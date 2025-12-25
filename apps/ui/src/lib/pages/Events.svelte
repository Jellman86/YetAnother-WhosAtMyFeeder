<script lang="ts">
    import { onMount } from 'svelte';
    import {
        fetchEvents,
        fetchEventFilters,
        fetchEventsCount,
        deleteDetection,
        fetchClassifierLabels,
        reclassifyDetection,
        updateDetectionSpecies,
        type Detection,
        getThumbnailUrl
    } from '../api';
    import DetectionCard from '../components/DetectionCard.svelte';
    import SpeciesDetailModal from '../components/SpeciesDetailModal.svelte';
    import Pagination from '../components/Pagination.svelte';

    let events: Detection[] = $state([]);
    let loading = $state(true);
    let error = $state<string | null>(null);
    let deleting = $state(false);

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

    // Computed date range based on preset
    let dateRange = $derived(() => {
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

        // Load filter options and classifier labels in parallel
        try {
            const [filters, labelsResponse] = await Promise.all([
                fetchEventFilters(),
                fetchClassifierLabels().catch(() => ({ labels: [] }))
            ]);
            availableSpecies = filters.species;
            availableCameras = filters.cameras;
            classifierLabels = labelsResponse.labels;
        } catch (e) {
            console.error('Failed to load filters', e);
        }

        await loadEvents();
    });

    async function loadEvents() {
        loading = true;
        error = null;
        try {
            const range = dateRange();
            const offset = (currentPage - 1) * pageSize;

            // Fetch events and count in parallel
            const [newEvents, countResponse] = await Promise.all([
                fetchEvents({
                    limit: pageSize,
                    offset,
                    startDate: range.start,
                    endDate: range.end,
                    species: speciesFilter || undefined,
                    camera: cameraFilter || undefined,
                    sort: sortOrder
                }),
                fetchEventsCount({
                    startDate: range.start,
                    endDate: range.end,
                    species: speciesFilter || undefined,
                    camera: cameraFilter || undefined
                })
            ]);

            events = newEvents;
            totalCount = countResponse.count;

            // Ensure current page is valid
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
        speciesFilter || cameraFilter || sortOrder !== 'newest' || datePreset !== 'all'
    );

    async function handleDelete() {
        if (!selectedEvent) return;
        if (!confirm(`Delete this ${selectedEvent.display_name} detection?`)) return;

        deleting = true;
        try {
            await deleteDetection(selectedEvent.frigate_event);
            events = events.filter(e => e.frigate_event !== selectedEvent?.frigate_event);
            totalCount = Math.max(0, totalCount - 1);
            selectedEvent = null;
        } catch (e) {
            console.error('Failed to delete detection', e);
            alert('Failed to delete detection');
        } finally {
            deleting = false;
        }
    }

    async function handleReclassify() {
        if (!selectedEvent) return;

        reclassifying = true;
        try {
            const result = await reclassifyDetection(selectedEvent.frigate_event);
            if (result.updated) {
                // Update the local event data
                selectedEvent = { ...selectedEvent, display_name: result.new_species, score: result.new_score };
                // Update in the events list too
                events = events.map(e =>
                    e.frigate_event === selectedEvent?.frigate_event
                        ? { ...e, display_name: result.new_species, score: result.new_score }
                        : e
                );
                alert(`Reclassified: ${result.old_species} → ${result.new_species} (${(result.new_score * 100).toFixed(1)}%)`);
            } else {
                alert(`Classification unchanged: ${result.new_species} (${(result.new_score * 100).toFixed(1)}%)`);
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
                // Update the local event data
                selectedEvent = { ...selectedEvent, display_name: newSpecies.trim() };
                // Update in the events list too
                events = events.map(e =>
                    e.frigate_event === selectedEvent?.frigate_event
                        ? { ...e, display_name: newSpecies.trim() }
                        : e
                );
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

    // Filter labels based on search query
    let filteredLabels = $derived(
        tagSearchQuery.trim()
            ? classifierLabels.filter(label =>
                label.toLowerCase().includes(tagSearchQuery.toLowerCase())
              ).slice(0, 20)
            : classifierLabels.slice(0, 20)
    );
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
                    <label class="text-sm text-slate-600 dark:text-slate-400 w-12 sm:w-auto">From:</label>
                    <input
                        type="date"
                        bind:value={customStartDate}
                        class="flex-1 sm:flex-none px-3 py-1.5 rounded-lg border border-slate-300 dark:border-slate-600
                               bg-white dark:bg-slate-800 text-slate-900 dark:text-white text-sm"
                    />
                </div>
                <div class="flex items-center gap-2 w-full sm:w-auto">
                    <label class="text-sm text-slate-600 dark:text-slate-400 w-12 sm:w-auto">To:</label>
                    <input
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
                <div class="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400 mb-5">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                              d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                    </svg>
                    <span class="font-medium">{selectedEvent.camera_name}</span>
                </div>

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
