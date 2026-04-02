<script lang="ts">
    import { onDestroy, onMount } from 'svelte';
    import {
        fetchEvents,
        fetchEventFilters,
        getThumbnailUrl,
        hideDetection,
        deleteDetection,
        fetchClassifierLabels,
        reclassifyDetection,
        updateDetectionSpecies,
        bulkUpdateDetectionSpecies,
        fetchHiddenCount,
        fetchEventsCount,
        analyzeDetection,
        searchSpecies,
        type Detection,
        type EventFilters,
        type EventFilterSpecies,
        type SearchResult
    } from '../api';
    import { detectionsStore } from '../stores/detections.svelte';
    import { settingsStore } from '../stores/settings.svelte';
    import { fullVisitStore } from '../stores/full-visit.svelte';
    import { authStore } from '../stores/auth.svelte';
    import { toastStore } from '../stores/toast.svelte';
    import { _ } from 'svelte-i18n';
    import Pagination from '../components/Pagination.svelte';
    import DetectionCard from '../components/DetectionCard.svelte';
    import SpeciesDetailModal from '../components/SpeciesDetailModal.svelte';
    import VideoPlayer from '../components/VideoPlayer.svelte';
    import DetectionModal from '../components/DetectionModal.svelte';
    import ReclassificationOverlay from '../components/ReclassificationOverlay.svelte';
    import { toLocalYMD } from '../utils/date-only';

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
    let audioConfirmedOnly = $state(false);
    let sortOrder = $state<'newest' | 'oldest' | 'confidence'>('newest');

    let selectedEvent = $state<Detection | null>(null);
    let selectedSpecies = $state<string | null>(null);
    let pendingEventId = $state<string | null>(null);
    let classifierLabels = $state<string[]>([]);
    let tagSearchQuery = $state('');
    let showTagDropdown = $state(false);
    let updatingTag = $state(false);
    let selectionMode = $state(false);
    let selectedEventIds = $state<string[]>([]);
    let showBulkTagModal = $state(false);
    let bulkTagSearchQuery = $state('');
    let bulkSearchResults = $state<SearchResult[]>([]);
    let bulkTagging = $state(false);
    let bulkTagPendingId = $state<string | null>(null);
    let bulkSearchTimeout: ReturnType<typeof setTimeout> | null = null;
    let bulkSearching = $state(false);
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

    let analyzingAI = $state(false);
    let aiAnalysis = $state<string | null>(null);

    let llmReady = $state(false);
    $effect(() => {
        llmReady = settingsStore.llmReady;
    });

    let eventsSyncFrame: number | null = null;
    let reclassifyCompletionRefreshTimeout: number | null = null;
    let eventMetadataRefreshTimeout: number | null = null;
    let handledVisibleReclassifyCompletions = $state<Record<string, number>>({});
    let refreshingFilterOptions = $state(false);

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
            asNumber(d.video_classification_score)
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
        const fmt = (d: Date) => toLocalYMD(d);
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
                    favoritesOnly,
                    audioConfirmedOnly
                }),
                fetchEventsCount({
                    startDate: range.start,
                    endDate: range.end,
                    species: speciesFilter || undefined,
                    camera: cameraFilter || undefined,
                    includeHidden: showHidden,
                    favoritesOnly,
                    audioConfirmedOnly
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

    async function loadEventMetadata(forceRefresh = false, includeAuxiliary = true): Promise<boolean> {
        let shouldReloadEvents = false;
        try {
            const filters = await fetchEventFilters({ forceRefresh });
            availableSpecies = (filters as EventFilters).species;
            availableCameras = (filters as EventFilters).cameras;
            if (includeAuxiliary) {
                const [labels, hidden] = await Promise.all([
                    fetchClassifierLabels().catch(() => ({ labels: [] })),
                    fetchHiddenCount().catch(() => ({ hidden_count: 0 }))
                ]);
                classifierLabels = labels.labels;
                hiddenCount = hidden.hidden_count;
            }

            if (speciesFilter && !speciesFilter.startsWith('taxa:')) {
                const normalized = speciesFilter.toLowerCase();
                const match = availableSpecies.find((s) => {
                    const display = String(s.display_name || '').toLowerCase();
                    const sci = String(s.scientific_name || '').toLowerCase();
                    const common = String(s.common_name || '').toLowerCase();
                    return display === normalized || sci === normalized || common === normalized;
                });
                if (match && match.value !== speciesFilter) {
                    speciesFilter = match.value;
                    shouldReloadEvents = true;
                }
            }
        } catch {
            // Metadata failures should not block event rendering.
        }
        return shouldReloadEvents;
    }

    async function refreshEventMetadata(forceRefresh = true, reloadEventsIfNeeded = false) {
        if (refreshingFilterOptions) return;
        refreshingFilterOptions = true;
        try {
            const shouldReloadEvents = await loadEventMetadata(forceRefresh, false);
            if (reloadEventsIfNeeded && shouldReloadEvents) {
                currentPage = 1;
                await loadEvents();
            }
        } finally {
            refreshingFilterOptions = false;
        }
    }

    function scheduleEventMetadataRefresh() {
        if (typeof window === 'undefined') {
            void refreshEventMetadata(true, false);
            return;
        }
        if (eventMetadataRefreshTimeout !== null) return;
        eventMetadataRefreshTimeout = window.setTimeout(() => {
            eventMetadataRefreshTimeout = null;
            void refreshEventMetadata(true, false);
        }, 900);
    }

    function handlePageChange(page: number) {
        currentPage = page;
        void loadEvents();
    }

    function handlePageSizeChange(size: number) {
        pageSize = size;
        currentPage = 1;
        void loadEvents();
    }

    onMount(async () => {
        const params = new URLSearchParams(window.location.search);
        if (params.get('species')) speciesFilter = params.get('species')!;
        if (params.get('date')) datePreset = params.get('date') as any;
        if (params.get('favorites') === '1' || params.get('favorites') === 'true') favoritesOnly = true;
        if (params.get('audio') === '1' || params.get('audio') === 'true') audioConfirmedOnly = true;
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

        const metadataTask = loadEventMetadata(false, true);
        await loadEvents();

        const shouldReloadEvents = await metadataTask;
        if (shouldReloadEvents) {
            currentPage = 1;
            await loadEvents();
        }
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

    $effect(() => {
        if (selectedEvent || showVideo) {
            selectionMode = false;
            selectedEventIds = [];
        }
    });

    $effect(() => {
        if (!showBulkTagModal) {
            if (bulkSearchTimeout) {
                clearTimeout(bulkSearchTimeout);
                bulkSearchTimeout = null;
            }
            bulkTagSearchQuery = '';
            bulkSearchResults = [];
            bulkSearching = false;
            bulkTagPendingId = null;
            return;
        }

        const query = bulkTagSearchQuery.trim();
        if (bulkSearchTimeout) {
            clearTimeout(bulkSearchTimeout);
            bulkSearchTimeout = null;
        }

        if (query.length === 0) {
            bulkSearching = true;
            (async () => {
                try {
                    bulkSearchResults = await searchSpecies('', 20, true);
                } catch (e) {
                    console.error('Bulk species search failed', e);
                    bulkSearchResults = classifierLabels.slice(0, 20).map((label) => ({
                        id: label,
                        display_name: label,
                        common_name: null,
                        scientific_name: null
                    }));
                } finally {
                    bulkSearching = false;
                }
            })();
            return;
        }

        bulkSearchTimeout = setTimeout(async () => {
            bulkSearching = true;
            try {
                bulkSearchResults = await searchSpecies(query);
            } catch (e) {
                console.error('Bulk species search failed', e);
                bulkSearchResults = classifierLabels
                    .filter((label) => String(label).toLowerCase().includes(query.toLowerCase()))
                    .map((label) => ({
                        id: String(label),
                        display_name: String(label),
                        common_name: null,
                        scientific_name: null
                    }));
            } finally {
                bulkSearching = false;
            }
        }, 300);
    });

    function applyStoreUpdatesToEventList() {
        if (!events.length) return;
        let changed = false;
        const nextEvents = events.map((event) => {
            const updated = detectionsStore.getDetectionPatch(event.frigate_event);
            if (!updated) return event;
            const definedPatch = Object.fromEntries(
                Object.entries(updated).filter(([, value]) => value !== undefined)
            ) as Partial<Detection>;
            const merged = { ...event, ...definedPatch } as Detection;
            if (detectionSyncSignature(merged) !== detectionSyncSignature(event)) {
                changed = true;
                return merged;
            }
            return event;
        });
        if (changed) {
            events = nextEvents;
        }
    }

    function scheduleEventListSync() {
        if (typeof window === 'undefined') {
            applyStoreUpdatesToEventList();
            return;
        }
        if (eventsSyncFrame !== null) return;
        eventsSyncFrame = window.requestAnimationFrame(() => {
            eventsSyncFrame = null;
            applyStoreUpdatesToEventList();
        });
    }

    function scheduleReclassifyCompletionRefresh() {
        if (typeof window === 'undefined') {
            void loadEvents();
            return;
        }
        if (reclassifyCompletionRefreshTimeout !== null) return;
        reclassifyCompletionRefreshTimeout = window.setTimeout(() => {
            reclassifyCompletionRefreshTimeout = null;
            void loadEvents();
        }, 700);
    }

    $effect(() => {
        if (loading) return;
        if (!events.length) return;
        const _mutationVersion = detectionsStore.mutationVersion;
        void _mutationVersion;
        scheduleEventListSync();
    });

    $effect(() => {
        if (loading) return;
        if (!events.length) return;
        const _mutationVersion = detectionsStore.mutationVersion;
        void _mutationVersion;
        const _progressMap = detectionsStore.progressMap;
        void _progressMap;

        let nextHandled = handledVisibleReclassifyCompletions;
        let handledChanged = false;
        let shouldRefresh = false;

        for (const event of events) {
            const progress = detectionsStore.getReclassificationProgress(event.frigate_event);
            if (!progress || progress.status !== 'completed') continue;
            const completedAt = Number(progress.completedAt ?? progress.lastUpdateAt ?? 0);
            if (!Number.isFinite(completedAt) || completedAt <= 0) continue;
            if ((handledVisibleReclassifyCompletions[event.frigate_event] ?? 0) >= completedAt) continue;

            if (!handledChanged) {
                nextHandled = { ...handledVisibleReclassifyCompletions };
                handledChanged = true;
            }
            nextHandled[event.frigate_event] = completedAt;
            shouldRefresh = true;
        }

        const handledKeys = Object.keys(nextHandled);
        if (handledKeys.length > 512) {
            const activeProgressIds = new Set(detectionsStore.progressMap.keys());
            const visibleIds = new Set(events.map((event) => event.frigate_event));
            const pruned: Record<string, number> = {};
            for (const id of handledKeys) {
                if (activeProgressIds.has(id) || visibleIds.has(id)) {
                    pruned[id] = nextHandled[id];
                }
            }
            nextHandled = pruned;
            handledChanged = true;
        }

        if (handledChanged) {
            handledVisibleReclassifyCompletions = nextHandled;
        }
        if (shouldRefresh) {
            // Batch completions can evict SSE update patches from the recent detections list.
            // A debounced reload ensures Explorer cards converge to backend truth.
            scheduleReclassifyCompletionRefresh();
            // Keep species/camera filter options in sync after batch/manual reclassification updates.
            scheduleEventMetadataRefresh();
        }
    });

    onDestroy(() => {
        if (eventsSyncFrame !== null && typeof window !== 'undefined') {
            window.cancelAnimationFrame(eventsSyncFrame);
            eventsSyncFrame = null;
        }
        if (reclassifyCompletionRefreshTimeout !== null && typeof window !== 'undefined') {
            window.clearTimeout(reclassifyCompletionRefreshTimeout);
            reclassifyCompletionRefreshTimeout = null;
        }
        if (eventMetadataRefreshTimeout !== null && typeof window !== 'undefined') {
            window.clearTimeout(eventMetadataRefreshTimeout);
            eventMetadataRefreshTimeout = null;
        }
        if (bulkSearchTimeout !== null) {
            clearTimeout(bulkSearchTimeout);
            bulkSearchTimeout = null;
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
        const eventId = selectedEvent.frigate_event;
        const requestedStrategy = selectedEvent.has_clip ? 'video' : 'snapshot';
        try {
            const result = await reclassifyDetection(eventId, requestedStrategy);

            // Check if backend used a different strategy (fallback occurred)
            if (result.actual_strategy && result.actual_strategy !== requestedStrategy) {
                toastStore.warning($_('notifications.reclassify_fallback'));
            }
        } catch (e: any) {
            detectionsStore.dismissReclassification(eventId);
            console.error('Failed to start reclassification', e.message);
            toastStore.error($_('notifications.reclassify_failed', { values: { message: e.message || 'Unknown error' } }));
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
            // Update local list
            events = events.map(e => e.frigate_event === eventId ? { ...e, display_name: newSpecies, category_name: newSpecies, manual_tagged: true } : e);
            detectionsStore.updateDetection({ ...selectedEvent, display_name: newSpecies, category_name: newSpecies, manual_tagged: true });
            if (recordingClipFetchEnabled) {
                await fullVisitStore.ensureAvailability(eventId, { refresh: true });
            }
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
        if (!recordingClipFetchEnabled) return;
        for (const event of visibleEvents) {
            void fullVisitStore.ensureAvailability(event.frigate_event);
        }
    });

    $effect(() => {
        if (!recordingClipFetchEnabled || !selectedEvent) return;
        void fullVisitStore.ensureAvailability(selectedEvent.frigate_event);
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
        if (url.searchParams.has('clip')) {
            url.searchParams.delete('clip');
            changed = true;
        }
        if (changed) {
            window.history.replaceState(null, '', `${url.pathname}${url.search}`);
        }
    }

    function eventKey(event: Detection): string {
        const eventId = event?.frigate_event ?? 'unknown';
        const eventIndex = event?.detection_index ?? 0;
        const eventTime = event?.detection_time ?? '';
        return `${eventId}:${eventIndex}:${eventTime}`;
    }

    function getSearchResultNames(result: SearchResult) {
        const common = result.common_name?.trim() || null;
        const scientific = result.scientific_name?.trim() || null;
        const fallback = result.display_name || result.id;
        if (common && scientific && common !== scientific) {
            return { primary: common, secondary: scientific };
        }
        return { primary: common || scientific || fallback, secondary: null };
    }

    function toggleSelectionMode() {
        selectionMode = !selectionMode;
        selectedEventIds = [];
        showBulkTagModal = false;
    }

    function toggleEventSelection(eventId: string) {
        if (selectedEventIds.includes(eventId)) {
            selectedEventIds = selectedEventIds.filter((id) => id !== eventId);
        } else {
            selectedEventIds = [...selectedEventIds, eventId];
        }
    }

    function handleEventCardClick(event: Detection) {
        if (selectionMode) {
            toggleEventSelection(event.frigate_event);
            return;
        }
        selectedEvent = event;
    }

    async function handleFetchFullVisit(event: Detection) {
        try {
            await fullVisitStore.fetchFullVisit(event.frigate_event);
            toastStore.success($_('video_player.full_visit_ready', { default: 'Full visit clip ready' }));
        } catch (e) {
            const message = e instanceof Error ? e.message : $_('video_player.full_visit_failed', { default: 'Could not fetch full visit clip' });
            toastStore.error(message);
        }
    }

    async function applyBulkManualTag(selection: SearchResult) {
        const eventIds = [...selectedEventIds];
        if (!eventIds.length || bulkTagging) return;

        bulkTagging = true;
        bulkTagPendingId = selection.id;
        try {
            const result = await bulkUpdateDetectionSpecies(eventIds, selection.id);
            const appliedSpecies = result.new_species || selection.common_name || selection.scientific_name || selection.display_name || selection.id;
            const updatedSet = new Set(result.updated_event_ids);

            events = events.map((event) => (
                updatedSet.has(event.frigate_event)
                    ? {
                        ...event,
                        display_name: appliedSpecies,
                        category_name: selection.scientific_name ?? selection.display_name ?? selection.id,
                        manual_tagged: true
                    }
                    : event
            ));

            for (const eventId of result.updated_event_ids) {
                const existing = events.find((event) => event.frigate_event === eventId);
                if (existing) {
                    detectionsStore.updateDetection({
                        ...existing,
                        display_name: appliedSpecies,
                        category_name: selection.scientific_name ?? selection.display_name ?? selection.id,
                        manual_tagged: true
                    });
                }
            }

            if (recordingClipFetchEnabled) {
                await Promise.all(result.updated_event_ids.map((eventId) => (
                    fullVisitStore.ensureAvailability(eventId, { refresh: true })
                )));
            }

            showBulkTagModal = false;
            selectionMode = false;
            selectedEventIds = [];
            await loadEvents();
            scheduleEventMetadataRefresh();

            const names = getSearchResultNames(selection);
            toastStore.success(
                `${$_('actions.manual_tag')}: ${names.primary || appliedSpecies} (${result.updated_count})`
            );
            if (result.failed_count > 0 || result.missing_count > 0) {
                toastStore.warning(
                    $_('notifications.reclassify_fallback', {
                        default: `${result.failed_count + result.missing_count} selected events were not updated.`
                    })
                );
            }
        } catch (e: any) {
            toastStore.error($_('notifications.reclassify_failed', { values: { message: e?.message || 'Unknown error' } }));
        } finally {
            bulkTagPendingId = null;
            bulkTagging = false;
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
        <div class="flex items-center gap-3">
            <div class="text-sm text-slate-500">{$_('events.total_count', { values: { count: totalCount } })}</div>
            <button
                type="button"
                class="inline-flex items-center gap-2 rounded-xl border px-3 py-2 text-xs font-black uppercase tracking-widest transition-colors
                    {selectionMode
                        ? 'bg-cyan-100 text-cyan-700 border-cyan-300 dark:bg-cyan-500/20 dark:text-cyan-100 dark:border-cyan-400/60'
                        : 'bg-white text-slate-600 border-slate-300 hover:bg-slate-50 dark:bg-slate-900/60 dark:text-slate-200 dark:border-slate-700 dark:hover:bg-slate-800'}"
                onclick={toggleSelectionMode}
            >
                <span>{selectionMode ? $_('common.cancel') : $_('common.multi_select', { default: 'Multi Select' })}</span>
            </button>
        </div>
    </div>

    {#if selectionMode}
        <div class="card-base rounded-2xl p-4 flex flex-wrap items-center justify-between gap-3 border border-cyan-200/80 dark:border-cyan-500/30 bg-cyan-50/70 dark:bg-cyan-500/10">
            <div>
                <p class="text-sm font-black uppercase tracking-widest text-cyan-700 dark:text-cyan-100">
                    {$_('actions.manual_tag')}
                </p>
                <p class="text-xs text-cyan-700/80 dark:text-cyan-100/80">
                    {selectedEventIds.length
                        ? `${selectedEventIds.length} ${$_('common.selected', { default: 'selected' })}`
                        : $_('common.select', { default: 'Select' }) + ' events to tag together.'}
                </p>
            </div>
            <div class="flex flex-wrap items-center gap-2">
                <button
                    type="button"
                    class="inline-flex items-center gap-2 rounded-xl border px-3 py-2 text-xs font-black uppercase tracking-widest transition-colors bg-white text-slate-600 border-slate-300 hover:bg-slate-50 dark:bg-slate-900/60 dark:text-slate-200 dark:border-slate-700 dark:hover:bg-slate-800"
                    onclick={() => selectedEventIds = []}
                    disabled={selectedEventIds.length === 0}
                >
                    {$_('common.clear', { default: 'Clear' })}
                </button>
                <button
                    type="button"
                    class="inline-flex items-center gap-2 rounded-xl border px-3 py-2 text-xs font-black uppercase tracking-widest transition-colors bg-cyan-600 text-white border-cyan-500 hover:bg-cyan-500 disabled:opacity-50 disabled:cursor-not-allowed"
                    onclick={() => showBulkTagModal = true}
                    disabled={selectedEventIds.length === 0}
                >
                    {$_('actions.manual_tag')}
                </button>
            </div>
        </div>
    {/if}

    <div class="card-base rounded-2xl p-4 space-y-3">
        <div class="grid gap-3 lg:grid-cols-3">
            <select bind:value={datePreset} onchange={loadEvents} class="select-base min-w-0 w-full">
                <option value="all">{$_('events.filters.all_time')}</option><option value="today">{$_('common.today')}</option><option value="week">{$_('events.filters.week')}</option><option value="month">{$_('events.filters.month')}</option><option value="custom">{$_('events.filters.custom')}</option>
            </select>
            <select bind:value={speciesFilter} onchange={loadEvents} class="select-base min-w-0 w-full">
                <option value="">{$_('events.filters.all_species')}</option>{#each availableSpecies as s}<option value={s.value}>{formatSpeciesLabel(s)}</option>{/each}
            </select>
            <select bind:value={cameraFilter} onchange={loadEvents} class="select-base min-w-0 w-full">
                <option value="">{$_('events.filters.all_cameras')}</option>{#each availableCameras as c}<option value={c}>{c}</option>{/each}
            </select>
        </div>
        <div class="flex flex-wrap gap-3">
            <button
            type="button"
            class="inline-flex items-center gap-2 px-3 py-2 rounded-xl border text-xs font-black uppercase tracking-widest transition-colors
                {refreshingFilterOptions
                    ? 'bg-slate-100 text-slate-500 border-slate-300 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700'
                    : 'bg-white text-slate-600 border-slate-300 hover:bg-slate-50 dark:bg-slate-900/60 dark:text-slate-200 dark:border-slate-700 dark:hover:bg-slate-800'}"
            onclick={() => void refreshEventMetadata(true, true)}
            disabled={refreshingFilterOptions}
            title={$_('events.filters.refresh_options', { default: 'Refresh species and camera options' })}
        >
            {#if refreshingFilterOptions}
                <svg class="w-3.5 h-3.5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M4 12a8 8 0 018-8m8 8a8 8 0 01-8 8"></path>
                </svg>
                <span>{$_('events.filters.refreshing_options', { default: 'Refreshing' })}</span>
            {:else}
                <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M4 4v6h6M20 20v-6h-6"></path>
                    <path stroke-linecap="round" stroke-linejoin="round" d="M20 9A8 8 0 005.4 5.4L4 6M4 15a8 8 0 0014.6 3.6L20 18"></path>
                </svg>
                <span>{$_('events.filters.refresh_options', { default: 'Refresh options' })}</span>
            {/if}
            </button>
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
            <button
            type="button"
            class="inline-flex items-center gap-2 px-4 py-2 rounded-xl border text-xs font-black uppercase tracking-widest transition-colors
                {audioConfirmedOnly
                    ? 'bg-blue-100 text-blue-700 border-blue-300 dark:bg-blue-500/20 dark:text-blue-200 dark:border-blue-500/50'
                    : 'bg-white text-slate-600 border-slate-300 hover:bg-slate-50 dark:bg-slate-900/60 dark:text-slate-200 dark:border-slate-700 dark:hover:bg-slate-800'}"
            onclick={() => {
                audioConfirmedOnly = !audioConfirmedOnly;
                currentPage = 1;
                void loadEvents();
            }}
            aria-pressed={audioConfirmedOnly}
            title={$_('events.filters.audio_confirmed_only', { default: 'Audio confirmed only' })}
        >
            <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" />
            </svg>
            <span>{$_('events.filters.audio_confirmed', { default: 'Audio Matches' })}</span>
            </button>
        </div>
    </div>

    <Pagination {currentPage} {totalPages} totalItems={totalCount} itemsPerPage={pageSize} onPageChange={handlePageChange} onPageSizeChange={handlePageSizeChange} />

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
            {#each visibleEvents as event, index (eventKey(event))}
                <DetectionCard 
                    detection={event} 
                    {index}
                    onclick={() => handleEventCardClick(event)}
                    onPlay={() => {
                        videoEventId = event.frigate_event;
                        videoShareToken = null;
                        videoPlayIntent = 'user';
                        showVideo = true;
                        selectedEvent = null;
                    }}
                    onFetchFullVisit={recordingClipFetchEnabled ? () => handleFetchFullVisit(event) : undefined}
                    fullVisitAvailable={fullVisitAvailability[event.frigate_event] === 'available'}
                    fullVisitFetched={fullVisitFetchState[event.frigate_event] === 'ready'}
                    fullVisitFetchState={fullVisitFetchState[event.frigate_event] ?? 'idle'}
                    hideProgress={selectedEvent?.frigate_event === event.frigate_event}
                    selectionMode={selectionMode}
                    selected={selectedEventIds.includes(event.frigate_event)}
                />
            {/each}
        </div>
    {/if}

    <Pagination
        {currentPage}
        {totalPages}
        totalItems={totalCount}
        itemsPerPage={pageSize}
        onPageChange={handlePageChange}
        onPageSizeChange={handlePageSizeChange}
        showPageSize={false}
    />
</div>

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
            videoShareToken = null;
            videoPlayIntent = playIntent;
            showVideo = true;
            selectedEvent = null;
        }}
        onViewSpecies={(species: string) => { selectedSpecies = species; selectedEvent = null; }}
    />
{/if}
{#if selectedSpecies}<SpeciesDetailModal speciesName={selectedSpecies} onclose={() => selectedSpecies = null} />{/if}
{#if showBulkTagModal}
    <div
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
        onclick={(e) => {
            if (e.target === e.currentTarget && !bulkTagging) {
                showBulkTagModal = false;
            }
        }}
        onkeydown={(e) => {
            if ((e.key === 'Escape' || e.key === 'Enter' || e.key === ' ') && e.target === e.currentTarget && !bulkTagging) {
                e.preventDefault();
                showBulkTagModal = false;
            }
        }}
        role="button"
        tabindex="0"
    >
        <div class="w-full max-w-md mx-2 bg-white dark:bg-slate-800 rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-700 overflow-hidden" aria-busy={bulkTagging}>
            <div class="px-5 py-4 border-b border-slate-100 dark:border-slate-700 flex items-center justify-between">
                <div>
                    <h4 class="text-sm font-black text-slate-800 dark:text-slate-100 uppercase tracking-widest">
                        {$_('actions.manual_tag')}
                    </h4>
                    <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">
                        {selectedEventIds.length} {$_('common.selected', { default: 'selected' })}
                    </p>
                </div>
                <button
                    type="button"
                    onclick={() => showBulkTagModal = false}
                    disabled={bulkTagging}
                    class="text-xs font-bold text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
                >
                    {$_('common.cancel')}
                </button>
            </div>
            <div class="p-4 border-b border-slate-100 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50">
                <input
                    type="text"
                    bind:value={bulkTagSearchQuery}
                    disabled={bulkTagging}
                    placeholder={$_('detection.tagging.search_placeholder')}
                    class="w-full px-4 py-2 text-sm rounded-xl border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-700 text-slate-900 dark:text-white focus:ring-2 focus:ring-teal-500 focus:border-transparent outline-none"
                />
            </div>
            <div class="max-h-72 overflow-y-auto overscroll-contain p-1">
                {#each bulkSearchResults as result}
                    {@const names = getSearchResultNames(result)}
                    {@const isPending = bulkTagging && bulkTagPendingId === result.id}
                    <button
                        type="button"
                        onclick={() => applyBulkManualTag(result)}
                        disabled={bulkTagging}
                        class="w-full px-4 py-2.5 text-left text-sm font-medium rounded-lg transition-all touch-manipulation hover:bg-teal-50 dark:hover:bg-teal-900/20 hover:text-teal-600 dark:hover:text-teal-400 disabled:opacity-60 disabled:cursor-wait text-slate-600 dark:text-slate-300"
                    >
                        <span class="block text-sm leading-tight">
                            {names.primary}
                            {#if isPending}
                                <span class="ml-2 inline-flex items-center gap-1 text-[10px] uppercase tracking-wider text-teal-500">
                                    <span class="inline-block h-2 w-2 rounded-full border border-current border-t-transparent animate-spin"></span>
                                    {$_('common.saving')}
                                </span>
                            {/if}
                        </span>
                        {#if names.secondary}
                            <span class="block text-[11px] text-slate-400 dark:text-slate-400 italic">{names.secondary}</span>
                        {/if}
                    </button>
                {/each}
                {#if bulkSearchResults.length === 0}
                    <p class="px-4 py-6 text-sm text-slate-400 italic text-center">
                        {bulkSearching ? $_('common.loading') : $_('detection.tagging.no_results')}
                    </p>
                {/if}
            </div>
        </div>
    </div>
{/if}
{#if showVideo && videoEventId}
    <VideoPlayer
        frigateEvent={videoEventId}
        shareToken={videoShareToken}
        playIntent={videoPlayIntent}
        initialFullVisitPromoted={fullVisitFetchState[videoEventId] === 'ready'}
        onClose={() => {
            showVideo = false;
            videoEventId = null;
            videoShareToken = null;
        }}
    />
{/if}
