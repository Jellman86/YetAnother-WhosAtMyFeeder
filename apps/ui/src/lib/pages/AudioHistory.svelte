<script lang="ts">
    import { MediaQuery } from 'svelte/reactivity';
    import { onMount, untrack } from 'svelte';
    import { _, locale } from 'svelte-i18n';
    import {
        fetchAudioHistory,
        fetchAudioHiddenCount,
        setAudioHidden,
        setAudioHiddenBulk,
        fetchAudioSummary,
        fetchAudioActivityHeatmap,
        fetchSpeciesInfo,
        type AudioActivityHeatmapResponse,
        type AudioHistoryDetection,
        type AudioHistoryResponse,
        type AudioSummaryResponse,
        type SpeciesInfo
    } from '../api';
    import { chartjs, toggleChartSlice, type CanvasChartConfig } from '../actions/chartjs';
    import { themeStore } from '../stores/theme.svelte';
    import { speciesSeriesColor } from '../leaderboard/species-palette';
    import { authStore } from '../stores/auth.svelte';
    import { settingsStore } from '../stores/settings.svelte';
    import { detectionsStore } from '../stores/detections.svelte';
    import { createAudioHistoryLoader } from './audio-history-loader';
    import {
        DEFAULT_AUDIO_HISTORY_FILTERS,
        audioHistoryFiltersDiffer,
        settledAudioHistoryFilters,
        type AudioHistoryFilters
    } from './audio-history-filters';
    import {
        AUDIO_HISTORY_WINDOWS,
        audioHistoryRequest,
        isAudioHistoryWindow,
        msUntilNextLocalMidnight,
        narrowedWindowStart,
        type AudioHistoryRequest,
        type AudioHistoryWindow
    } from './audio-history-window';
    import { withAuthParams } from '../api/core';
    import { appApiPath, toAppPath } from '../app/url-base';
    import { formatCalendarDay, formatDate, formatDateTime, formatHour, formatShortDay, formatTime } from '../utils/datetime';
    import { getErrorMessage, isTransientRequestError } from '../utils/error-handling';
    import { logger } from '../utils/logger';
    import FilterSheet from '../components/ui/FilterSheet.svelte';
    import ChartFigure from '../components/ui/ChartFigure.svelte';
    import Segmented from '../components/ui/Segmented.svelte';
    import ActivityHeatmap from '../components/ActivityHeatmap.svelte';
    import HeatmapSpeciesChips from '../components/HeatmapSpeciesChips.svelte';
    import { busiestHourOfDay, keptHeatmapChoice, weekdayHourTable } from '../leaderboard/heatmap';
    import {
        audioHeatmapReading,
        audioHeatmapSpeciesOptions,
        audioSpeciesHeatmapParams,
        keptSpeciesHeatmap,
        type AudioHeatmapReading
    } from './audio-heatmap-species';
    import LazyModal from '../components/LazyModal.svelte';
    import { loadSpeciesDetailModal } from '../components/lazy-dialogs';
    import { doughnutInsightPlugin } from '../actions/chartjs-doughnut';
    import { audioSpeciesMix } from './audio-species-mix';
    import { SCORE_TEXT, scoreBand } from '../utils/score-tone';
    import { audioReading } from './audio-history-state';
    import { dailySeries } from './audio-chart-series';
    import { namesListedMoreThanOnce, sourceNameKey } from './audio-source-names';
    import { whenNearViewport } from '../actions/near-viewport';

    const PAGE_SIZE = 25;

    let changingVisibility = $state(false);
    let lastVisibilityChange = $state<{ ids: number[]; hidden: boolean } | null>(null);
    let visibilityError = $state<string | null>(null);
    let showHidden = $state(false);
    let hiddenCount = $state(0);
    let selectionMode = $state(false);
    let selectedIds = $state<number[]>([]);
    let searchInput = $state('');
    let appliedSearch = $state('');
    let searchTimer: ReturnType<typeof setTimeout> | null = null;

    let speciesFilter = $state(DEFAULT_AUDIO_HISTORY_FILTERS.species);
    let sourceFilter = $state(DEFAULT_AUDIO_HISTORY_FILTERS.source);
    let minConfidence = $state(DEFAULT_AUDIO_HISTORY_FILTERS.minConfidence);
    // The list, charts and paging follow what was applied, never the half-edited form.
    let applied = $state<AudioHistoryFilters>({ ...DEFAULT_AUDIO_HISTORY_FILTERS });
    const filtersChanged = $derived(
        audioHistoryFiltersDiffer({ window: applied.window, species: speciesFilter, source: sourceFilter, minConfidence }, applied)
    );
    let filterSheetOpen = $state(false);
    const windowOptions = $derived(AUDIO_HISTORY_WINDOWS.map((value) => ({ value, label: windowLabel(value) })));
    // A phone's sheet. From the md breakpoint the fields stand inline, so the sheet, and the scroll
    // lock it holds, go away with the width; a draft then stays in the inline form beside its Apply.
    const inlineFilters = new MediaQuery('min-width: 768px', false);
    const filterSheetShown = $derived(filterSheetOpen && !inlineFilters.current);
    // What the filters narrow the list to, in words, beside the phone's Filters button; the window
    // has its own control beside it.
    const appliedSummary = $derived(
        [
            applied.species.trim(),
            applied.source.trim(),
            applied.minConfidence > 0 ? `≥ ${confidencePercent(applied.minConfidence)}` : ''
        ].filter(Boolean).join(' · ')
    );
    // Spectrograms BirdNET-Go could not render, keyed by its detection id.
    let failedSpectrograms = $state<Record<number, true>>({});
    let history = $state<AudioHistoryResponse | null>(null);
    let summary = $state<AudioSummaryResponse | null>(null);
    let heatmap = $state.raw<AudioActivityHeatmapResponse | null>(null);
    // The grid's own failure, kept for Technical details: the list and summary beside it were read.
    let heatmapError = $state<string | null>(null);
    let loading = $state(true);
    // The read's own words, kept for Technical details; the page states the failure in its own sentence.
    let error = $state<string | null>(null);
    let stale = $state(false);
    let readAt = $state<number | null>(null);
    // What the reading on screen asked for, so the page can say when the server counted less of it.
    let shownRequest = $state.raw<AudioHistoryRequest | null>(null);
    let offset = $state(0);
    let birdnetExternalUrl = $state('');
    let reduceMotion = $state(false);
    let selectedSpecies = $state<string | null>(null);
    let speciesChartEl = $state<HTMLCanvasElement | null>(null);
    let hiddenChartState = $state({ theme: '', indices: [] as number[] });
    let hiddenChartSpecies = $derived(hiddenChartState.theme === `${themeStore.isDark}-${reduceMotion}` ? hiddenChartState.indices : []);

    function toggleSpeciesSlice(index: number) {
        const visible = toggleChartSlice(speciesChartEl, index);
        if (visible === null) return;
        hiddenChartState = {
            theme: `${themeStore.isDark}-${reduceMotion}`,
            indices: visible ? hiddenChartSpecies.filter((item) => item !== index) : [...hiddenChartSpecies, index],
        };
    }

    // Species recognition thumbnails for the top-species summary, reusing the
    // same lazy per-species fetch + cache the visual leaderboard uses. These are a
    // recognition aid (a stock photo of the species), not the bird that was heard —
    // the spectrogram in the detail table is the honest per-detection artifact.
    let speciesInfoCache = $state<Record<string, SpeciesInfo>>({});
    let speciesInfoPending = $state<Record<string, boolean>>({});
    const speciesInfoLocale = $derived((($locale || 'en') as string).split(/[-_]/)[0].toLowerCase());

    function speciesInfoKey(name: string): string {
        return `${speciesInfoLocale}:${name}`;
    }

    function cachedSpeciesThumb(name?: string | null): string | null {
        if (!name) return null;
        return speciesInfoCache[speciesInfoKey(name)]?.thumbnail_url ?? null;
    }

    async function loadSpeciesInfo(name: string) {
        const key = speciesInfoKey(name);
        if (!name || name === 'Unknown Bird' || speciesInfoCache[key] || speciesInfoPending[key]) {
            return;
        }
        speciesInfoPending = { ...speciesInfoPending, [key]: true };
        try {
            const info = await fetchSpeciesInfo(name);
            speciesInfoCache = { ...speciesInfoCache, [key]: info };
        } catch {
            // Enrichment disabled or lookup failed — the list falls back to a neutral icon.
        } finally {
            const { [key]: _discarded, ...rest } = speciesInfoPending;
            speciesInfoPending = rest;
        }
    }

    // The reference photos sit below the log and the charts, so they are fetched only once that list
    // comes near the screen, not as six requests on every visit.
    let topSpeciesNear = $state(false);
    $effect(() => {
        if (!topSpeciesNear) return;
        for (const item of (summary?.top_species ?? []).slice(0, 6)) {
            if (item.species) void loadSpeciesInfo(item.species);
        }
    });

    let detections = $derived<AudioHistoryDetection[]>(history?.items ?? []);
    let pageIds = $derived(detections.map((item) => item.id));
    let allPageSelected = $derived(pageIds.length > 0 && pageIds.every((id) => selectedIds.includes(id)));
    let canPrevious = $derived(offset > 0);
    let canNext = $derived(Boolean(history && offset + history.limit < history.total));
    const canSearchSources = $derived(authStore.canModify || !authStore.isGuest || settingsStore.settings?.public_access_show_camera_names !== false);

    let isDark = $derived(themeStore.isDark);
    // slate-500 on a light page and slate-400 on a dark one: slate-400 on white is 2.56:1, too faint for axis labels.
    let chartTickColor = $derived(isDark ? '#94a3b8' : '#64748b');
    const reading = $derived(audioReading({ loading, error, stale, total: summary?.total ?? null }));
    /** A reading is on screen: numbers can be shown, and zero means none were heard. */
    const measured = $derived(reading === 'ready' || reading === 'empty' || reading === 'stale');
    let hasDaily = $derived((summary?.daily_counts?.length ?? 0) > 0);
    let hasHeatmap = $derived((heatmap?.total_count ?? 0) > 0);
    let hasSpecies = $derived((summary?.top_species?.length ?? 0) > 0);
    // Read from the grid, which is in the viewer's time zone, so the figure names the hour the grid outlines.
    let busiestHour = $derived(busiestHourOfDay(heatmap?.cells ?? []));

    // The grid can show one species' calls: "when does the Robin sing?" is the question the
    // all-species grid cannot answer. The busiest hour above it stays the page's, for all species.
    const heatmapSpeciesOptions = $derived(audioHeatmapSpeciesOptions(summary?.top_species ?? [], applied.species));
    let heatmapChoice = $state<string | null>(null);
    const heatmapSpecies = $derived(keptHeatmapChoice(heatmapChoice, heatmapSpeciesOptions));
    // The filters of the reading on screen. A chip asks under these, never under a window chosen
    // since that is still being read or failed to read, so its grid counts what the figures beside it count.
    let heatmapReading = $state.raw<AudioHeatmapReading | null>(null);
    // Kept with the species it counts and the reading it was read under, so the grid is always named
    // for the data on screen and never stands beside another window's figures.
    let speciesHeatmap = $state.raw<{ key: string; readingKey: string; grid: AudioActivityHeatmapResponse } | null>(null);
    let speciesHeatmapLoading = $state(false);
    let speciesHeatmapError = $state<string | null>(null);
    let speciesHeatmapAttempt = $state(0);
    $effect(() => {
        const requested = heatmapSpecies;
        // Each new reading of the page (window, filters, refresh) asks again under its filters.
        const reading = heatmapReading;
        void speciesHeatmapAttempt;
        if (!requested || !reading) {
            speciesHeatmapLoading = false;
            speciesHeatmapError = null;
            return;
        }
        const params = audioSpeciesHeatmapParams(reading, requested);
        // A quicker second choice aborts this one, so an older answer never lands over it.
        const controller = new AbortController();
        speciesHeatmapLoading = true;
        speciesHeatmapError = null;
        fetchAudioActivityHeatmap(params, controller.signal)
            .then((grid) => {
                if (controller.signal.aborted) return;
                speciesHeatmap = { key: requested, readingKey: reading.key, grid };
                speciesHeatmapLoading = false;
            })
            .catch((failure: unknown) => {
                if (controller.signal.aborted) return;
                speciesHeatmapLoading = false;
                speciesHeatmapError = getErrorMessage(failure) || 'Unable to load calls by hour and weekday.';
                logger.warn('Audio species activity grid fetch failed', { message: speciesHeatmapError });
            });
        return () => controller.abort();
    });
    // While another species loads, the previous one's grid stays (dimmed) under its own name.
    const shownSpeciesHeatmap = $derived(heatmapSpecies && !speciesHeatmapError ? speciesHeatmap : null);
    const shownHeatmap = $derived(heatmapSpecies ? (shownSpeciesHeatmap?.grid ?? null) : heatmap);
    const hasShownHeatmap = $derived((shownHeatmap?.total_count ?? 0) > 0);
    const heatmapSubject = $derived(
        shownSpeciesHeatmap
            ? (heatmapSpeciesOptions.find((option) => option.key === shownSpeciesHeatmap.key)?.label ?? shownSpeciesHeatmap.key)
            : null
    );
    const chosenSpeciesLabel = $derived(heatmapSpeciesOptions.find((option) => option.key === heatmapSpecies)?.label ?? '');
    const heatmapTable = $derived(
        weekdayHourTable(shownHeatmap?.cells ?? [], { day: $_('audio.chart.col_day', { default: 'Day' }), weekday: weekdayLabel, hour: formatHour })
    );

    const audioHistoryLoader = createAudioHistoryLoader({
        resolveRequest: () => audioHistoryRequest(
            { applied, search: appliedSearch, onlyHidden: authStore.canModify && showHidden, offset, pageSize: PAGE_SIZE },
            new Date()
        ),
        requestKey: (request) => request.key,
        fetchHistory: (request) => fetchAudioHistory(request.list),
        fetchSummary: (request) => fetchAudioSummary(request.aggregate),
        fetchHeatmap: (request) => fetchAudioActivityHeatmap(request.aggregate),
        begin: () => { loading = true; error = null; stale = false; },
        apply: (nextHistory, nextSummary, nextHeatmap, request) => {
            history = nextHistory;
            summary = nextSummary;
            shownRequest = request;
            // A species no longer offered in this window goes back to all species. A refresh of the
            // same filters keeps the chosen species' grid, dimmed until it is read again; a grid read
            // for other filters is never shown beside this reading's figures.
            const reading = audioHeatmapReading(request.aggregate);
            heatmapChoice = keptHeatmapChoice(heatmapChoice, audioHeatmapSpeciesOptions(nextSummary.top_species, applied.species));
            speciesHeatmap = keptSpeciesHeatmap(speciesHeatmap, reading);
            heatmapReading = reading;
            if ('heatmap' in nextHeatmap) {
                heatmap = nextHeatmap.heatmap;
                heatmapError = null;
            } else {
                heatmap = null;
                heatmapError = getErrorMessage(nextHeatmap.error) || 'Unable to load calls by hour and weekday.';
                logger.warn('Audio activity grid fetch failed', { message: heatmapError });
            }
            readAt = Date.now();
            hiddenChartState = { theme: '', indices: [] };
        },
        clear: () => {
            history = null;
            summary = null;
            heatmap = null;
            heatmapError = null;
            heatmapReading = null;
            speciesHeatmap = null;
            shownRequest = null;
            readAt = null;
            if (authStore.isGuest) selectedSpecies = null;
        },
        fail: (e, state) => {
            stale = state.stale;
            error = getErrorMessage(e) || 'Unable to load BirdNET history.';
            if (isTransientRequestError(e)) {
                logger.warn('BirdNET history fetch failed (transient)', { message: error });
            } else {
                logger.error('Failed to load BirdNET history', e);
            }
        },
        finish: () => { loading = false; }
    });

    async function refreshHiddenCount(): Promise<void> {
        if (!authStore.canModify) {
            hiddenCount = 0;
            return;
        }
        try {
            const res = await fetchAudioHiddenCount();
            hiddenCount = Math.max(0, res.hidden_count ?? 0);
        } catch {
            // Leave the last known count untouched if the auxiliary count read fails.
        }
    }

    async function loadAudioHistory() {
        await Promise.all([audioHistoryLoader.load(), refreshHiddenCount()]);
    }

    $effect(() => {
        if (authStore.canModify) return;
        if (selectionMode) selectionMode = false;
        if (selectedIds.length > 0) selectedIds = [];
        if (showHidden) {
            showHidden = false;
            offset = 0;
            untrack(() => { void audioHistoryLoader.load(true); });
        }
        hiddenCount = 0;
    });

    let handledPublicHistoryVersion = detectionsStore.publicHistoryVersion;
    $effect(() => {
        const version = detectionsStore.publicHistoryVersion;
        if (version <= handledPublicHistoryVersion || !authStore.isGuest) return;
        handledPublicHistoryVersion = version;
        untrack(() => { void audioHistoryLoader.load(true); });
    });

    async function changeVisibility(id: number, hidden: boolean, recordUndo = true): Promise<void> {
        if (!authStore.canModify || changingVisibility) return;
        changingVisibility = true;
        visibilityError = null;
        try {
            await setAudioHidden(id, hidden);
            lastVisibilityChange = recordUndo ? { ids: [id], hidden } : null;
            selectedIds = selectedIds.filter((item) => item !== id);
            if (detections.length === 1 && offset > 0) offset = Math.max(0, offset - PAGE_SIZE);
            await loadAudioHistory();
        } catch (e) {
            visibilityError = getErrorMessage(e);
        } finally {
            changingVisibility = false;
        }
    }

    async function changeVisibilityBulk(ids: number[], hidden: boolean, recordUndo = true): Promise<void> {
        if (!authStore.canModify || changingVisibility || ids.length === 0) return;
        changingVisibility = true;
        visibilityError = null;
        try {
            const res = await setAudioHiddenBulk(ids, hidden);
            const updatedIds = res.ids.length > 0 ? res.ids : ids;
            lastVisibilityChange = recordUndo ? { ids: updatedIds, hidden } : null;
            selectedIds = selectedIds.filter((item) => !updatedIds.includes(item));
            if (detections.length > 0 && detections.every((item) => updatedIds.includes(item.id)) && offset > 0) {
                offset = Math.max(0, offset - PAGE_SIZE);
            }
            await loadAudioHistory();
        } catch (e) {
            visibilityError = getErrorMessage(e);
        } finally {
            changingVisibility = false;
        }
    }

    async function undoLastVisibilityChange(): Promise<void> {
        if (!lastVisibilityChange) return;
        const { ids, hidden } = lastVisibilityChange;
        if (ids.length === 1) {
            await changeVisibility(ids[0], !hidden, false);
        } else {
            await changeVisibilityBulk(ids, !hidden, false);
        }
    }

    function toggleShowHidden(): void {
        if (!authStore.canModify) return;
        showHidden = !showHidden;
        selectedIds = [];
        lastVisibilityChange = null;
        visibilityError = null;
        offset = 0;
        void loadAudioHistory();
    }

    function toggleSelectionMode(): void {
        if (!authStore.canModify) return;
        selectionMode = !selectionMode;
        if (!selectionMode) selectedIds = [];
    }

    function toggleRowSelected(id: number): void {
        if (selectedIds.includes(id)) {
            selectedIds = selectedIds.filter((item) => item !== id);
        } else {
            selectedIds = [...selectedIds, id];
        }
    }

    function toggleSelectAllPage(): void {
        if (allPageSelected) {
            const pageSet = new Set(pageIds);
            selectedIds = selectedIds.filter((id) => !pageSet.has(id));
        } else {
            selectedIds = [...new Set([...selectedIds, ...pageIds])];
        }
    }

    function handleRowClick(event: MouseEvent, id: number): void {
        if (!selectionMode || !authStore.canModify) return;
        const target = event.target as HTMLElement | null;
        if (target?.closest('a, button, input, label')) return;
        toggleRowSelected(id);
    }

    function applySearchNow(): void {
        if (searchTimer) {
            clearTimeout(searchTimer);
            searchTimer = null;
        }
        const next = searchInput.trim();
        if (next === appliedSearch) return;
        appliedSearch = next;
        selectedIds = [];
        offset = 0;
        void audioHistoryLoader.load();
    }

    function handleSearchInput(): void {
        if (searchTimer) clearTimeout(searchTimer);
        searchTimer = setTimeout(() => {
            searchTimer = null;
            applySearchNow();
        }, 250);
    }

    function submitSearch(event: SubmitEvent): void {
        event.preventDefault();
        applySearchNow();
    }

    function clearSearch(): void {
        searchInput = '';
        applySearchNow();
    }

    async function loadBirdnetUrl() {
        if (!authStore.showSettings) {
            birdnetExternalUrl = '';
            return;
        }
        try {
            const settings = await settingsStore.read();
            birdnetExternalUrl = settings.birdnet_external_url || settings.birdnet_url || '';
        } catch {
            birdnetExternalUrl = '';
        }
    }

    function windowLabel(window: AudioHistoryWindow): string {
        if (window === 'today') return $_('audio.filter.today', { default: 'Today' });
        if (window === '24h') return $_('audio.filter.24h', { default: 'Last 24 hours' });
        if (window === '7d') return $_('audio.filter.7d', { default: 'Last 7 days' });
        if (window === '30d') return $_('audio.filter.30d', { default: 'Last 30 days' });
        if (window === '90d') return $_('audio.filter.90d', { default: 'Last 90 days' });
        return $_('audio.filter.1y', { default: 'Last 365 days' });
    }

    function weekdayLabel(dayOfWeek: number): string {
        if (dayOfWeek === 1) return $_('leaderboard.weekday_mon', { default: 'Mon' });
        if (dayOfWeek === 2) return $_('leaderboard.weekday_tue', { default: 'Tue' });
        if (dayOfWeek === 3) return $_('leaderboard.weekday_wed', { default: 'Wed' });
        if (dayOfWeek === 4) return $_('leaderboard.weekday_thu', { default: 'Thu' });
        if (dayOfWeek === 5) return $_('leaderboard.weekday_fri', { default: 'Fri' });
        if (dayOfWeek === 6) return $_('leaderboard.weekday_sat', { default: 'Sat' });
        return $_('leaderboard.weekday_sun', { default: 'Sun' });
    }

    /**
     * The window the server counted, which for a guest is the shared one, not the one chosen. Today's
     * is in hours. Only a reading on screen has a range: while another window, or the next day, is
     * read the dates stay hidden, so a period's name never stands beside another period's dates.
     */
    function windowRange(): string {
        if (!measured || !summary?.window_start || !summary.window_end) return '';
        const format = shownRequest?.aggregate.start_date ? formatTime : formatShortDay;
        return `${format(summary.window_start)}-${format(summary.window_end)}`;
    }

    // For a guest the shared history can start after the viewer's own midnight, so Today holds less of the day.
    const sharedFrom = $derived(
        measured && authStore.isGuest ? narrowedWindowStart(shownRequest?.aggregate.start_date, summary?.window_start) : null
    );
    const nothingNarrows = $derived(!applied.species && !applied.source && applied.minConfidence <= 0 && !appliedSearch);

    const listedSources = $derived((summary?.sources ?? []).slice(0, 8));
    const sharedSourceNames = $derived(namesListedMoreThanOnce(listedSources));

    function callsHeard(count: number): string {
        return $_('audio.calls_heard', { values: { count }, default: '{count, plural, one {# call heard} other {# calls heard}}' });
    }

    /** The window applies as it is chosen, as the Leaderboard's span does; the other filters wait for Apply. */
    function chooseWindow(next: string): void {
        if (!isAudioHistoryWindow(next) || next === applied.window) return;
        applied = { ...applied, window: next };
        offset = 0;
        selectedIds = [];
        void loadAudioHistory();
    }

    // Today ends at the viewer's midnight; past it the page reads the new day instead of standing on
    // the old one. The clock is outside Svelte, so this is an effect. A timer can fire a little early,
    // so it waits a second past midnight to be sure the new day has begun.
    $effect(() => {
        if (applied.window !== 'today') return;
        let timer: ReturnType<typeof setTimeout>;
        const waitForMidnight = () => {
            timer = setTimeout(() => {
                offset = 0;
                selectedIds = [];
                void loadAudioHistory();
                waitForMidnight();
            }, msUntilNextLocalMidnight(new Date()) + 1000);
        };
        waitForMidnight();
        return () => clearTimeout(timer);
    });

    function applyFilters(event?: SubmitEvent) {
        event?.preventDefault();
        applied = settledAudioHistoryFilters({ window: applied.window, species: speciesFilter, source: sourceFilter, minConfidence });
        offset = 0;
        void loadAudioHistory();
    }

    /** Leaving the sheet without Apply leaves the list as it was, so the fields go back to what it shows. */
    function dismissFilterSheet(): void {
        speciesFilter = applied.species;
        sourceFilter = applied.source;
        minConfidence = applied.minConfidence;
        filterSheetOpen = false;
    }

    /** Clears what narrows the list; the window is its own control and stays as chosen. */
    function clearFilters() {
        speciesFilter = DEFAULT_AUDIO_HISTORY_FILTERS.species;
        sourceFilter = DEFAULT_AUDIO_HISTORY_FILTERS.source;
        minConfidence = DEFAULT_AUDIO_HISTORY_FILTERS.minConfidence;
        searchInput = '';
        appliedSearch = '';
        if (searchTimer) {
            clearTimeout(searchTimer);
            searchTimer = null;
        }
        applied = { ...DEFAULT_AUDIO_HISTORY_FILTERS, window: applied.window };
        selectedIds = [];
        offset = 0;
        void loadAudioHistory();
    }

    function previousPage() {
        if (!canPrevious) return;
        offset = Math.max(0, offset - PAGE_SIZE);
        selectedIds = [];
        void loadAudioHistory();
    }

    function nextPage() {
        if (!canNext) return;
        offset += PAGE_SIZE;
        selectedIds = [];
        void loadAudioHistory();
    }

    function confidencePercent(value: number | null | undefined): string {
        return `${Math.round((value ?? 0) * 100)}%`;
    }

    function spectrogramUrl(birdnet_id: number | null | undefined): string | null {
        if (!birdnet_id) return null;
        // Loaded as an <img> src; append the JWT as a query param so it works
        // when authentication is enabled (mirrors Frigate media URLs and RecentAudio).
        return withAuthParams(`${appApiPath(`/audio/spectrogram/${birdnet_id}`)}?width=300`);
    }

    function markSpectrogramFailed(birdnetId: number | null | undefined): void {
        if (birdnetId) failedSpectrograms = { ...failedSpectrograms, [birdnetId]: true };
    }

    function birdnetDetectionUrl(birdnet_id: number | null | undefined): string | null {
        if (!birdnetExternalUrl || !birdnet_id) return null;
        return `${birdnetExternalUrl.replace(/\/$/, '')}/ui/detections/${birdnet_id}`;
    }

    // Calls over time take the colour theme's primary, as the Leaderboard trend does;
    // species take the shared colour-blind-safe species palette, so a species reads the same here.
    let audioPrimary = $derived(themeStore.colorTheme === 'bluetit' ? '#2563eb' : '#0d9488');
    let audioPrimaryFill = $derived(themeStore.colorTheme === 'bluetit' ? 'rgba(37,99,235,0.18)' : 'rgba(13,148,136,0.18)');
    function audioSpeciesColor(index: number): string {
        return speciesSeriesColor(index, isDark);
    }

    // One series per chart, drawn by the canvas and listed by its table, so the two always agree.
    const dailyPoints = $derived(dailySeries(summary?.daily_counts ?? [], formatCalendarDay));

    let dailyChartConfig = $derived((): CanvasChartConfig => {
        const points = summary?.daily_counts ?? [];
        const labels = dailyPoints.map((point) => point.label);
        return {
            type: 'line',
            data: {
                labels,
                datasets: [{
                    label: $_('audio.chart.heard', { default: 'Heard' }),
                    data: dailyPoints.map((point) => point.count),
                    borderColor: audioPrimary,
                    backgroundColor: audioPrimaryFill,
                    fill: true,
                    tension: 0.3,
                    pointRadius: points.length > 45 ? 0 : 2,
                    pointHoverRadius: 5,
                    borderWidth: 2,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: reduceMotion ? false : { duration: 250 },
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: { display: false },
                    tooltip: { callbacks: { title: (items) => points[items[0]?.dataIndex]?.date ?? '' } },
                },
                scales: {
                    x: { ticks: { color: chartTickColor, maxTicksLimit: 6 }, grid: { display: false } },
                    y: { beginAtZero: true, ticks: { color: chartTickColor, precision: 0 }, grid: { color: isDark ? 'rgba(148,163,184,0.12)' : 'rgba(148,163,184,0.2)' } },
                },
            },
        };
    });

    // The ring's slices total the page's "Heard" figure: the named species, then all the others.
    let speciesMix = $derived(
        audioSpeciesMix(summary?.top_species ?? [], summary?.total, $_('audio.chart.other_species', { default: 'Other species' }), 8)
    );
    let otherSpeciesColor = $derived(isDark ? '#64748b' : '#94a3b8');

    let speciesDonutConfig = $derived((): CanvasChartConfig => {
        const top = speciesMix;
        const values = top.map((species) => species.count);
        const totalLabel = $_('audio.chart.heard', { default: 'Heard' });
        const centerTotal = doughnutInsightPlugin('audioCenterTotal', values, totalLabel, isDark);
        return {
            type: 'doughnut',
            data: {
                labels: top.map((species) => species.species),
                datasets: [{ data: values, backgroundColor: top.map((slice, index) => (slice.other ? otherSpeciesColor : audioSpeciesColor(index))), borderColor: isDark ? '#1e293b' : '#ffffff', borderWidth: 1.5 }],
            },
            plugins: [centerTotal],
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: reduceMotion ? false : { duration: 250 },
                cutout: '62%',
                plugins: {
                    legend: { display: false },
                    tooltip: { callbacks: { label: (item) => `${item.label}: ${item.formattedValue}` } },
                },
            },
        };
    });

    onMount(() => {
        const motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)');
        const syncMotionPreference = () => {
            reduceMotion = motionPreference.matches || document.documentElement.classList.contains('reduced-motion');
        };
        const classObserver = new MutationObserver(syncMotionPreference);
        syncMotionPreference();
        motionPreference.addEventListener('change', syncMotionPreference);
        classObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
        void loadAudioHistory();
        void loadBirdnetUrl();
        return () => {
            if (searchTimer) clearTimeout(searchTimer);
            audioHistoryLoader.dispose();
            motionPreference.removeEventListener('change', syncMotionPreference);
            classObserver.disconnect();
        };
    });
