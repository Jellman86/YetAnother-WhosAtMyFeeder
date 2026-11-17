<script lang="ts">
    import { onMount, untrack } from 'svelte';
    import { _, locale } from 'svelte-i18n';
    import {
        fetchAudioHistory,
        setAudioHidden,
        fetchAudioSummary,
        fetchSpeciesInfo,
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
    import { withAuthParams } from '../api/core';
    import { appApiPath, toAppPath } from '../app/url-base';
    import { formatCalendarDay, formatDate, formatDateTime, formatHour, formatTime } from '../utils/datetime';
    import { getErrorMessage, isTransientRequestError } from '../utils/error-handling';
    import { logger } from '../utils/logger';
    import FilterSheet from '../components/ui/FilterSheet.svelte';
    import ChartFigure from '../components/ui/ChartFigure.svelte';
    import LazyModal from '../components/LazyModal.svelte';
    import { loadSpeciesDetailModal } from '../components/lazy-dialogs';
    import { doughnutInsightPlugin } from '../actions/chartjs-doughnut';
    import { audioSpeciesMix } from './audio-species-mix';
    import { SCORE_TEXT, scoreBand } from '../utils/score-tone';
    import { audioReading } from './audio-history-state';
    import { dailySeries, hourlySeries } from './audio-chart-series';
    import { whenNearViewport } from '../actions/near-viewport';

    const PAGE_SIZE = 25;

    let changingVisibility = $state(false);
    let lastHiddenId = $state<number | null>(null);
    let visibilityError = $state<string | null>(null);

    let days = $state(DEFAULT_AUDIO_HISTORY_FILTERS.days);
    let speciesFilter = $state(DEFAULT_AUDIO_HISTORY_FILTERS.species);
    let sourceFilter = $state(DEFAULT_AUDIO_HISTORY_FILTERS.source);
    let minConfidence = $state(DEFAULT_AUDIO_HISTORY_FILTERS.minConfidence);
    // The list, charts and paging follow what was applied, never the half-edited form.
    let applied = $state<AudioHistoryFilters>({ ...DEFAULT_AUDIO_HISTORY_FILTERS });
    const filtersChanged = $derived(
        audioHistoryFiltersDiffer({ days, species: speciesFilter, source: sourceFilter, minConfidence }, applied)
    );
    let filterSheetOpen = $state(false);
    // What the list shows, in words, beside the phone's Filters button.
    const appliedSummary = $derived(
        [
            windowLabel(applied.days),
            applied.species.trim(),
            applied.source.trim(),
            applied.minConfidence > 0 ? `≥ ${confidencePercent(applied.minConfidence)}` : ''
        ].filter(Boolean).join(' · ')
    );
    // Spectrograms BirdNET-Go could not render, keyed by its detection id.
    let failedSpectrograms = $state<Record<number, true>>({});
    let history = $state<AudioHistoryResponse | null>(null);
    let summary = $state<AudioSummaryResponse | null>(null);
    let loading = $state(true);
    // The read's own words, kept for Technical details; the page states the failure in its own sentence.
    let error = $state<string | null>(null);
    let stale = $state(false);
    let readAt = $state<number | null>(null);
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
    let canPrevious = $derived(offset > 0);
    let canNext = $derived(Boolean(history && offset + history.limit < history.total));

    let isDark = $derived(themeStore.isDark);
    // slate-500 on a light page and slate-400 on a dark one: slate-400 on white is 2.56:1, too faint for axis labels.
    let chartTickColor = $derived(isDark ? '#94a3b8' : '#64748b');
    const reading = $derived(audioReading({ loading, error, stale, total: summary?.total ?? null }));
    /** A reading is on screen: numbers can be shown, and zero means none were heard. */
    const measured = $derived(reading === 'ready' || reading === 'empty' || reading === 'stale');
    let hasDaily = $derived((summary?.daily_counts?.length ?? 0) > 0);
    let hasHourly = $derived((summary?.hourly_counts?.length ?? 0) > 0);
    let hasSpecies = $derived((summary?.top_species?.length ?? 0) > 0);
    let peakHour = $derived.by(() => {
        const counts = summary?.hourly_counts ?? [];
        if (!counts.length) return null;
        return counts.reduce((best, item) => (item.count > best.count ? item : best), counts[0]);
    });

    function requestParams(includePaging = true) {
        return {
            days: applied.days,
            species: applied.species || undefined,
            source: applied.source || undefined,
            min_confidence: applied.minConfidence,
            limit: includePaging ? PAGE_SIZE : undefined,
            offset: includePaging ? offset : undefined
        };
    }

    const audioHistoryLoader = createAudioHistoryLoader({
        requestKey: () => JSON.stringify(requestParams(true)),
        fetchHistory: () => fetchAudioHistory(requestParams(true)),
        fetchSummary: () => fetchAudioSummary(requestParams(false)),
        begin: () => { loading = true; error = null; stale = false; },
        apply: (nextHistory, nextSummary) => {
            history = nextHistory;
            summary = nextSummary;
            readAt = Date.now();
            hiddenChartState = { theme: '', indices: [] };
        },
        clear: () => {
            history = null;
            summary = null;
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

    async function loadAudioHistory() {
        await audioHistoryLoader.load();
    }

    let handledPublicHistoryVersion = detectionsStore.publicHistoryVersion;
    $effect(() => {
        const version = detectionsStore.publicHistoryVersion;
        if (version <= handledPublicHistoryVersion || !authStore.isGuest) return;
        handledPublicHistoryVersion = version;
        untrack(() => { void audioHistoryLoader.load(true); });
    });

    async function changeVisibility(id: number, hidden: boolean): Promise<void> {
        if (!authStore.canModify || changingVisibility) return;
        changingVisibility = true;
        visibilityError = null;
        try {
            await setAudioHidden(id, hidden);
            lastHiddenId = hidden ? id : null;
            if (hidden && detections.length === 1 && offset > 0) offset = Math.max(0, offset - PAGE_SIZE);
            await loadAudioHistory();
        } catch (e) {
            visibilityError = getErrorMessage(e);
        } finally {
            changingVisibility = false;
        }
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

    function windowLabel(windowDays: number): string {
        if (windowDays === 1) return $_('audio.filter.24h', { default: '24 hours' });
        if (windowDays === 7) return $_('audio.filter.7d', { default: '7 days' });
        if (windowDays === 30) return $_('audio.filter.30d', { default: '30 days' });
        if (windowDays === 90) return $_('audio.filter.90d', { default: '90 days' });
        return $_('audio.filter.1y', { default: '1 year' });
    }

    function applyFilters(event?: SubmitEvent) {
        event?.preventDefault();
        applied = settledAudioHistoryFilters({ days, species: speciesFilter, source: sourceFilter, minConfidence });
        offset = 0;
        void loadAudioHistory();
    }

    function clearFilters() {
        days = DEFAULT_AUDIO_HISTORY_FILTERS.days;
        speciesFilter = DEFAULT_AUDIO_HISTORY_FILTERS.species;
        sourceFilter = DEFAULT_AUDIO_HISTORY_FILTERS.source;
        minConfidence = DEFAULT_AUDIO_HISTORY_FILTERS.minConfidence;
        applied = { ...DEFAULT_AUDIO_HISTORY_FILTERS };
        offset = 0;
        void loadAudioHistory();
    }

    function previousPage() {
        if (!canPrevious) return;
        offset = Math.max(0, offset - PAGE_SIZE);
        void loadAudioHistory();
    }

    function nextPage() {
        if (!canNext) return;
        offset += PAGE_SIZE;
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

    // Calls over time and by hour take the colour theme's primary, as the Leaderboard trend does;
    // species take the shared colour-blind-safe species palette, so a species reads the same here.
    let audioPrimary = $derived(themeStore.colorTheme === 'bluetit' ? '#2563eb' : '#0d9488');
    let audioPrimaryFill = $derived(themeStore.colorTheme === 'bluetit' ? 'rgba(37,99,235,0.18)' : 'rgba(13,148,136,0.18)');
    function audioSpeciesColor(index: number): string {
        return speciesSeriesColor(index, isDark);
    }

    // One series per chart, drawn by the canvas and listed by its table, so the two always agree.
    const dailyPoints = $derived(dailySeries(summary?.daily_counts ?? [], formatCalendarDay));
    const hourlyPoints = $derived(hourlySeries(summary?.hourly_counts ?? [], formatHour));

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

    let hourlyChartConfig = $derived((): CanvasChartConfig => {
        const counts = hourlyPoints.map((point) => point.count);
        const labels = hourlyPoints.map((point) => String(point.hour).padStart(2, '0'));
        return {
            type: 'bar',
            data: {
                labels,
                datasets: [{
                    label: $_('audio.chart.heard', { default: 'Heard' }),
                    data: counts,
                    backgroundColor: audioPrimary,
                    borderRadius: 4,
                    barPercentage: 0.8,
                    categoryPercentage: 0.9,
                    maxBarThickness: 48,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: reduceMotion ? false : { duration: 200 },
                plugins: {
                    legend: { display: false },
                    tooltip: { callbacks: { title: (items) => `${labels[items[0]?.dataIndex] ?? '00'}:00` } },
                },
                scales: {
                    x: { ticks: { color: chartTickColor, autoSkip: false, minRotation: 0, maxRotation: 0, callback: (value) => Number(value) % 3 === 0 ? `${labels[Number(value)]}:00` : '' }, grid: { display: false } },
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
            {$_('audio.not_shared_body', { default: 'The owner of this instance has turned off audio for visitors.' })}
        </p>
    </section>
{:else}

{#snippet statValue(value: string)}
    {#if measured}
        <dd class="mt-1 text-2xl font-bold tabular-nums text-strong">{value}</dd>
    {:else if reading === 'failed'}
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
            <label class="space-y-1.5">
                <span class="text-xs font-semibold text-muted">{$_('audio.filter.window', { default: 'Window' })}</span>
                <select bind:value={days} class="select-base min-h-11 font-semibold focus-visible:ring-2 focus-visible:ring-focus">
                    <option value={1}>{$_('audio.filter.24h', { default: '24 hours' })}</option>
                    <option value={7}>{$_('audio.filter.7d', { default: '7 days' })}</option>
                    <option value={30}>{$_('audio.filter.30d', { default: '30 days' })}</option>
                    <option value={90}>{$_('audio.filter.90d', { default: '90 days' })}</option>
                    <option value={365}>{$_('audio.filter.1y', { default: '1 year' })}</option>
                </select>
            </label>
            <label class="space-y-1.5">
                <span class="text-xs font-semibold text-muted">{$_('audio.filter.species', { default: 'Species' })}</span>
                <input bind:value={speciesFilter} class="input-base min-h-11 focus-visible:ring-2 focus-visible:ring-focus" placeholder={$_('audio.filter.species_placeholder', { default: 'Any species' })} />
            </label>
            <label class="space-y-1.5">
                <span class="text-xs font-semibold text-muted">{$_('audio.filter.source', { default: 'Source' })}</span>
                <input bind:value={sourceFilter} class="input-base min-h-11 focus-visible:ring-2 focus-visible:ring-focus" placeholder={$_('audio.filter.source_placeholder', { default: 'Any source' })} />
            </label>
            <label class="space-y-1.5">
                <span class="flex justify-between gap-2 text-xs font-semibold text-muted">
                    <span>{$_('audio.filter.min_confidence', { default: 'Min confidence' })}</span>
                    <span class="tabular-nums text-accent-ink">{confidencePercent(minConfidence)}</span>
                </span>
                <input bind:value={minConfidence} type="range" min="0" max="1" step="0.05" class="min-h-11 w-full accent-accent focus-visible:ring-2 focus-visible:ring-focus" aria-valuetext={confidencePercent(minConfidence)} />
            </label>
{/snippet}

{#snippet filterActions(after?: () => void)}
    <div class="flex items-end gap-2">
        <button type="submit" class="btn btn-primary min-h-11 px-4" disabled={loading}>{$_('common.apply', { default: 'Apply' })}</button>
        <button type="button" class="btn btn-secondary min-h-11 px-4" onclick={() => { clearFilters(); after?.(); }} disabled={loading}>{$_('common.clear', { default: 'Clear' })}</button>
    </div>
{/snippet}

<div class="space-y-10" data-audio-history-page data-audio-reading={reading}>
    <!-- At 1280 px and wider the log has the main column and what summarises it (the window's
         figures, the most heard species, the sources) stands beside it; on a phone the log comes first. -->
    <div class="grid grid-cols-1 gap-10 xl:grid-cols-12 xl:gap-x-10" data-audio-history-layout>
    <div class="min-w-0 space-y-6 xl:col-span-8 2xl:col-span-9">
    <section data-audio-history-filters aria-label={$_('events.filters.title', { default: 'Filters' })}>
        <!-- A phone gets one Filters button and a sheet; a wider window has the fields in a row. -->
        <div class="flex flex-wrap items-center justify-between gap-3 md:hidden">
            <p class="min-w-0 text-sm text-muted" data-audio-filters-summary>{appliedSummary}</p>
            <button type="button" class="btn btn-secondary min-h-11 px-4" aria-haspopup="dialog" aria-expanded={filterSheetOpen} aria-controls="audio-filter-sheet" onclick={() => (filterSheetOpen = true)} data-audio-filters-open>
                {$_('events.filters.title', { default: 'Filters' })}
            </button>
        </div>
        <form class="hidden border-b border-line-soft pb-6 md:grid md:grid-cols-2 md:gap-4 xl:grid-cols-4 2xl:grid-cols-5" onsubmit={applyFilters}>
            {@render filterFields()}
            <div class="md:col-span-2 xl:col-span-4 2xl:col-span-1 2xl:self-end">{@render filterActions()}</div>
        </form>
        <p class="{filtersChanged ? 'mt-3' : ''} text-sm font-semibold text-status-attention" role="status" data-audio-filters-changed>{filtersChanged ? $_('audio.filter.changed', { default: 'Filters changed. Apply to update the list.' }) : ''}</p>
    </section>
    {#if filterSheetOpen}
        <FilterSheet title={$_('events.filters.title', { default: 'Filters' })} id="audio-filter-sheet" onclose={() => (filterSheetOpen = false)} data-audio-filter-sheet>
            <form class="grid gap-4" onsubmit={(event) => { applyFilters(event); filterSheetOpen = false; }}>
                {@render filterFields()}
                {@render filterActions(() => (filterSheetOpen = false))}
            </form>
        </FilterSheet>
    {/if}

    <section class="space-y-5" data-audio-history-log aria-labelledby="audio-history-title">
        <div class="flex flex-wrap items-start justify-between gap-4">
            <div class="min-w-0 max-w-prose">
                <h2 id="audio-history-title" class="text-xl font-bold text-strong">{$_('audio.history.title', { default: 'Call history' })}</h2>
                <p class="mt-1 text-sm text-muted">{$_('audio.history.sub', { default: 'Every call BirdNET-Go reported, kept apart from camera visits.' })}</p>
            </div>
            <button type="button" class="btn btn-secondary min-h-11 flex-none px-4 text-sm" onclick={() => void loadAudioHistory()} disabled={loading}>
                <svg aria-hidden="true" class="mr-2 h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M20 12a8 8 0 10-2.34 5.66M20 12v-5m0 5h-5" /></svg>
                {$_('common.refresh', { default: 'Refresh' })}
            </button>
        </div>
        {#if authStore.canModify}
            <p class="max-w-prose text-sm text-muted">{$_('audio.history.local_only')}</p>
            {#if lastHiddenId !== null}
                <div class="flex items-center justify-between gap-3 rounded-lg border border-line p-3" role="status">
                    <span>{$_('audio.history.hidden_message')}</span>
                    <button type="button" class="btn btn-secondary min-h-11" disabled={changingVisibility} onclick={() => { if (lastHiddenId !== null) void changeVisibility(lastHiddenId, false); }}>{$_('audio.history.undo')}</button>
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
                {$_('audio.history.empty', { default: 'No calls match these filters.' })}
            </div>
        {:else}
            <!-- A table only where its own box has room at the reader's text size (rem, so larger text
                 stacks the rows); in the side-column layout the box is narrower than the window. -->
            <div class="@container">
            <table class="block w-full text-sm @2xl:table" data-audio-history-table>
                <thead class="hidden border-y border-line-soft @2xl:table-header-group">
                    <tr class="text-left text-xs font-semibold text-muted">
                        <th scope="col" class="py-3 pr-4">{$_('audio.table.sound', { default: 'Sound' })}</th>
                        <th scope="col" class="py-3 pr-4">{$_('audio.table.species', { default: 'Species' })}</th>
                        <th scope="col" class="py-3 pr-4">{$_('audio.table.time', { default: 'Time' })}</th>
                        <th scope="col" class="py-3 pr-4">{$_('audio.table.source', { default: 'Source' })}</th>
                        <th scope="col" class="py-3 text-right">{$_('audio.table.confidence', { default: 'Confidence' })}</th>
                        {#if authStore.canModify}<th scope="col" class="py-3 pl-3 text-right"><span class="sr-only">{$_('audio.history.hide')}</span></th>{/if}
                    </tr>
                </thead>
                <tbody class="block divide-y divide-line-soft border-y border-line-soft @2xl:table-row-group @2xl:border-0">
                    {#each detections as detection}
                        {@const spec = detection.birdnet_id && failedSpectrograms[detection.birdnet_id] ? null : spectrogramUrl(detection.birdnet_id)}
                        {@const specAlt = $_('audio.table.spectrogram_alt', { values: { species: detection.species }, default: 'Spectrogram of the {species} call' })}
                        {@const link = birdnetDetectionUrl(detection.birdnet_id)}
                        <tr class="grid grid-cols-[5rem_minmax(0,1fr)_auto] gap-x-3 py-3 text-ink @2xl:table-row @2xl:py-0">
                            <td class="row-span-3 flex items-center @2xl:table-cell @2xl:w-28 @2xl:py-3 @2xl:pr-4">
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
                            <td class="col-start-2 row-start-1 min-w-0 self-end font-bold text-strong @2xl:table-cell @2xl:py-3 @2xl:pr-4">
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
                            <td class="col-start-2 row-start-2 min-w-0 self-start text-xs text-muted @2xl:table-cell @2xl:whitespace-nowrap @2xl:py-3 @2xl:pr-4">
                                <span class="@2xl:font-bold">{formatDate(detection.timestamp)}</span>
                                <span class="before:mx-1 before:content-['·'] @2xl:block @2xl:before:content-none">{formatTime(detection.timestamp, { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>
                            </td>
                            <!-- On a phone the source sits under the time in the same column, so a long microphone name wraps there instead of squeezing the time out. -->
                            <td class="col-start-2 row-start-3 min-w-0 self-start wrap-break-word text-xs text-muted @2xl:table-cell @2xl:max-w-48 @2xl:py-3 @2xl:pr-4">
                                {detection.source_name || detection.sensor_id || $_('audio.table.unknown_source', { default: 'Unknown source' })}
                            </td>
                            <td class="col-start-3 row-start-1 self-end whitespace-nowrap text-right @2xl:table-cell @2xl:py-3">
                                <span class="font-bold tabular-nums {SCORE_TEXT[scoreBand(detection.confidence)]}">{confidencePercent(detection.confidence)}</span>
                            </td>
                            {#if authStore.canModify}
                                <td class="col-span-3 text-right @2xl:table-cell @2xl:py-3 @2xl:pl-3">
                                    <button type="button" class="btn btn-ghost min-h-11 text-sm" disabled={changingVisibility || loading} onclick={() => void changeVisibility(detection.id, true)}>{$_('audio.history.hide')}</button>
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

    <aside class="min-w-0 space-y-8 xl:col-span-4 2xl:col-span-3" aria-labelledby="audio-summary-title" data-audio-history-side>
        <section class="border-y border-line-soft" data-audio-history-summary aria-busy={reading === 'loading'}>
            <h2 id="audio-summary-title" class="sr-only">{$_('audio.summary_title', { default: 'This window' })}</h2>
        <dl class="grid grid-cols-2 gap-x-6 gap-y-5 py-5 md:grid-cols-4 xl:grid-cols-2">
            <div class="min-w-0">
                <dt class="text-xs font-semibold text-muted">{$_('audio.stat.heard', { default: 'Heard' })}</dt>
                {@render statValue((summary?.total ?? 0).toLocaleString())}
                <dd class="mt-1 text-xs text-muted">{$_('audio.stat.heard_sub', { default: 'Calls BirdNET-Go heard in this window' })}</dd>
            </div>
            <div class="min-w-0">
                <dt class="text-xs font-semibold text-muted">{$_('audio.stat.species', { default: 'Species' })}</dt>
                {@render statValue((summary?.species_count ?? 0).toLocaleString())}
                <dd class="mt-1 text-xs text-muted">{$_('audio.stat.species_sub', { default: 'Heard in this window' })}</dd>
            </div>
            <div class="min-w-0">
                <dt class="text-xs font-semibold text-muted">{$_('audio.stat.peak_hour', { default: 'Peak hour' })}</dt>
                {@render statValue(peakHour ? formatHour(peakHour.hour) : '—')}
                {#if measured}
                    <dd class="mt-1 text-xs text-muted">{peakHour ? $_('audio.stat.peak_hour_sub', { values: { count: peakHour.count }, default: '{count, plural, one {# call} other {# calls}}' }) : $_('audio.stat.no_calls', { default: 'No calls in this window' })}</dd>
                {/if}
            </div>
            <div class="min-w-0">
                <dt class="text-xs font-semibold text-muted">{$_('audio.stat.sources', { default: 'Sources' })}</dt>
                {@render statValue((summary?.source_count ?? 0).toLocaleString())}
                <dd class="mt-1 text-xs text-muted">{$_('audio.stat.sources_sub', { default: 'Microphones or streams' })}</dd>
            </div>
        </dl>
        </section>
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
                    <p class="mt-4 border-y border-line-soft py-6 text-sm text-muted">{$_('audio.chart.empty', { default: 'No activity in this window.' })}</p>
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
                    {#each (summary?.sources ?? []).slice(0, 8) as item}
                        <div class="flex items-center justify-between gap-3 py-3">
                            <div class="min-w-0">
                                <p class="wrap-break-word text-sm font-bold text-strong">{item.source_name}</p>
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

    <!-- Charts take the page's full width; each has its data as a table. -->
    <section class="min-w-0 space-y-8 border-t border-line-soft pt-8" data-audio-history-analytics aria-labelledby="audio-analytics-title">
        <div class="max-w-prose">
            <h2 id="audio-analytics-title" class="text-xl font-bold text-strong">{$_('leaderboard.analytics_section')}</h2>
            <p class="mt-1 text-sm text-muted">{$_('audio.chart.daily_sub', { default: 'Calls BirdNET-Go heard per day' })}</p>
        </div>

        <ChartFigure
            title={$_('audio.chart.daily_title', { default: 'Activity over time' })}
            table={measured && hasDaily ? { columns: [$_('audio.chart.col_day', { default: 'Day' }), $_('audio.chart.col_calls', { default: 'Calls' })], rows: dailyPoints.map((point) => [point.label, point.count.toLocaleString()]) } : { columns: [], rows: [] }}
            class="border-y border-line-soft py-6"
        >
            {#if !measured}
                {@render chartPending()}
            {:else if hasDaily}
                {#key `${applied.days}-${isDark}-${reduceMotion}`}
                    <div class="relative mt-3 chart-h w-full"><canvas use:chartjs={dailyChartConfig()} aria-label={$_('audio.chart.daily_title', { default: 'Activity over time' })}></canvas></div>
                {/key}
            {:else}
                <div class="flex h-60 items-center justify-center text-sm font-semibold text-muted">{$_('audio.chart.empty', { default: 'No activity in this window.' })}</div>
            {/if}
        </ChartFigure>

        <div class="grid min-w-0 gap-8 lg:grid-cols-2">
            <ChartFigure
                title={$_('audio.chart.hourly_title', { default: 'Time of day' })}
                table={measured && hasHourly ? { columns: [$_('audio.chart.col_hour', { default: 'Hour' }), $_('audio.chart.col_calls', { default: 'Calls' })], rows: hourlyPoints.map((point) => [point.label, point.count.toLocaleString()]) } : { columns: [], rows: [] }}
            >
                {#if !measured}
                    {@render chartPending()}
                {:else if hasHourly}
                    {#key `${applied.days}-${isDark}-${reduceMotion}`}
                        <div class="relative mt-3 h-60 w-full"><canvas use:chartjs={hourlyChartConfig()} aria-label={$_('audio.chart.hourly_title', { default: 'Time of day' })}></canvas></div>
                    {/key}
                {:else}
                    <div class="flex h-60 items-center justify-center text-sm font-semibold text-muted">{$_('audio.chart.empty', { default: 'No activity in this window.' })}</div>
                {/if}
            </ChartFigure>
            <ChartFigure
                title={$_('audio.chart.species_title', { default: 'Species mix' })}
                table={measured && hasSpecies ? { columns: [$_('audio.chart.col_species', { default: 'Species' }), $_('audio.chart.col_calls', { default: 'Calls' })], rows: speciesMix.map((item) => [item.species, item.count.toLocaleString()]) } : { columns: [], rows: [] }}
            >
                {#if !measured}
                    {@render chartPending()}
                {:else if hasSpecies}
                    {#key `${applied.days}-${isDark}-${reduceMotion}`}
                        <div class="relative mt-3 chart-h w-full"><canvas use:chartjs={speciesDonutConfig()} bind:this={speciesChartEl} aria-label={$_('audio.chart.species_title', { default: 'Species mix' })}></canvas></div>
                        <div class="mt-2 flex flex-wrap justify-center gap-2" role="group" aria-label={$_('audio.chart.species_title', { default: 'Species mix' })}>
                            {#each speciesMix as item, index}
                                <button type="button" class="btn btn-ghost min-h-9 gap-1.5 px-2 text-xs focus-visible:ring-2 focus-visible:ring-focus {hiddenChartSpecies.includes(index) ? 'opacity-45 line-through' : ''}"
                                    aria-pressed={!hiddenChartSpecies.includes(index)} aria-label="{hiddenChartSpecies.includes(index) ? $_('common.show') : $_('common.hide')} {item.species} {item.count.toLocaleString()}" onclick={() => toggleSpeciesSlice(index)}>
                                    <span class="h-2.5 w-2.5 rounded-xs" style="background-color: {item.other ? otherSpeciesColor : audioSpeciesColor(index)}"></span>{item.species}
                                    <!-- The slice's count beside its name, "Other species" included, so the ring is readable without hovering it. -->
                                    <span class="tabular-nums text-muted" data-audio-mix-count>{item.count.toLocaleString()}</span>
                                </button>
                            {/each}
                        </div>
                    {/key}
                {:else}
                    <div class="flex h-60 items-center justify-center text-sm font-semibold text-muted">{$_('audio.chart.empty', { default: 'No activity in this window.' })}</div>
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
