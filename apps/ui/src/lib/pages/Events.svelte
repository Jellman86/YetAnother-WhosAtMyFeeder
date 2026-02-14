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
    let favoritesOnly = $state(false);
    let sortOrder = $state<'newest' | 'oldest' | 'confidence'>('newest');

    let selectedEvent = $state<Detection | null>(null);
    let selectedSpecies = $state<string | null>(null);
    let pendingEventId = $state<string | null>(null);
    let classifierLabels = $state<string[]>([]);
    let tagSearchQuery = $state('');
    let showTagDropdown = $state(false);
    let updatingTag = $state(false);

    let analyzingAI = $state(false);
    let aiAnalysis = $state<string | null>(null);

    let llmReady = $state(false);
    $effect(() => {
        llmReady = settingsStore.llmReady;
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

    function detectionSyncSignature(d: Detection): string {
        return [
            d.frigate_event,
            d.display_name,
            d.score,
            d.manual_tagged,
            d.is_hidden,
            d.is_favorite,
            d.video_classification_status,
            d.video_classification_label,
            d.video_classification_score,
            d.has_clip
        ].join('|');
    }

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
        error = null;
        try {
            const range = dateRange;
            const [newEvents, countRes] = await Promise.all([
                fetchEvents({
                    limit: pageSize,
                    offset: (currentPage - 1) * pageSize,
                    startDate: range.start,
                    endDate: range.end,
                    species: speciesFilter || undefined,
                    camera: cameraFilter || undefined,
                    sort: sortOrder,
                    includeHidden: showHidden,
                    favoritesOnly
                }),
                fetchEventsCount({
                    startDate: range.start,
                    endDate: range.end,
                    species: speciesFilter || undefined,
                    camera: cameraFilter || undefined,
                    includeHidden: showHidden,
                    favoritesOnly
                })
            ]);
            events = newEvents;
            totalCount = countRes.count;
            if (pendingEventId) {
                const target = newEvents.find((event) => event.frigate_event === pendingEventId);
                if (target) {
                    selectedEvent = target;
                    pendingEventId = null;
                    clearEventVideoDeepLinkParams();
                }
            }
        } catch (e) {
            if (e instanceof Error && e.name === 'AbortError') {
                // Request cancellation is expected when filter changes trigger a newer fetch.
                return;
            }
            // Events can look "empty" when the API is unreachable; surface a visible error instead.
            error = $_('events.load_failed');
            console.error('Failed to load events', e);
        } finally {
            loading = false;
        }
    }

    onMount(async () => {
        const params = new URLSearchParams(window.location.search);
        if (params.get('species')) speciesFilter = params.get('species')!;
        if (params.get('date')) datePreset = params.get('date') as any;
        if (params.get('favorites') === '1' || params.get('favorites') === 'true') favoritesOnly = true;
        const deepLinkedEvent = params.get('event');
        const deepLinkedShare = params.get('share');
        const videoParam = params.get('video');
        const deepLinkWantsVideo = videoParam === '1' || videoParam === 'true';
        if (deepLinkedEvent && deepLinkWantsVideo) {
            videoEventId = deepLinkedEvent;
            videoShareToken = deepLinkedShare;
            videoPlayIntent = 'auto';
            showVideo = true;
            if (!deepLinkedShare) {
                clearEventVideoDeepLinkParams();
            }
        } else if (deepLinkedEvent) {
            pendingEventId = deepLinkedEvent;
        }

        const openedViaShare = !!(deepLinkedEvent && deepLinkWantsVideo && deepLinkedShare);
        if (openedViaShare) {
            loading = false;
            return;
        }

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
        // Avoid proxy-identity churn causing a self-triggering effect loop.
        if (updated && detectionSyncSignature(updated) !== detectionSyncSignature(selectedEvent)) {
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
    let videoEventId = $state<string | null>(null);
    let videoShareToken = $state<string | null>(null);
    let videoPlayIntent = $state<'auto' | 'user'>('auto');

    let selectedTimelineBucket = $state<string>('all');

    function detectionDayKey(detection: Detection): string {
        const date = new Date(detection.detection_time);
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    }

    function formatTimelineBucketLabel(bucket: string): string {
        const date = new Date(`${bucket}T00:00:00`);
        return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
    }

    let timelineBuckets = $derived.by(() => {
        const counts = new Map<string, number>();
        for (const event of events) {
            const key = detectionDayKey(event);
            counts.set(key, (counts.get(key) ?? 0) + 1);
        }
        return Array.from(counts.entries())
            .sort((a, b) => b[0].localeCompare(a[0]))
            .map(([key, count]) => ({ key, count, label: formatTimelineBucketLabel(key) }));
    });

    let visibleEvents = $derived.by(() => {
        if (selectedTimelineBucket === 'all') return events;
        return events.filter((event) => detectionDayKey(event) === selectedTimelineBucket);
    });

    $effect(() => {
        if (selectedTimelineBucket === 'all') return;
        if (!timelineBuckets.some((bucket) => bucket.key === selectedTimelineBucket)) {
            selectedTimelineBucket = 'all';
        }
    });

    function moveTimelineSelection(direction: 1 | -1): void {
        const keys = ['all', ...timelineBuckets.map((bucket) => bucket.key)];
        const current = Math.max(0, keys.indexOf(selectedTimelineBucket));
        const next = Math.min(keys.length - 1, Math.max(0, current + direction));
        selectedTimelineBucket = keys[next];
    }

    function handleTimelineKeydown(event: KeyboardEvent): void {
        const target = event.target as HTMLElement | null;
        const tag = target?.tagName?.toLowerCase();
        if (tag === 'input' || tag === 'textarea' || target?.isContentEditable) return;
        if (selectedEvent || showVideo) return;

        if (event.key === '[' || (event.altKey && event.key === 'ArrowLeft')) {
            event.preventDefault();
            moveTimelineSelection(1);
            return;
        }
        if (event.key === ']' || (event.altKey && event.key === 'ArrowRight')) {
            event.preventDefault();
            moveTimelineSelection(-1);
            return;
        }
        if (event.key === '0') {
            selectedTimelineBucket = 'all';
        }
    }

    function clearEventVideoDeepLinkParams() {
        const url = new URL(window.location.href);
        let changed = false;
        if (url.searchParams.has('event')) {
            url.searchParams.delete('event');
            changed = true;
        }
        if (url.searchParams.has('video')) {
            url.searchParams.delete('video');
            changed = true;
        }
        if (changed) {
            window.history.replaceState(null, '', `${url.pathname}${url.search}`);
        }
    }
</script>

<svelte:window onkeydown={handleTimelineKeydown} />

<div class="space-y-6">
    <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
            <h2 class="text-2xl font-bold text-slate-900 dark:text-white">{$_('events.title')}</h2>
            <p class="text-xs text-slate-500">{$_('events.classification_legend')}</p>
        </div>
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
        <button
            type="button"
            class="inline-flex items-center gap-2 px-4 py-2 rounded-xl border text-xs font-black uppercase tracking-widest transition-colors
                {favoritesOnly
                    ? 'bg-amber-100 text-amber-700 border-amber-300 dark:bg-amber-500/20 dark:text-amber-200 dark:border-amber-500/50'
                    : 'bg-white text-slate-600 border-slate-300 hover:bg-slate-50 dark:bg-slate-900/60 dark:text-slate-200 dark:border-slate-700 dark:hover:bg-slate-800'}"
            onclick={() => {
                favoritesOnly = !favoritesOnly;
                currentPage = 1;
                void loadEvents();
            }}
            aria-pressed={favoritesOnly}
            title={$_('events.filters.favorites', { default: 'Favorites only' })}
        >
            <svg class="w-4 h-4" viewBox="0 0 24 24" fill={favoritesOnly ? 'currentColor' : 'none'} stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" d="M11.05 2.927c.3-.921 1.603-.921 1.902 0l2.02 6.217a1 1 0 00.95.69h6.54c.969 0 1.371 1.24.588 1.81l-5.29 3.844a1 1 0 00-.364 1.118l2.02 6.217c.3.921-.755 1.688-1.539 1.118l-5.29-3.844a1 1 0 00-1.175 0l-5.29 3.844c-.783.57-1.838-.197-1.539-1.118l2.02-6.217a1 1 0 00-.364-1.118L.98 11.644c-.783-.57-.38-1.81.588-1.81h6.54a1 1 0 00.95-.69l2.02-6.217z" />
            </svg>
            <span>{$_('events.filters.favorites', { default: 'Favorites' })}</span>
        </button>
    </div>

    <Pagination {currentPage} {totalPages} totalItems={totalCount} itemsPerPage={pageSize} onPageChange={(p) => {currentPage=p; loadEvents()}} onPageSizeChange={(s) => {pageSize=s; currentPage=1; loadEvents()}} />

    {#if error}
        <div class="p-4 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 border border-red-200 dark:border-red-800">
            {error}
            <button onclick={loadEvents} class="ml-2 underline">{$_('common.retry')}</button>
        </div>
    {/if}

    {#if !loading && timelineBuckets.length > 0}
        <div class="card-base rounded-2xl p-3">
            <div class="flex flex-wrap items-center gap-2">
                <button
                    type="button"
                    class="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-[11px] font-black uppercase tracking-widest border transition-colors
                        {selectedTimelineBucket === 'all'
                            ? 'bg-cyan-100/90 dark:bg-cyan-500/20 border-cyan-300/80 dark:border-cyan-400/60 text-cyan-700 dark:text-cyan-100 shadow-sm'
                            : 'bg-white/80 dark:bg-slate-800/60 border-slate-300/80 dark:border-slate-600/70 text-slate-600 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700/70'}"
                    onclick={() => selectedTimelineBucket = 'all'}
                >
                    <svg class="h-3.5 w-3.5" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                        <circle cx="10" cy="10" r="6"></circle>
                        <path d="M4.5 10h11"></path>
                    </svg>
                    <span>{$_('common.all', { default: 'All' })}</span>
                    <span class="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-black normal-case tracking-normal
                        {selectedTimelineBucket === 'all'
                            ? 'bg-cyan-200/80 dark:bg-cyan-400/25 text-cyan-800 dark:text-cyan-100'
                            : 'bg-slate-100 dark:bg-slate-700/60 text-slate-700 dark:text-slate-200'}"
                    >
                        <svg class="h-3 w-3" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                            <path d="M4 14h12"></path>
                            <path d="M7 14V9M10 14V6M13 14v-3"></path>
                        </svg>
                        {events.length}
                    </span>
                </button>
                {#each timelineBuckets as bucket}
                    <button
                        type="button"
                        class="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-[11px] font-black uppercase tracking-widest border transition-colors
                            {selectedTimelineBucket === bucket.key
                                ? 'bg-cyan-100/90 dark:bg-cyan-500/20 border-cyan-300/80 dark:border-cyan-400/60 text-cyan-700 dark:text-cyan-100 shadow-sm'
                                : 'bg-white/80 dark:bg-slate-800/60 border-slate-300/80 dark:border-slate-600/70 text-slate-600 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700/70'}"
                        onclick={() => selectedTimelineBucket = bucket.key}
                    >
                        <svg class="h-3.5 w-3.5" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                            <rect x="3" y="4" width="14" height="13" rx="2"></rect>
                            <path d="M3 8h14"></path>
                        </svg>
                        <span>{bucket.label}</span>
                        <span class="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-black normal-case tracking-normal
                            {selectedTimelineBucket === bucket.key
                                ? 'bg-cyan-200/80 dark:bg-cyan-400/25 text-cyan-800 dark:text-cyan-100'
                                : 'bg-slate-100 dark:bg-slate-700/60 text-slate-700 dark:text-slate-200'}"
                        >
                            <svg class="h-3 w-3" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                                <path d="M4 14h12"></path>
                                <path d="M7 14V9M10 14V6M13 14v-3"></path>
                            </svg>
                            {bucket.count}
                        </span>
                    </button>
                {/each}
            </div>
            <p class="mt-2 inline-flex items-center gap-1.5 text-[11px] text-slate-500 dark:text-slate-400">
                <svg class="h-3.5 w-3.5" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                    <path d="M6 7h8M6 10h8M6 13h5"></path>
                    <rect x="3" y="4" width="14" height="12" rx="2"></rect>
                </svg>
                {$_('events.timeline_keyboard_hint', { default: 'Timeline keyboard: [ previous day, ] next day, 0 reset' })}
            </p>
        </div>
    {/if}

    {#if !loading && visibleEvents.length === 0}
        <div class="card-base rounded-3xl p-10 text-center">
            <div class="text-5xl mb-3">🪶</div>
            <h3 class="text-lg font-semibold text-slate-900 dark:text-white">{$_('events.empty_title')}</h3>
            <p class="text-sm text-slate-500 dark:text-slate-400 mt-2">{$_('events.empty_desc')}</p>
        </div>
    {:else}
        <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
            {#each visibleEvents as event, index (event.frigate_event)}
                <DetectionCard 
                    detection={event} 
                    {index}
                    onclick={() => selectedEvent = event} 
                    onPlay={() => {
                        videoEventId = event.frigate_event;
                        videoShareToken = null;
                        videoPlayIntent = 'user';
                        showVideo = true;
                        selectedEvent = null;
                    }}
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
        llmReady={llmReady}
        showVideoButton={true}
        onClose={() => selectedEvent = null}
        onReclassify={handleReclassify}
        onPlayVideo={(frigateEvent: string, playIntent: 'auto' | 'user' = 'auto') => {
            videoEventId = frigateEvent;
            videoShareToken = null;
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
        shareToken={videoShareToken}
        playIntent={videoPlayIntent}
        onClose={() => {
            showVideo = false;
            videoEventId = null;
            videoShareToken = null;
        }}
    />
{/if}