</script>

{#if !authStore.canViewAudio}
    <!-- Audio is the owner's to share (#291); a visitor gets words, not errors. -->
    <section data-audio-not-shared class="mx-auto max-w-lg py-16 text-center">
        <p class="text-sm font-semibold text-strong">
            {$_('audio.not_shared_title', { default: 'Audio is not shared publicly' })}
        </p>
        <p class="mt-1 text-sm text-muted">
            {$_('audio.not_shared_body', { default: 'The owner of this instance has turned off audio for guests.' })}
        </p>
    </section>
{:else}

{#snippet statValue(value: string, unavailable: boolean = false)}
    {#if measured && !unavailable}
        <dd class="mt-1 font-display text-2xl font-bold tabular-nums text-strong">{value}</dd>
    {:else if reading === 'failed' || (measured && unavailable)}
        <!-- Not measured, so said in words at body size, never as a zero (layout-patterns 5). -->
        <dd class="mt-2 text-sm font-semibold text-ink" data-audio-stat-unavailable>{$_('audio.stat.not_available', { default: 'Not available' })}</dd>
    {:else}
        <dd class="mt-1 h-8" data-audio-stat-pending>
            <span class="block h-7 w-16 animate-pulse rounded-md bg-surface-raised motion-reduce:animate-none" aria-hidden="true"></span>
            <span class="sr-only">{$_('common.loading', { default: 'Loading' })}</span>
        </dd>
    {/if}
{/snippet}

{#snippet technicalDetails(text: string)}
    <details class="group">
        <summary class="flex min-h-11 cursor-pointer items-center gap-1.5 text-xs font-semibold text-ink focus-ring">
            <svg class="h-3.5 w-3.5 shrink-0 transition-transform duration-200 group-open:rotate-90" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="m8 5 5 5-5 5" /></svg>
            {$_('common.technical_details', { default: 'Technical details' })}
        </summary>
        <p class="pb-1 font-mono text-xs wrap-anywhere text-ink">{text}</p>
    </details>
{/snippet}

{#snippet chartPending()}
    {#if reading === 'failed'}
        <div class="flex h-60 items-center justify-center px-4 text-center text-sm font-semibold text-ink" data-audio-chart-unavailable>{$_('audio.chart.unavailable', { default: 'Not available while the history cannot be read.' })}</div>
    {:else}
        <div class="mt-3 h-60 animate-pulse bg-surface-raised motion-reduce:animate-none" aria-hidden="true"></div>
    {/if}
{/snippet}

{#snippet filterFields()}
            <label class="block space-y-1.5">
                <span class="block text-xs font-semibold leading-4 text-muted">{$_('audio.filter.species', { default: 'Species' })}</span>
                <input bind:value={speciesFilter} class="input-base min-h-11 focus-visible:ring-2 focus-visible:ring-focus" placeholder={$_('audio.filter.species_placeholder', { default: 'Any species' })} />
            </label>
            <label class="block space-y-1.5">
                <span class="block text-xs font-semibold leading-4 text-muted">{$_('audio.filter.source', { default: 'Source' })}</span>
                <input bind:value={sourceFilter} class="input-base min-h-11 focus-visible:ring-2 focus-visible:ring-focus" placeholder={$_('audio.filter.source_placeholder', { default: 'Any source' })} />
            </label>
            <label class="block space-y-1.5">
                <span class="flex justify-between gap-2 text-xs font-semibold leading-4 text-muted">
                    <span>{$_('audio.filter.min_confidence', { default: 'Min confidence' })}</span>
                    <span class="tabular-nums text-accent-ink">{confidencePercent(minConfidence)}</span>
                </span>
                <input bind:value={minConfidence} type="range" min="0" max="1" step="0.05" class="block min-h-11 w-full accent-accent focus-visible:ring-2 focus-visible:ring-focus" aria-valuetext={confidencePercent(minConfidence)} />
            </label>
{/snippet}

{#snippet filterActions(after?: () => void)}
    <div class="flex flex-wrap items-end gap-2">
        <button type="submit" class="btn btn-primary min-h-11 px-4" disabled={loading}>{$_('common.apply', { default: 'Apply' })}</button>
        <button type="button" class="btn btn-secondary min-h-11 px-4" onclick={() => { clearFilters(); after?.(); }} disabled={loading}>{$_('common.clear', { default: 'Clear' })}</button>
    </div>
{/snippet}

<div class="space-y-10" data-audio-history-page data-audio-reading={reading}>
    <!-- The window first, in the Leaderboard's place and with its control: below 768 px a select beside
         the Filters button, from 768 px a segmented bar, where its six period names fit on one line. It
         applies as it is chosen; what narrows the list (species, source, confidence) waits for Apply,
         inline from 768 px and in a sheet below. -->
    <section class="border-y border-line py-3 sm:py-4" data-audio-history-controls data-audio-history-filters aria-label={$_('events.filters.title', { default: 'Filters' })}>
        <div class="flex flex-wrap items-center gap-x-4 gap-y-3">
            <label class="md:hidden">
                <span class="sr-only">{$_('audio.filter.window', { default: 'Window' })}</span>
                <select class="select-base min-h-11 w-auto py-2 text-sm" value={applied.window} onchange={(event) => chooseWindow(event.currentTarget.value)} data-audio-window-select>
                    {#each windowOptions as option (option.value)}<option value={option.value}>{option.label}</option>{/each}
                </select>
            </label>
            <div class="hidden md:block">
                <Segmented
                    value={applied.window}
                    options={windowOptions}
                    onchange={(next) => chooseWindow(next)}
                    label={$_('audio.filter.window', { default: 'Window' })}
                    width="content"
                    size="sm"
                    data-audio-window-bar
                />
            </div>
            <div class="flex min-w-0 flex-1 items-center justify-end gap-3 md:hidden">
                <p class="min-w-0 text-right text-sm text-muted" data-audio-filters-summary>{appliedSummary}</p>
                <button type="button" class="btn btn-secondary min-h-11 shrink-0 px-4" aria-haspopup="dialog" aria-expanded={filterSheetShown} aria-controls="audio-filter-sheet" onclick={() => (filterSheetOpen = true)} data-audio-filters-open>
                    {$_('events.filters.title', { default: 'Filters' })}
                </button>
            </div>
        </div>
        <form class="mt-4 hidden md:grid md:grid-cols-3 md:gap-4 xl:grid-cols-4" onsubmit={applyFilters}>
            {@render filterFields()}
            <div class="md:col-span-3 xl:col-span-1 xl:self-end">{@render filterActions()}</div>
        </form>
        <p class="{filtersChanged ? 'mt-3' : ''} text-sm font-semibold text-status-attention" role="status" data-audio-filters-changed>{filtersChanged ? $_('audio.filter.changed', { default: 'Filters changed. Apply to update the list.' }) : ''}</p>
        {#if sharedFrom}
            <p class="mt-3 text-sm text-muted" data-audio-window-narrowed>{$_('audio.filter.shared_from', { values: { time: formatTime(sharedFrom) }, default: 'Shared history starts at {time}, so calls heard earlier today are not shown.' })}</p>
        {/if}
    </section>
    {#if filterSheetShown}
        <FilterSheet title={$_('events.filters.title', { default: 'Filters' })} id="audio-filter-sheet" onclose={dismissFilterSheet} data-audio-filter-sheet>
            <form class="grid gap-4" onsubmit={(event) => { applyFilters(event); filterSheetOpen = false; }}>
                {@render filterFields()}
                {@render filterActions(() => (filterSheetOpen = false))}
            </form>
        </FilterSheet>
    {/if}

    <!-- The window's figures come first, as the Leaderboard's standing figures do: on a phone above
         the log, so the reader sees how the window stands before 25 rows of calls. At 1280 px and
         wider the log has the main column across both rows and the figures, then the most heard
         species and the sources, stand beside it in the right-hand column. Rendered once, placed by
         the grid. -->
    <div class="grid grid-cols-1 gap-10 xl:grid-cols-12 xl:gap-x-10 xl:gap-y-8" data-audio-history-layout>
    <!-- The Leaderboard's standing band: the same ruled list, figures and spacing, in the same
         order (species, the count, the busiest hour), with this page's own unit, calls heard. -->
    <section class="min-w-0 xl:col-span-4 xl:col-start-9 xl:row-start-1 2xl:col-span-3 2xl:col-start-10" aria-labelledby="audio-summary-title" aria-busy={reading === 'loading'} data-audio-history-summary>
        <h2 id="audio-summary-title" class="sr-only">{$_('audio.summary_title', { default: 'This window' })}</h2>
        <div class="@container">
        <dl class="grid grid-cols-1 gap-x-6 gap-y-5 border-y border-line py-5 @xs:grid-cols-2 @2xl:grid-cols-4" data-audio-standing>
            <div class="min-w-0">
                <dt class="text-xs font-semibold text-muted">{$_('audio.stat.species', { default: 'Species' })}</dt>
                {@render statValue((summary?.species_count ?? 0).toLocaleString())}
                <dd class="text-xs text-muted">{$_('audio.stat.species_sub', { default: 'Heard in this window' })}</dd>
            </div>
            <div class="min-w-0">
                <dt class="text-xs font-semibold text-muted">{$_('audio.stat.heard', { default: 'Calls heard' })}</dt>
                {@render statValue((summary?.total ?? 0).toLocaleString())}
                <dd class="text-xs text-muted">{$_('audio.stat.heard_sub', { default: 'Calls BirdNET-Go heard in this window' })}</dd>
            </div>
            <div class="min-w-0">
                <dt class="text-xs font-semibold text-muted">{$_('audio.stat.busiest_hour', { default: 'Busiest hour' })}</dt>
                {@render statValue(busiestHour ? formatHour(busiestHour.hour) : '—', heatmapError !== null)}
                {#if measured && heatmapError === null}
                    <dd class="text-xs text-muted">{busiestHour ? callsHeard(busiestHour.count) : $_('audio.stat.no_calls', { default: 'No calls in this window' })}</dd>
                {/if}
            </div>
            <div class="min-w-0">
                <dt class="text-xs font-semibold text-muted">{$_('audio.stat.sources', { default: 'Sources' })}</dt>
                {@render statValue((summary?.source_count ?? 0).toLocaleString())}
                <dd class="text-xs text-muted">{$_('audio.stat.sources_sub', { default: 'Microphones or streams' })}</dd>
            </div>
        </dl>
        </div>
    </section>
    <div class="min-w-0 space-y-6 xl:col-span-8 xl:col-start-1 xl:row-span-2 xl:row-start-1 2xl:col-span-9">

    <section class="space-y-5" data-audio-history-log aria-labelledby="audio-history-title">
        <div class="flex flex-wrap items-start justify-between gap-3">
            <div class="min-w-0 max-w-prose">
                <h2 id="audio-history-title" class="text-xl font-bold text-strong">{$_('audio.history.title', { default: 'Call history' })}</h2>
                <p class="mt-1 text-sm text-muted">{$_('audio.history.sub', { default: 'Every call BirdNET-Go reported, kept apart from camera visits.' })}</p>
            </div>
            <div class="flex flex-wrap items-center gap-2">
                {#if authStore.canModify}
                    <button
                        type="button"
                        class="btn {showHidden ? 'btn-primary' : 'btn-secondary'} min-h-11 flex-none gap-2 px-3.5 text-sm focus-visible:ring-2 focus-visible:ring-focus"
                        aria-pressed={showHidden}
                        onclick={toggleShowHidden}
                        disabled={loading || changingVisibility}
                        data-audio-hidden-toggle
                    >
                        <svg aria-hidden="true" class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M3 3l18 18M10.58 10.58a2 2 0 1 0 2.83 2.83M9.88 5.09A10.94 10.94 0 0 1 12 4.9c5.05 0 9.27 3.11 10.5 7.1a10.7 10.7 0 0 1-4.18 5.26M6.61 6.61A10.73 10.73 0 0 0 1.5 12c1.23 3.99 5.45 7.1 10.5 7.1 1.61 0 3.14-.33 4.5-.92" />
                        </svg>
                        <span>{$_('audio.history.hidden_toggle', { default: 'Hidden' })}</span>
                        {#if hiddenCount > 0}
                            <span class="rounded-full bg-surface-raised px-2 py-0.5 text-xs font-bold tabular-nums text-strong" data-audio-hidden-count>{hiddenCount.toLocaleString()}</span>
                        {/if}
                    </button>
                    <button
                        type="button"
                        class="btn {selectionMode ? 'btn-primary' : 'btn-secondary'} min-h-11 flex-none gap-2 px-3.5 text-sm focus-visible:ring-2 focus-visible:ring-focus"
                        aria-pressed={selectionMode}
                        onclick={toggleSelectionMode}
                        disabled={changingVisibility}
                        data-audio-multiselect-toggle
                    >
                        <svg aria-hidden="true" class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <rect x="3" y="3" width="18" height="18" rx="3" />
                            <path stroke-linecap="round" stroke-linejoin="round" d="m8.5 12 2.5 2.5 4.5-5" />
                        </svg>
                        <span>{$_('common.multi_select', { default: 'Multi-select' })}</span>
                    </button>
                {/if}
                <button type="button" class="btn btn-secondary min-h-11 flex-none px-4 text-sm focus-visible:ring-2 focus-visible:ring-focus" onclick={() => void loadAudioHistory()} disabled={loading}>
                    <svg aria-hidden="true" class="mr-2 h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M20 12a8 8 0 10-2.34 5.66M20 12v-5m0 5h-5" /></svg>
                    {$_('common.refresh', { default: 'Refresh' })}
                </button>
            </div>
        </div>

        <form class="relative flex items-center" role="search" onsubmit={submitSearch} data-audio-search-form>
            <label class="relative block w-full">
                <span class="sr-only">{$_('audio.history.search_label', { default: 'Search call history' })}</span>
                <svg aria-hidden="true" class="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="11" cy="11" r="7" />
                    <path stroke-linecap="round" stroke-linejoin="round" d="m20 20-3.5-3.5" />
                </svg>
                <input
                    type="search"
                    bind:value={searchInput}
                    oninput={handleSearchInput}
                    class="input-base min-h-11 w-full pl-10 pr-12 text-sm focus-visible:ring-2 focus-visible:ring-focus"
                    placeholder={canSearchSources
                        ? $_('audio.history.search_placeholder', { default: 'Search species or source…' })
                        : $_('audio.history.search_species_placeholder', { default: 'Search species…' })}
                    data-audio-search-input
                />
            </label>
            {#if searchInput.length > 0}
                <button
                    type="button"
                    class="btn btn-ghost absolute right-0.5 top-1/2 min-h-11 min-w-11 -translate-y-1/2 p-0 text-muted hover:text-strong focus-visible:ring-2 focus-visible:ring-focus"
                    onclick={clearSearch}
                    aria-label={$_('audio.history.clear_search', { default: 'Clear search' })}
                    data-audio-search-clear
                >
                    <svg aria-hidden="true" class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12" /></svg>
                </button>
            {/if}
        </form>

        {#if authStore.canModify}
            <p class="max-w-prose text-sm text-muted">{$_('audio.history.local_only')}</p>
            {#if showHidden}
                <div class="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line bg-surface-raised px-4 py-3 text-sm" role="status" data-audio-viewing-hidden>
                    <p class="text-ink">{$_('audio.history.viewing_hidden', { default: 'Showing hidden calls. Restore any call to include it in YA-WAMF history and audio matching again.' })}</p>
                    <button type="button" class="btn btn-secondary min-h-11 shrink-0 px-3.5 text-xs focus-visible:ring-2 focus-visible:ring-focus" onclick={toggleShowHidden}>
                        {$_('audio.history.back_to_visible', { default: 'Show visible calls' })}
                    </button>
                </div>
            {/if}
            {#if selectionMode}
                <div class="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-accent-line bg-accent-soft p-4" data-audio-selection-bar>
                    <div>
                        <p class="text-sm font-semibold text-accent-ink">{$_('common.multi_select', { default: 'Multi-select' })}</p>
                        <p class="text-xs text-accent-ink" role="status" data-audio-selection-count>
                            {$_('audio.history.selection_count', {
                                values: { count: selectedIds.length },
                                default: '{count, plural, =0 {No calls selected} one {# call selected} other {# calls selected}}'
                            })}
                        </p>
                    </div>
                    <div class="flex flex-wrap items-center gap-2">
                        <button
                            type="button"
                            class="btn btn-secondary min-h-11 px-3 py-2 text-xs focus-visible:ring-2 focus-visible:ring-focus"
                            onclick={toggleSelectAllPage}
                            disabled={pageIds.length === 0 || changingVisibility}
                            data-audio-select-all
                        >
                            {allPageSelected ? $_('audio.history.deselect_page', { default: 'Deselect page' }) : $_('audio.history.select_page', { default: 'Select page' })}
                        </button>
                        <button
                            type="button"
                            class="btn btn-ghost min-h-11 px-3 py-2 text-xs focus-visible:ring-2 focus-visible:ring-focus"
                            onclick={() => (selectedIds = [])}
                            disabled={selectedIds.length === 0 || changingVisibility}
                        >
                            {$_('common.clear', { default: 'Clear' })}
                        </button>
                        <button
                            type="button"
                            class="btn btn-primary min-h-11 px-3 py-2 text-xs focus-visible:ring-2 focus-visible:ring-focus"
                            onclick={() => void changeVisibilityBulk(selectedIds, !showHidden)}
                            disabled={selectedIds.length === 0 || changingVisibility || loading}
                            data-audio-bulk-visibility
                        >
                            {#if changingVisibility}
                                {$_('common.working', { default: 'Working…' })}
                            {:else if showHidden}
                                {$_('audio.history.restore_selected', { default: 'Restore selected' })}
                            {:else}
                                {$_('audio.history.hide_selected', { default: 'Hide selected' })}
                            {/if}
                        </button>
                        <button
                            type="button"
                            class="btn btn-ghost min-h-11 px-3 py-2 text-xs focus-visible:ring-2 focus-visible:ring-focus"
                            onclick={toggleSelectionMode}
                            disabled={changingVisibility}
                            data-audio-selection-done
                        >
                            {$_('events.selection_done', { default: 'Done' })}
                        </button>
                    </div>
                </div>
            {/if}
            {#if lastVisibilityChange !== null}
                <div class="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line p-3 text-sm" role="status" data-audio-visibility-status>
                    <span>
                        {lastVisibilityChange.hidden
                            ? $_('audio.history.hidden_count_message', {
                                values: { count: lastVisibilityChange.ids.length },
                                default: '{count, plural, one {Call hidden.} other {# calls hidden.}}'
                            })
                            : $_('audio.history.restored_count_message', {
                                values: { count: lastVisibilityChange.ids.length },
                                default: '{count, plural, one {Call restored.} other {# calls restored.}}'
                            })}
                    </span>
                    <button type="button" class="btn btn-secondary min-h-11 px-3.5 text-sm focus-visible:ring-2 focus-visible:ring-focus" disabled={changingVisibility} onclick={() => void undoLastVisibilityChange()} data-audio-visibility-undo>{$_('audio.history.undo')}</button>
                </div>
            {/if}
            {#if visibilityError}<p class="text-sm text-status-fail" role="alert">{visibilityError}</p>{/if}
        {/if}

        {#if reading === 'failed'}
            <!-- The app's own sentence and next step; what the server said is a detail behind a disclosure. -->
            <div role="alert" class="space-y-2 border-y border-status-fail-line px-4 py-4 text-sm" data-audio-read-failed>
                <p class="font-semibold text-status-fail">{$_('audio.history.read_failed', { default: 'Audio history could not be read from YA-WAMF, so nothing on this page is a measurement.' })}</p>
                <p class="text-ink">{$_('audio.history.read_failed_next', { default: 'Try again. If it keeps failing, open Health to see whether the backend reports a fault.' })}</p>
                <div class="flex flex-wrap items-center gap-x-4">
                    <button type="button" class="btn btn-secondary min-h-11 px-4 focus-visible:ring-2 focus-visible:ring-focus" onclick={() => void loadAudioHistory()}>{$_('common.retry')}</button>
                    {#if error}{@render technicalDetails(error)}{/if}
                </div>
            </div>
        {:else if reading === 'loading'}
            <div class="space-y-1 border-y border-line-soft py-2" aria-label={$_('common.loading', { default: 'Loading' })}>
                {#each Array.from({ length: 8 }) as _}
                    <div class="h-16 animate-pulse bg-surface-raised"></div>
                {/each}
            </div>
        {:else}
            {#if reading === 'stale'}
                <div role="status" class="flex flex-col gap-2 border-y border-line px-4 py-3 text-sm sm:flex-row sm:items-center sm:justify-between" data-audio-stale>
                    <p class="font-semibold text-strong">
                        {$_('audio.history.stale', { values: { at: readAt ? formatDateTime(readAt) : '' }, default: 'The latest refresh failed, so this is the reading from {at}.' })}
                    </p>
                    <button type="button" class="btn btn-secondary min-h-11 shrink-0 px-4 focus-visible:ring-2 focus-visible:ring-focus" onclick={() => void loadAudioHistory()}>{$_('common.retry')}</button>
                </div>
            {/if}
        {#if detections.length === 0}
            <div class="border-y border-dashed border-line px-4 py-12 text-center text-sm font-semibold text-muted">
                {#if showHidden}
                    {$_('audio.history.empty_hidden', { default: 'No hidden calls match these filters.' })}
                {:else if applied.window === 'today' && nothingNarrows && sharedFrom}
                    <span data-audio-history-empty-today>{$_('audio.history.empty_today_shared', { values: { time: formatTime(sharedFrom) }, default: 'No calls heard since {time}, when the shared history starts. Select Refresh to check for new calls.' })}</span>
                {:else if applied.window === 'today' && nothingNarrows}
                    <span data-audio-history-empty-today>{$_('audio.history.empty_today', { default: 'No calls heard yet today. Select Refresh to check for new calls.' })}</span>
                {:else}
                    {$_('audio.history.empty', { default: 'No calls match these filters.' })}
                {/if}
            </div>
        {:else}
            <!-- A table only where its own box has room at the reader's text size (rem, so larger text
                 stacks the rows); in the side-column layout the box is narrower than the window. -->
            <div class="@container">
            <table class="block w-full text-sm @2xl:table" data-audio-history-table>
                <thead class="hidden border-y border-line-soft @2xl:table-header-group">
                    <tr class="text-left text-xs font-semibold text-muted">
                        {#if authStore.canModify && selectionMode}
                            <th scope="col" class="w-11 py-3 pr-2">
                                <label class="inline-flex min-h-11 min-w-11 cursor-pointer items-center justify-center">
                                    <input
                                        type="checkbox"
                                        class="h-4 w-4 rounded border-line accent-accent focus-visible:ring-2 focus-visible:ring-focus"
                                        checked={allPageSelected}
                                        onchange={toggleSelectAllPage}
                                        aria-label={allPageSelected ? $_('audio.history.deselect_page', { default: 'Deselect page' }) : $_('audio.history.select_page', { default: 'Select page' })}
                                    />
                                </label>
                            </th>
                        {/if}
                        <th scope="col" class="py-3 pr-4">{$_('audio.table.sound', { default: 'Sound' })}</th>
                        <th scope="col" class="py-3 pr-4">{$_('audio.table.species', { default: 'Species' })}</th>
                        <th scope="col" class="py-3 pr-4">{$_('audio.table.time', { default: 'Time' })}</th>
                        <th scope="col" class="py-3 pr-4">{$_('audio.table.source', { default: 'Source' })}</th>
                        <th scope="col" class="py-3 text-right">{$_('audio.table.confidence', { default: 'Confidence' })}</th>
                        {#if authStore.canModify}<th scope="col" class="py-3 pl-2 text-right"><span class="sr-only">{showHidden ? $_('audio.history.unhide', { default: 'Restore to YA-WAMF' }) : $_('audio.history.hide')}</span></th>{/if}
                    </tr>
                </thead>
                <tbody class="block divide-y divide-line-soft border-y border-line-soft @2xl:table-row-group @2xl:border-0">
                    {#each detections as detection (detection.id)}
                        {@const spec = detection.birdnet_id && failedSpectrograms[detection.birdnet_id] ? null : spectrogramUrl(detection.birdnet_id)}
                        {@const specAlt = $_('audio.table.spectrogram_alt', { values: { species: detection.species }, default: 'Spectrogram of the {species} call' })}
                        {@const link = birdnetDetectionUrl(detection.birdnet_id)}
                        {@const isSelected = selectedIds.includes(detection.id)}
                        {@const rowActionLabel = showHidden ? $_('audio.history.unhide', { default: 'Restore to YA-WAMF' }) : $_('audio.history.hide')}
                        <tr
                            class="grid grid-cols-[5rem_minmax(0,1fr)_auto] {authStore.canModify && selectionMode ? 'audio-row-selecting cursor-pointer' : ''} gap-x-3 py-3 text-ink @2xl:table-row @2xl:py-0 {isSelected ? 'bg-accent-soft/50' : ''}"
                            onclick={(event) => handleRowClick(event, detection.id)}
                        >
                            {#if authStore.canModify && selectionMode}
                                <td class="col-start-1 row-span-3 flex items-center justify-center @2xl:table-cell @2xl:w-11 @2xl:py-3 @2xl:pr-2">
                                    <label class="inline-flex min-h-11 min-w-11 cursor-pointer items-center justify-center">
                                        <input
                                            type="checkbox"
                                            class="h-4 w-4 rounded border-line accent-accent focus-visible:ring-2 focus-visible:ring-focus"
                                            checked={isSelected}
                                            onchange={() => toggleRowSelected(detection.id)}
                                            aria-label={$_('audio.history.select_call', { values: { species: detection.species, time: formatDateTime(detection.timestamp) }, default: 'Select {species} call at {time}' })}
                                            data-audio-select-row={detection.id}
                                        />
                                    </label>
                                </td>
                            {/if}
                            <td class="{authStore.canModify && selectionMode ? 'col-start-2' : 'col-start-1'} row-span-3 flex items-center @2xl:table-cell @2xl:w-28 @2xl:py-3 @2xl:pr-4">
                                {#if spec}
                                    {#if link}
                                        <a href={link} target="_blank" rel="noopener noreferrer" class="block min-h-11 rounded-md focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-focus" title={$_('audio.table.open_birdnet', { default: 'Open in BirdNET-Go' })}>
                                            <img data-audio-spectrogram src={spec} alt={specAlt} loading="lazy" onerror={() => markSpectrogramFailed(detection.birdnet_id)} class="h-12 w-20 rounded-md object-cover ring-1 ring-line @2xl:w-24" />
                                        </a>
                                    {:else}
                                        <img data-audio-spectrogram src={spec} alt={specAlt} loading="lazy" onerror={() => markSpectrogramFailed(detection.birdnet_id)} class="h-12 w-20 rounded-md object-cover ring-1 ring-line @2xl:w-24" />
                                    {/if}
                                {:else}
                                    <div class="flex h-12 w-20 items-center justify-center rounded-md bg-surface-raised text-muted @2xl:w-24">
                                        <svg aria-hidden="true" class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path stroke-linecap="round" stroke-linejoin="round" d="M4 12v2m4-5v8m4-13v16m4-13v10m4-7v4" /></svg>
                                    </div>
                                {/if}
                            </td>
                            <td class="{authStore.canModify && selectionMode ? 'col-start-3' : 'col-start-2'} row-start-1 min-w-0 self-end font-bold text-strong @2xl:table-cell @2xl:py-3 @2xl:pr-4">
                                <span class="flex min-w-0 items-center gap-1">
                                    <span class="min-w-0 wrap-anywhere">{detection.species}</span>
                                    {#if detection.matched_visual_event_id}
                                        <a
                                            data-audio-visual-match-link
                                            href={toAppPath(`/events?event=${encodeURIComponent(detection.matched_visual_event_id)}`)}
                                            class="inline-flex min-h-11 min-w-11 shrink-0 items-center justify-center rounded-full text-accent-ink transition hover:bg-accent-soft hover:text-accent-ink focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-focus"
                                            aria-label={$_('audio.table.open_visual_match')}
                                            title={$_('audio.table.open_visual_match')}
                                        >
                                            <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
                                                <path stroke-linecap="round" stroke-linejoin="round" d="M4 7.5A2.5 2.5 0 0 1 6.5 5h8A2.5 2.5 0 0 1 17 7.5v9a2.5 2.5 0 0 1-2.5 2.5h-8A2.5 2.5 0 0 1 4 16.5v-9Z" />
                                                <path stroke-linecap="round" stroke-linejoin="round" d="m17 10 3-2v8l-3-2M8 12l1.5 1.5L13 10" />
                                            </svg>
                                        </a>
                                    {/if}
                                </span>
                            </td>
                            <td class="{authStore.canModify && selectionMode ? 'col-start-3' : 'col-start-2'} row-start-2 min-w-0 self-start text-xs text-muted @2xl:table-cell @2xl:whitespace-nowrap @2xl:py-3 @2xl:pr-4">
                                <span class="@2xl:font-bold">{formatDate(detection.timestamp)}</span>
                                <span class="before:mx-1 before:content-['·'] @2xl:block @2xl:before:content-none">{formatTime(detection.timestamp, { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>
                            </td>
                            <!-- On a phone the source sits under the time in the same column, so a long microphone name wraps there instead of squeezing the time out. -->
                            <td class="{authStore.canModify && selectionMode ? 'col-start-3' : 'col-start-2'} row-start-3 min-w-0 self-start wrap-break-word text-xs text-muted @2xl:table-cell @2xl:max-w-48 @2xl:py-3 @2xl:pr-4">
                                {detection.source_name || detection.sensor_id || $_('audio.table.unknown_source', { default: 'Unknown source' })}
                            </td>
                            <td class="{authStore.canModify && selectionMode ? 'col-start-4' : 'col-start-3'} row-start-1 self-end whitespace-nowrap text-right @2xl:table-cell @2xl:py-3">
                                <span class="font-bold tabular-nums {SCORE_TEXT[scoreBand(detection.confidence)]}">{confidencePercent(detection.confidence)}</span>
                            </td>
                            {#if authStore.canModify}
                                <td class="{selectionMode ? 'col-start-4' : 'col-start-3'} row-start-2 row-span-2 self-center justify-self-end @2xl:table-cell @2xl:w-12 @2xl:py-3 @2xl:pl-2 @2xl:text-right">
                                    <button
                                        type="button"
                                        class="btn btn-ghost min-h-11 min-w-11 p-0 text-muted hover:text-strong focus-visible:ring-2 focus-visible:ring-focus"
                                        disabled={changingVisibility || loading}
                                        onclick={() => void changeVisibility(detection.id, !showHidden)}
                                        aria-label={rowActionLabel}
                                        title={rowActionLabel}
                                        data-audio-visibility-toggle
                                    >
                                        {#if showHidden}
                                            <svg aria-hidden="true" class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9">
                                                <path stroke-linecap="round" stroke-linejoin="round" d="M2.25 12s3.75-7 9.75-7 9.75 7 9.75 7-3.75 7-9.75 7-9.75-7-9.75-7Z" />
                                                <circle cx="12" cy="12" r="3" />
                                            </svg>
                                        {:else}
                                            <svg aria-hidden="true" class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9">
                                                <path stroke-linecap="round" stroke-linejoin="round" d="M3 3l18 18M10.58 10.58a2 2 0 1 0 2.83 2.83M9.88 5.09A10.94 10.94 0 0 1 12 4.9c5.05 0 9.27 3.11 10.5 7.1a10.7 10.7 0 0 1-4.18 5.26M6.61 6.61A10.73 10.73 0 0 0 1.5 12c1.23 3.99 5.45 7.1 10.5 7.1 1.61 0 3.14-.33 4.5-.92" />
                                            </svg>
                                        {/if}
                                    </button>
                                </td>
                            {/if}
                        </tr>
                    {/each}
                </tbody>
            </table>
            </div>
            <div class="flex flex-col gap-3 border-b border-line-soft py-4 text-sm font-semibold text-muted sm:flex-row sm:items-center sm:justify-between">
                <span class="tabular-nums">{$_('audio.history.showing', { values: { from: offset + 1, to: Math.min(offset + (history?.items.length ?? 0), history?.total ?? 0), total: history?.total ?? 0 }, default: `Showing ${offset + 1}-${Math.min(offset + (history?.items.length ?? 0), history?.total ?? 0)} of ${history?.total ?? 0}` })}</span>
                <div class="grid grid-cols-2 gap-2 sm:flex">
                    <button type="button" class="btn btn-secondary min-h-11 px-4 text-sm focus-visible:ring-2 focus-visible:ring-focus" onclick={previousPage} disabled={!canPrevious}>{$_('common.previous', { default: 'Previous' })}</button>
                    <button type="button" class="btn btn-secondary min-h-11 px-4 text-sm focus-visible:ring-2 focus-visible:ring-focus" onclick={nextPage} disabled={!canNext}>{$_('common.next', { default: 'Next' })}</button>
                </div>
            </div>
        {/if}
        {/if}
    </section>
    </div>

    <aside class="min-w-0 space-y-8 xl:col-span-4 xl:col-start-9 xl:row-start-2 2xl:col-span-3 2xl:col-start-10" aria-label={$_('audio.side_label', { default: 'Most heard species and sources' })} data-audio-history-side>
            <section use:whenNearViewport={() => (topSpeciesNear = true)}>
                <h2 class="text-base font-bold text-strong">{$_('audio.top_species', { default: 'Top heard species' })}</h2>
                {#if !measured}
                    <p class="mt-4 border-y border-line-soft py-6 text-sm text-muted">
                        {reading === 'failed' ? $_('audio.chart.unavailable', { default: 'Not available while the history cannot be read.' }) : $_('common.loading', { default: 'Loading' })}
                    </p>
                {:else if hasSpecies}
                    <ol class="mt-4 grid border-y border-line-soft sm:grid-cols-2 xl:grid-cols-1">
                        {#each (summary?.top_species ?? []).slice(0, 6) as item, index}
                            {@const thumb = cachedSpeciesThumb(item.species)}
                            <li class="min-w-0 border-b border-line-soft sm:odd:pr-4 sm:even:border-l sm:even:pl-4 xl:odd:pr-0 xl:even:border-l-0 xl:even:pl-0">
                                <button
                                    type="button"
                                    data-audio-top-species-button
                                    onclick={() => selectedSpecies = item.species}
                                    class="group flex min-h-11 w-full flex-wrap items-center gap-x-3 gap-y-1 py-3 text-left transition-colors hover:bg-surface-raised focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus"
                                >
                                    <span class="w-6 flex-none text-center text-xs font-bold tabular-nums text-muted">{index + 1}</span>
                                    <span class="h-11 w-11 flex-none overflow-hidden rounded-full bg-surface-raised">
                                        {#if thumb}
                                            <img src={thumb} alt="" loading="lazy" class="h-full w-full object-cover" />
                                        {:else}
                                            <span class="flex h-full w-full items-center justify-center text-muted">
                                                <svg aria-hidden="true" class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path stroke-linecap="round" stroke-linejoin="round" d="M12 3a4 4 0 00-4 4v4a4 4 0 008 0V7a4 4 0 00-4-4Z M6 11a6 6 0 0012 0 M12 17v4 M9 21h6" /></svg>
                                            </span>
                                        {/if}
                                    </span>
                                    <!-- Wide enough to hold a name: when the row is too narrow for that, the count drops to a line of its own. -->
                                    <span class="min-w-0 flex-1 basis-32">
                                        <span class="block wrap-break-word font-bold text-strong transition-colors group-hover:text-accent-ink">{item.species}</span>
                                        <span class="mt-0.5 block wrap-break-word text-xs text-muted">{$_('audio.card.last_heard', { default: 'Last heard' })} {item.last_heard ? formatDateTime(item.last_heard) : '—'}</span>
                                    </span>
                                    <span class="flex-none text-right">
                                        <span class="block font-bold tabular-nums text-accent-ink">{item.count.toLocaleString()}</span>
                                        <span class="block text-xs font-semibold tabular-nums text-muted">{$_('audio.card.avg', { default: 'avg' })} {confidencePercent(item.avg_confidence)}</span>
                                    </span>
                                    <svg aria-hidden="true" class="h-4 w-4 flex-none text-muted transition-transform group-hover:translate-x-0.5" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8"><path stroke-linecap="round" stroke-linejoin="round" d="m8 5 5 5-5 5" /></svg>
                                </button>
                            </li>
                        {/each}
                    </ol>
                {:else}
                    <p class="mt-4 border-y border-line-soft py-6 text-sm text-muted">{$_('audio.chart.empty', { default: 'No calls heard in this window.' })}</p>
                {/if}
            </section>

            <section>
                <h2 class="text-base font-bold text-strong">{$_('audio.sources.title', { default: 'Sources' })}</h2>
                <div class="mt-4 divide-y divide-line-soft border-y border-line-soft">
                    {#if !measured}
                        <p class="py-6 text-sm text-muted">
                            {reading === 'failed' ? $_('audio.chart.unavailable', { default: 'Not available while the history cannot be read.' }) : $_('common.loading', { default: 'Loading' })}
                        </p>
                    {:else}
                    {#each listedSources as item}
                        <div class="flex items-center justify-between gap-3 py-3">
                            <div class="min-w-0">
                                <p class="wrap-break-word text-sm font-bold text-strong">{item.source_name}</p>
                                {#if sharedSourceNames.has(sourceNameKey(item.source_name))}
                                    <p class="mt-0.5 break-all text-xs text-muted" data-audio-source-id>
                                        {#if item.source_id && item.source_node}
                                            {$_('audio.sources.source_id_on_node', { values: { id: item.source_id, node: item.source_node }, default: 'BirdNET-Go id {id} on {node}' })}
                                        {:else if item.source_id}
                                            {$_('audio.sources.source_id', { values: { id: item.source_id }, default: 'BirdNET-Go id {id}' })}
                                        {:else if item.source_node}
                                            {$_('audio.sources.no_source_id_on_node', { values: { node: item.source_node }, default: 'Calls without a usable BirdNET-Go id on {node}' })}
                                        {:else}
                                            {$_('audio.sources.no_source_id', { default: 'Calls without a usable BirdNET-Go id' })}
                                        {/if}
                                    </p>
                                {/if}
                                <p class="mt-0.5 wrap-break-word text-xs text-muted">{$_('audio.card.last_heard', { default: 'Last heard' })} {formatDateTime(item.last_heard)}</p>
                            </div>
                            <span class="flex-none text-sm font-bold tabular-nums text-ink">{item.count.toLocaleString()}</span>
                        </div>
                    {:else}
                        <p class="py-6 text-sm text-muted">{$_('audio.sources.empty', { default: 'No sources yet.' })}</p>
                    {/each}
                    {/if}
                </div>
            </section>
    </aside>
    </div>

    <!-- The Leaderboard's analytics, in its order and frames: the window said once for the section,
         each chart's count of calls heard in its caption, and each chart's data as a table. Charts take
         the page's full width; the grid and the species share a row from 1280 px. -->
    <section class="min-w-0 space-y-8 border-t border-line pt-8" data-audio-history-analytics aria-labelledby="audio-analytics-title">
        <header class="flex flex-wrap items-end justify-between gap-3">
            <div>
                <h2 id="audio-analytics-title" class="text-xl font-bold text-strong">{$_('leaderboard.analytics_section', { default: 'Analytics' })}</h2>
                <p class="text-sm text-muted" data-audio-analytics-window>{windowLabel(applied.window)}{windowRange() ? ` · ${windowRange()}` : ''}</p>
            </div>
        </header>

        <ChartFigure
            title={$_('audio.chart.daily_title', { default: 'Calls heard over time' })}
            description={measured ? callsHeard(summary?.total ?? 0) : undefined}
            table={measured && hasDaily ? { columns: [$_('audio.chart.col_day', { default: 'Day' }), $_('audio.chart.col_calls', { default: 'Calls' })], rows: dailyPoints.map((point) => [point.label, point.count.toLocaleString()]) } : { columns: [], rows: [] }}
            class="border-y border-line py-6"
        >
            {#if !measured}
                {@render chartPending()}
            {:else if hasDaily}
                {#key `${applied.window}-${isDark}-${reduceMotion}`}
                    <div class="relative mt-6 chart-h w-full"><canvas use:chartjs={dailyChartConfig()} aria-label={$_('audio.chart.daily_title', { default: 'Calls heard over time' })}></canvas></div>
                {/key}
            {:else}
                <div class="flex h-60 items-center justify-center text-sm text-muted">{$_('audio.chart.empty', { default: 'No calls heard in this window.' })}</div>
            {/if}
        </ChartFigure>

        <div class="grid min-w-0 grid-cols-1 gap-8 xl:grid-cols-5">
            <ChartFigure
                title={$_('audio.chart.heatmap_title', { default: 'Calls heard by hour and weekday' })}
                description={measured && shownHeatmap ? callsHeard(shownHeatmap.total_count) : undefined}
                table={measured && hasShownHeatmap ? heatmapTable : { columns: [], rows: [] }}
                class="min-w-0 xl:col-span-3"
            >
                {#if measured}
                    <HeatmapSpeciesChips
                        options={heatmapSpeciesOptions}
                        selected={heatmapSpecies}
                        label={$_('audio.heatmap.species_picker', { default: 'Show calls heard from' })}
                        onselect={(key) => (heatmapChoice = key)}
                        data-audio-heatmap-species
                    />
                {/if}
                {#if !measured}
                    {@render chartPending()}
                {:else if heatmapSpecies}
                    <div class="min-h-60" aria-busy={speciesHeatmapLoading} data-audio-species-heatmap>
                        {#if speciesHeatmapError}
                            <div class="flex min-h-60 flex-col items-center justify-center gap-2 px-4 text-center text-sm" role="status" data-audio-species-heatmap-failed>
                                <p class="max-w-prose text-ink">{$_('audio.heatmap.species_failed', { values: { species: chosenSpeciesLabel }, default: '{species} calls by hour and weekday could not be read. Everything else on the page was read.' })}</p>
                                <div class="flex flex-wrap items-center justify-center gap-x-4">
                                    <button type="button" class="btn btn-secondary min-h-11 px-4 focus-visible:ring-2 focus-visible:ring-focus" onclick={() => (speciesHeatmapAttempt += 1)}>{$_('common.retry')}</button>
                                    {@render technicalDetails(speciesHeatmapError)}
                                </div>
                            </div>
                        {:else if hasShownHeatmap && shownHeatmap}
                            <div class="mt-4 transition-opacity motion-reduce:transition-none {speciesHeatmapLoading ? 'opacity-50' : ''}" data-audio-heatmap>
                                <ActivityHeatmap cells={shownHeatmap.cells} maxCellCount={shownHeatmap.max_cell_count} dark={isDark} dayLabel={weekdayLabel} unit="calls" subject={heatmapSubject} />
                            </div>
                        {:else if shownHeatmap}
                            <div class="flex h-60 items-center justify-center px-4 text-center text-sm text-muted" data-audio-species-heatmap-empty>{$_('audio.heatmap.species_empty', { values: { species: heatmapSubject ?? '' }, default: 'No {species} calls heard in this window.' })}</div>
                        {:else}
                            <div class="mt-3 h-60 animate-pulse bg-surface-raised motion-reduce:animate-none" aria-hidden="true"></div>
                        {/if}
                    </div>
                {:else if heatmapError}
                    <!-- Only the grid failed: said in its own frame, with the list and the other figures left standing. -->
                    <div class="flex min-h-60 flex-col items-center justify-center gap-2 px-4 text-center text-sm" role="status" data-audio-heatmap-failed>
                        <p class="max-w-prose text-ink">{$_('audio.heatmap.read_failed', { default: 'Calls heard by hour and weekday could not be read, so this grid and the busiest hour are not shown. Everything else on the page was read.' })}</p>
                        <div class="flex flex-wrap items-center justify-center gap-x-4">
                            <button type="button" class="btn btn-secondary min-h-11 px-4 focus-visible:ring-2 focus-visible:ring-focus" onclick={() => void loadAudioHistory()}>{$_('common.retry')}</button>
                            {@render technicalDetails(heatmapError)}
                        </div>
                    </div>
                {:else if hasHeatmap && heatmap}
                    <div class="mt-4" data-audio-heatmap>
                        <ActivityHeatmap cells={heatmap.cells} maxCellCount={heatmap.max_cell_count} dark={isDark} dayLabel={weekdayLabel} unit="calls" />
                    </div>
                {:else}
                    <div class="flex h-60 items-center justify-center text-sm text-muted" data-audio-heatmap-empty>{$_('audio.chart.empty', { default: 'No calls heard in this window.' })}</div>
                {/if}
            </ChartFigure>
            <ChartFigure
                title={$_('audio.chart.species_title', { default: 'Species composition' })}
                description={measured ? callsHeard(summary?.total ?? 0) : undefined}
                table={measured && hasSpecies ? { columns: [$_('audio.chart.col_species', { default: 'Species' }), $_('audio.chart.col_calls', { default: 'Calls' })], rows: speciesMix.map((item) => [item.species, item.count.toLocaleString()]) } : { columns: [], rows: [] }}
                class="min-w-0 xl:col-span-2"
            >
                {#if !measured}
                    {@render chartPending()}
                {:else if hasSpecies}
                    {#key `${applied.window}-${isDark}-${reduceMotion}`}
                        <div class="relative mt-3 chart-h w-full"><canvas use:chartjs={speciesDonutConfig()} bind:this={speciesChartEl} aria-label={$_('audio.chart.species_title', { default: 'Species composition' })}></canvas></div>
                        <div class="mt-2 flex flex-wrap justify-center gap-x-1" role="group" aria-label={$_('audio.chart.species_title', { default: 'Species composition' })}>
                            {#each speciesMix as item, index}
                                <button type="button" class="btn btn-ghost min-h-11 gap-1.5 px-2 text-xs focus-visible:ring-2 focus-visible:ring-focus {hiddenChartSpecies.includes(index) ? 'opacity-45 line-through' : ''}"
                                    aria-pressed={!hiddenChartSpecies.includes(index)} aria-label="{hiddenChartSpecies.includes(index) ? $_('common.show') : $_('common.hide')} {item.species} {item.count.toLocaleString()}" onclick={() => toggleSpeciesSlice(index)}>
                                    <span class="h-2.5 w-2.5 rounded-xs" style="background-color: {item.other ? otherSpeciesColor : audioSpeciesColor(index)}"></span>{item.species}
                                    <!-- The slice's count beside its name, "Other species" included, so the ring is readable without hovering it. -->
                                    <span class="tabular-nums text-muted" data-audio-mix-count>{item.count.toLocaleString()}</span>
                                </button>
                            {/each}
                        </div>
                    {/key}
                {:else}
                    <div class="flex h-60 items-center justify-center text-sm text-muted">{$_('audio.chart.empty', { default: 'No calls heard in this window.' })}</div>
                {/if}
            </ChartFigure>
        </div>
    </section>
</div>

{#if selectedSpecies}
    <LazyModal loader={loadSpeciesDetailModal} onclose={() => (selectedSpecies = null)}>
        {#snippet children(SpeciesDetailModal)}
            {#if selectedSpecies}<SpeciesDetailModal speciesName={selectedSpecies} onclose={() => (selectedSpecies = null)} />{/if}
        {/snippet}
    </LazyModal>
{/if}
{/if}

<style>
    .audio-row-selecting {
        grid-template-columns: 2.75rem 5rem minmax(0, 1fr) auto;
    }

    /* From 1280px the log spans the right-hand column's two rows: the window's figures, then the
       most heard species and sources. The first row is only as tall as the figures, so the log's
       height never opens a gap under them (the Dashboard's desk does the same). */
    @media (min-width: 1280px) {
        [data-audio-history-layout] {
            grid-template-rows: auto 1fr;
        }
    }
</style>
