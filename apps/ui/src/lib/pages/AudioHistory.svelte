<script lang="ts">
    import { onMount } from 'svelte';
    import { _, locale } from 'svelte-i18n';
    import {
        fetchAudioHistory,
        fetchAudioSummary,
        fetchSpeciesInfo,
        type AudioHistoryDetection,
        type AudioHistoryResponse,
        type AudioSummaryResponse,
        type SpeciesInfo
    } from '../api';
    import { chart } from '../actions/apexchart';
    import { themeStore } from '../stores/theme.svelte';
    import { authStore } from '../stores/auth.svelte';
    import { withAuthParams } from '../api/core';
    import { appApiPath, toAppPath } from '../app/url-base';
    import { fetchSettings } from '../api/settings';
    import { formatDate, formatDateTime, formatTime } from '../utils/datetime';
    import { getErrorMessage, isTransientRequestError } from '../utils/error-handling';
    import { logger } from '../utils/logger';
    import SpeciesDetailModal from '../components/SpeciesDetailModal.svelte';
    import type { ApexOptions } from 'apexcharts';

    const PAGE_SIZE = 25;

    let days = $state(30);
    let speciesFilter = $state('');
    let sourceFilter = $state('');
    let minConfidence = $state(0);
    let history = $state<AudioHistoryResponse | null>(null);
    let summary = $state<AudioSummaryResponse | null>(null);
    let loading = $state(true);
    let error = $state<string | null>(null);
    let offset = $state(0);
    let birdnetExternalUrl = $state('');
    let reduceMotion = $state(false);
    let selectedSpecies = $state<string | null>(null);

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

    $effect(() => {
        for (const item of (summary?.top_species ?? []).slice(0, 6)) {
            if (item.species) void loadSpeciesInfo(item.species);
        }
    });

    let detections = $derived<AudioHistoryDetection[]>(history?.items ?? []);
    let canPrevious = $derived(offset > 0);
    let canNext = $derived(Boolean(history && offset + history.limit < history.total));

    let isDark = $derived(themeStore.isDark);
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
            days,
            species: speciesFilter.trim() || undefined,
            source: sourceFilter.trim() || undefined,
            min_confidence: minConfidence,
            limit: includePaging ? PAGE_SIZE : undefined,
            offset: includePaging ? offset : undefined
        };
    }

    async function loadAudioHistory() {
        loading = true;
        error = null;
        try {
            const [nextHistory, nextSummary] = await Promise.all([
                fetchAudioHistory(requestParams(true)),
                fetchAudioSummary(requestParams(false))
            ]);
            history = nextHistory;
            summary = nextSummary;
        } catch (e) {
            error = getErrorMessage(e) || 'Unable to load BirdNET history.';
            history = null;
            summary = null;
            if (isTransientRequestError(e)) {
                logger.warn('BirdNET history fetch failed (transient)', { message: error });
            } else {
                logger.error('Failed to load BirdNET history', e);
            }
        } finally {
            loading = false;
        }
    }

    async function loadBirdnetUrl() {
        if (!authStore.showSettings) {
            birdnetExternalUrl = '';
            return;
        }
        try {
            const settings = await fetchSettings();
            birdnetExternalUrl = settings.birdnet_external_url || settings.birdnet_url || '';
        } catch {
            birdnetExternalUrl = '';
        }
    }

    function applyFilters() {
        offset = 0;
        void loadAudioHistory();
    }

    function clearFilters() {
        days = 30;
        speciesFilter = '';
        sourceFilter = '';
        minConfidence = 0;
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

    function hourLabel(hour: number): string {
        return `${String(hour).padStart(2, '0')}:00`;
    }

    function spectrogramUrl(birdnet_id: number | null | undefined): string | null {
        if (!birdnet_id) return null;
        // Loaded as an <img> src; append the JWT as a query param so it works
        // when authentication is enabled (mirrors Frigate media URLs and RecentAudio).
        return withAuthParams(`${appApiPath(`/audio/spectrogram/${birdnet_id}`)}?width=300`);
    }

    function birdnetDetectionUrl(birdnet_id: number | null | undefined): string | null {
        if (!birdnetExternalUrl || !birdnet_id) return null;
        return `${birdnetExternalUrl.replace(/\/$/, '')}/ui/detections/${birdnet_id}`;
    }

    // Teal palette for audio-derived charts, matching the RecentAudio widget.
    const audioPalette = ['#14b8a6', '#0ea5e9', '#6366f1', '#f59e0b', '#ec4899', '#8b5cf6', '#10b981', '#94a3b8'];

    let dailyChartOptions = $derived((): ApexOptions => {
        const points = summary?.daily_counts ?? [];
        const data = points.map((p) => ({ x: new Date(`${p.date}T00:00:00Z`).getTime(), y: p.count }));
        return {
            chart: { type: 'area', height: 240, toolbar: { show: false }, animations: { enabled: !reduceMotion, speed: 250 }, fontFamily: 'inherit' },
            series: [{ name: $_('audio.chart.heard', { default: 'Heard' }), type: 'area', data }],
            colors: ['#14b8a6'],
            dataLabels: { enabled: false },
            stroke: { curve: 'smooth', width: 2 },
            fill: { type: 'gradient', gradient: { shadeIntensity: 1, opacityFrom: 0.35, opacityTo: 0.03, stops: [0, 100] } },
            xaxis: { type: 'datetime', labels: { style: { colors: '#94a3b8', fontSize: '12px' } }, axisBorder: { show: false }, axisTicks: { show: false } },
            yaxis: { labels: { style: { colors: '#94a3b8', fontSize: '12px' }, formatter: (v: number) => `${Math.round(v)}` } },
            grid: { borderColor: isDark ? 'rgba(148,163,184,0.12)' : 'rgba(148,163,184,0.2)', strokeDashArray: 4, padding: { left: 8, right: 8 } },
            tooltip: { theme: isDark ? 'dark' : 'light', x: { format: 'dd MMM yyyy' } }
        };
    });

    let hourlyChartOptions = $derived((): ApexOptions => {
        const counts = new Array(24).fill(0);
        for (const item of summary?.hourly_counts ?? []) {
            if (item.hour >= 0 && item.hour < 24) counts[item.hour] = item.count;
        }
        return {
            chart: { type: 'bar', height: 240, toolbar: { show: false }, animations: { enabled: !reduceMotion, speed: 200 }, fontFamily: 'inherit' },
            series: [{ name: $_('audio.chart.heard', { default: 'Heard' }), type: 'bar', data: counts.map((c, h) => ({ x: `${String(h).padStart(2, '0')}`, y: c })) }],
            colors: ['#14b8a6'],
            dataLabels: { enabled: false },
            plotOptions: { bar: { borderRadius: 3, columnWidth: '68%' } },
            xaxis: {
                labels: {
                    style: { colors: '#94a3b8', fontSize: '12px' },
                    formatter: (val: string) => (Number(val) % 3 === 0 ? `${val}:00` : '')
                },
                axisBorder: { show: false },
                axisTicks: { show: false },
                tickPlacement: 'on'
            },
            yaxis: { labels: { style: { colors: '#94a3b8', fontSize: '12px' }, formatter: (v: number) => `${Math.round(v)}` } },
            grid: { borderColor: isDark ? 'rgba(148,163,184,0.12)' : 'rgba(148,163,184,0.2)', strokeDashArray: 4 },
            tooltip: { theme: isDark ? 'dark' : 'light', x: { formatter: (val: number) => `${String(val).padStart(2, '0')}:00` } }
        };
    });

    let speciesDonutOptions = $derived((): ApexOptions => {
        const top = (summary?.top_species ?? []).slice(0, 8);
        const labels = top.map((s) => s.species);
        const series = top.map((s) => s.count);
        const total = series.reduce((a, b) => a + b, 0);
        return {
            chart: { type: 'donut', height: 240, toolbar: { show: false }, animations: { enabled: !reduceMotion, speed: 250 }, fontFamily: 'inherit' },
            series,
            labels,
            colors: audioPalette.slice(0, labels.length),
            dataLabels: { enabled: true, formatter: (val: number) => (val >= 6 ? `${Math.round(val)}%` : ''), style: { fontSize: '12px', fontWeight: 600, colors: ['#fff'] }, dropShadow: { enabled: false } },
            plotOptions: {
                pie: {
                    donut: {
                        size: '62%',
                        labels: {
                            show: true,
                            total: { show: true, showAlways: true, label: $_('audio.chart.heard', { default: 'Heard' }), fontSize: '12px', fontWeight: 600, color: isDark ? '#94a3b8' : '#64748b', formatter: () => total.toLocaleString() },
                            value: { show: true, fontSize: '15px', fontWeight: 700, color: isDark ? '#e2e8f0' : '#1e293b', formatter: (val: string) => Number(val).toLocaleString() },
                            name: { show: true, fontSize: '12px', color: isDark ? '#94a3b8' : '#64748b' }
                        }
                    }
                }
            },
            stroke: { width: 1.5, colors: [isDark ? '#1e293b' : '#ffffff'] },
            legend: { position: 'bottom', fontSize: '12px', labels: { colors: isDark ? '#94a3b8' : '#64748b' }, itemMargin: { horizontal: 6, vertical: 2 } },
            tooltip: { theme: isDark ? 'dark' : 'light' }
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
            motionPreference.removeEventListener('change', syncMotionPreference);
            classObserver.disconnect();
        };
    });
</script>

{#if !authStore.canViewAudio}
    <!-- Audio is the owner's to share (#291); a visitor gets words, not errors. -->
    <section data-audio-not-shared class="mx-auto max-w-lg py-16 text-center">
        <p class="text-sm font-semibold text-slate-800 dark:text-slate-100">
            {$_('audio.not_shared_title', { default: 'Audio is not shared publicly' })}
        </p>
        <p class="mt-1 text-sm text-slate-500 dark:text-slate-400">
            {$_('audio.not_shared_body', { default: 'The owner of this instance has turned off audio for visitors.' })}
        </p>
    </section>
{:else}

<div class="space-y-10" data-audio-history-page>
    <section class="border-y border-slate-200/80 dark:border-slate-800" data-audio-history-summary aria-label={$_('audio.history.title')}>
        <dl class="grid grid-cols-2 lg:grid-cols-4">
            <div class="border-b border-r border-slate-200/80 px-3 py-4 dark:border-slate-800 sm:px-5 lg:border-b-0">
                <dt class="text-xs font-semibold text-slate-500 dark:text-slate-400">{$_('audio.stat.heard', { default: 'Heard' })}</dt>
                <dd class="mt-1 text-2xl font-bold tabular-nums text-slate-900 dark:text-white">{(summary?.total ?? 0).toLocaleString()}</dd>
                <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">{$_('audio.stat.heard_sub', { default: 'BirdNET detections in view' })}</p>
            </div>
            <div class="border-b border-slate-200/80 px-3 py-4 dark:border-slate-800 sm:px-5 lg:border-b-0 lg:border-r">
                <dt class="text-xs font-semibold text-slate-500 dark:text-slate-400">{$_('audio.stat.species', { default: 'Species' })}</dt>
                <dd class="mt-1 text-2xl font-bold tabular-nums text-slate-900 dark:text-white">{summary?.species_count ?? 0}</dd>
                <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">{$_('audio.stat.species_sub', { default: 'Audio-derived species' })}</p>
            </div>
            <div class="border-r border-slate-200/80 px-3 py-4 dark:border-slate-800 sm:px-5">
                <dt class="text-xs font-semibold text-slate-500 dark:text-slate-400">{$_('audio.stat.peak_hour', { default: 'Peak hour' })}</dt>
                <dd class="mt-1 text-2xl font-bold tabular-nums text-slate-900 dark:text-white">{peakHour ? hourLabel(peakHour.hour) : '—'}</dd>
                <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">{peakHour ? $_('audio.stat.peak_hour_sub', { values: { count: peakHour.count }, default: `${peakHour.count} detections` }) : $_('audio.stat.no_activity', { default: 'No activity yet' })}</p>
            </div>
            <div class="px-3 py-4 sm:px-5">
                <dt class="text-xs font-semibold text-slate-500 dark:text-slate-400">{$_('audio.stat.sources', { default: 'Sources' })}</dt>
                <dd class="mt-1 text-2xl font-bold tabular-nums text-slate-900 dark:text-white">{summary?.source_count ?? 0}</dd>
                <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">{$_('audio.stat.sources_sub', { default: 'Microphones or streams' })}</p>
            </div>
        </dl>
    </section>

    <section class="border-b border-slate-200/80 pb-6 dark:border-slate-800" data-audio-history-filters>
        <div class="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-[9rem_minmax(10rem,1fr)_minmax(10rem,1fr)_minmax(12rem,1.2fr)_auto]">
            <label class="space-y-1.5">
                <span class="text-xs font-semibold text-slate-500 dark:text-slate-400">{$_('audio.filter.window', { default: 'Window' })}</span>
                <select bind:value={days} class="select-base min-h-11 font-semibold focus-visible:ring-2 focus-visible:ring-brand-500">
                    <option value={1}>{$_('audio.filter.24h', { default: '24 hours' })}</option>
                    <option value={7}>{$_('audio.filter.7d', { default: '7 days' })}</option>
                    <option value={30}>{$_('audio.filter.30d', { default: '30 days' })}</option>
                    <option value={90}>{$_('audio.filter.90d', { default: '90 days' })}</option>
                    <option value={365}>{$_('audio.filter.1y', { default: '1 year' })}</option>
                </select>
            </label>
            <label class="space-y-1.5">
                <span class="text-xs font-semibold text-slate-500 dark:text-slate-400">{$_('audio.filter.species', { default: 'Species' })}</span>
                <input bind:value={speciesFilter} class="input-base min-h-11 focus-visible:ring-2 focus-visible:ring-brand-500" placeholder="Dunnock" />
            </label>
            <label class="space-y-1.5">
                <span class="text-xs font-semibold text-slate-500 dark:text-slate-400">{$_('audio.filter.source', { default: 'Source' })}</span>
                <input bind:value={sourceFilter} class="input-base min-h-11 focus-visible:ring-2 focus-visible:ring-brand-500" placeholder="BirdCam" />
            </label>
            <label class="space-y-1.5">
                <span class="flex justify-between gap-2 text-xs font-semibold text-slate-500 dark:text-slate-400">
                    <span>{$_('audio.filter.min_confidence', { default: 'Min confidence' })}</span>
                    <span class="tabular-nums text-brand-700 dark:text-brand-300">{confidencePercent(minConfidence)}</span>
                </span>
                <input bind:value={minConfidence} type="range" min="0" max="1" step="0.05" class="min-h-11 w-full accent-brand-600 focus-visible:ring-2 focus-visible:ring-brand-500" />
            </label>
            <div class="flex items-end gap-2 md:col-span-2 xl:col-span-1">
                <button type="button" class="btn btn-primary min-h-11 flex-1 px-4 focus-visible:ring-2 focus-visible:ring-brand-500 xl:flex-none" onclick={applyFilters} disabled={loading}>{$_('common.apply', { default: 'Apply' })}</button>
                <button type="button" class="btn btn-secondary min-h-11 flex-1 px-4 focus-visible:ring-2 focus-visible:ring-brand-500 xl:flex-none" onclick={clearFilters} disabled={loading}>{$_('common.clear', { default: 'Clear' })}</button>
            </div>
        </div>
    </section>

    <section class="space-y-5" data-audio-history-log>
        <div class="flex items-start justify-between gap-4">
            <div class="flex min-w-0 items-start gap-3">
                <div class="mt-0.5 flex h-9 w-9 flex-none items-center justify-center rounded-full bg-brand-50 text-brand-700 dark:bg-brand-950/50 dark:text-brand-300">
                    <svg data-audio-section-icon aria-hidden="true" class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M4 12v2m4-5v8m4-13v16m4-13v10m4-7v4" />
                    </svg>
                </div>
                <div>
                    <h3 class="text-xl font-bold text-slate-900 dark:text-white">{$_('audio.history.title', { default: 'Detection history' })}</h3>
                    <p class="mt-1 text-sm text-slate-500 dark:text-slate-400">{$_('audio.history.sub', { default: 'Persisted BirdNET-Go detections, separate from visual visits.' })}</p>
                </div>
            </div>
            <button type="button" class="btn btn-secondary min-h-11 flex-none px-4 text-sm focus-visible:ring-2 focus-visible:ring-brand-500" onclick={() => void loadAudioHistory()} disabled={loading}>
                <svg aria-hidden="true" class="mr-2 h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M20 12a8 8 0 10-2.34 5.66M20 12v-5m0 5h-5" /></svg>
                {$_('common.refresh', { default: 'Refresh' })}
            </button>
        </div>

        {#if error}
            <div role="alert" class="flex flex-col gap-3 border-y border-red-200 bg-red-50/70 px-4 py-4 text-sm font-semibold text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-200 sm:flex-row sm:items-center sm:justify-between">
                <span>{error}</span>
                <button type="button" class="btn btn-secondary min-h-11 px-4 focus-visible:ring-2 focus-visible:ring-brand-500" onclick={() => void loadAudioHistory()}>{$_('common.retry')}</button>
            </div>
        {:else if loading}
            <div class="space-y-1 border-y border-slate-200/80 py-2 dark:border-slate-800" aria-label={$_('common.loading', { default: 'Loading' })}>
                {#each Array.from({ length: 8 }) as _}
                    <div class="h-16 animate-pulse bg-slate-100/80 dark:bg-slate-800/60"></div>
                {/each}
            </div>
        {:else if detections.length === 0}
            <div class="border-y border-dashed border-slate-300 px-4 py-12 text-center text-sm font-semibold text-slate-500 dark:border-slate-700 dark:text-slate-400">
                {$_('audio.history.empty', { default: 'No BirdNET detections match these filters.' })}
            </div>
        {:else}
            <table class="block w-full text-sm md:table" data-audio-history-table>
                <thead class="hidden border-y border-slate-200/80 md:table-header-group dark:border-slate-800">
                    <tr class="text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
                        <th scope="col" class="py-3 pr-4">{$_('audio.table.sound', { default: 'Sound' })}</th>
                        <th scope="col" class="py-3 pr-4">{$_('audio.table.species', { default: 'Species' })}</th>
                        <th scope="col" class="py-3 pr-4">{$_('audio.table.time', { default: 'Time' })}</th>
                        <th scope="col" class="py-3 pr-4">{$_('audio.table.source', { default: 'Source' })}</th>
                        <th scope="col" class="py-3 text-right">{$_('audio.table.confidence', { default: 'Confidence' })}</th>
                    </tr>
                </thead>
                <tbody class="block divide-y divide-slate-200/80 border-y border-slate-200/80 md:table-row-group md:border-0 dark:divide-slate-800 dark:border-slate-800">
                    {#each detections as detection}
                        {@const spec = spectrogramUrl(detection.birdnet_id)}
                        {@const link = birdnetDetectionUrl(detection.birdnet_id)}
                        <tr class="grid grid-cols-[5rem_minmax(0,1fr)_auto] grid-rows-2 gap-x-3 py-3 text-slate-700 md:table-row md:py-0 dark:text-slate-200">
                            <td class="row-span-2 flex items-center md:table-cell md:w-28 md:py-3 md:pr-4">
                                {#if spec}
                                    {#if link}
                                        <a href={link} target="_blank" rel="noopener noreferrer" class="block min-h-11 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500" title={$_('audio.table.open_birdnet', { default: 'Open in BirdNET-Go' })}>
                                            <img data-audio-spectrogram src={spec} alt={detection.species} loading="lazy" class="h-12 w-20 rounded-md object-cover ring-1 ring-slate-200 md:w-24 dark:ring-slate-700" />
                                        </a>
                                    {:else}
                                        <img data-audio-spectrogram src={spec} alt={detection.species} loading="lazy" class="h-12 w-20 rounded-md object-cover ring-1 ring-slate-200 md:w-24 dark:ring-slate-700" />
                                    {/if}
                                {:else}
                                    <div class="flex h-12 w-20 items-center justify-center rounded-md bg-slate-100 text-slate-400 md:w-24 dark:bg-slate-800 dark:text-slate-500">
                                        <svg aria-hidden="true" class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path stroke-linecap="round" stroke-linejoin="round" d="M4 12v2m4-5v8m4-13v16m4-13v10m4-7v4" /></svg>
                                    </div>
                                {/if}
                            </td>
                            <td class="col-start-2 row-start-1 min-w-0 self-end font-bold text-slate-900 md:table-cell md:py-3 md:pr-4 dark:text-white">
                                <span class="flex min-w-0 items-center gap-1">
                                    <span class="truncate">{detection.species}</span>
                                    {#if detection.matched_visual_event_id}
                                        <a
                                            data-audio-visual-match-link
                                            href={toAppPath(`/events?event=${encodeURIComponent(detection.matched_visual_event_id)}`)}
                                            class="inline-flex min-h-11 min-w-11 shrink-0 items-center justify-center rounded-full text-brand-600 transition hover:bg-brand-500/10 hover:text-brand-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 dark:text-brand-300 dark:hover:bg-brand-400/10 dark:hover:text-brand-200"
                                            aria-label={$_('audio.table.open_visual_match')}
                                            title={$_('audio.table.open_visual_match')}
                                        >
                                            <svg aria-hidden="true" class="h-4.5 w-4.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
                                                <path stroke-linecap="round" stroke-linejoin="round" d="M4 7.5A2.5 2.5 0 0 1 6.5 5h8A2.5 2.5 0 0 1 17 7.5v9a2.5 2.5 0 0 1-2.5 2.5h-8A2.5 2.5 0 0 1 4 16.5v-9Z" />
                                                <path stroke-linecap="round" stroke-linejoin="round" d="m17 10 3-2v8l-3-2M8 12l1.5 1.5L13 10" />
                                            </svg>
                                        </a>
                                    {/if}
                                </span>
                            </td>
                            <td class="col-start-2 row-start-2 min-w-0 self-start text-xs text-slate-500 md:table-cell md:whitespace-nowrap md:py-3 md:pr-4 md:text-sm dark:text-slate-400">
                                <span class="md:font-bold">{formatDate(detection.timestamp)}</span>
                                <span class="before:mx-1 before:content-['·'] md:block md:before:content-none">{formatTime(detection.timestamp, { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>
                            </td>
                            <td class="col-start-3 row-start-2 max-w-28 self-start truncate text-right text-xs text-slate-500 md:table-cell md:max-w-48 md:py-3 md:pr-4 md:text-left md:text-sm dark:text-slate-400">
                                {detection.source_name || detection.sensor_id || $_('audio.table.unknown_source', { default: 'Unknown source' })}
                            </td>
                            <td class="col-start-3 row-start-1 self-end whitespace-nowrap text-right md:table-cell md:py-3">
                                <span class="font-bold tabular-nums {detection.confidence > 0.7 ? 'text-green-600 dark:text-green-300' : 'text-amber-600 dark:text-amber-300'}">{confidencePercent(detection.confidence)}</span>
                            </td>
                        </tr>
                    {/each}
                </tbody>
            </table>
            <div class="flex flex-col gap-3 border-b border-slate-200/80 py-4 text-sm font-semibold text-slate-500 sm:flex-row sm:items-center sm:justify-between dark:border-slate-800 dark:text-slate-400">
                <span class="tabular-nums">{$_('audio.history.showing', { values: { from: offset + 1, to: Math.min(offset + (history?.items.length ?? 0), history?.total ?? 0), total: history?.total ?? 0 }, default: `Showing ${offset + 1}-${Math.min(offset + (history?.items.length ?? 0), history?.total ?? 0)} of ${history?.total ?? 0}` })}</span>
                <div class="grid grid-cols-2 gap-2 sm:flex">
                    <button type="button" class="btn btn-secondary min-h-11 px-4 text-sm focus-visible:ring-2 focus-visible:ring-brand-500" onclick={previousPage} disabled={!canPrevious}>{$_('common.previous', { default: 'Previous' })}</button>
                    <button type="button" class="btn btn-secondary min-h-11 px-4 text-sm focus-visible:ring-2 focus-visible:ring-brand-500" onclick={nextPage} disabled={!canNext}>{$_('common.next', { default: 'Next' })}</button>
                </div>
            </div>
        {/if}
    </section>

    <section class="min-w-0 space-y-8 border-t border-slate-200/80 pt-8 dark:border-slate-800" data-audio-history-analytics>
        <div class="flex items-start gap-3">
            <div class="mt-0.5 flex h-9 w-9 flex-none items-center justify-center rounded-full bg-sky-50 text-sky-700 dark:bg-sky-950/50 dark:text-sky-300">
                <svg data-audio-section-icon aria-hidden="true" class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M4 19V9m5 10V5m5 14v-7m5 7V3" />
                </svg>
            </div>
            <div>
                <h3 class="text-xl font-bold text-slate-900 dark:text-white">{$_('leaderboard.analytics_section')}</h3>
                <p class="mt-1 text-sm text-slate-500 dark:text-slate-400">{$_('audio.chart.daily_sub', { default: 'BirdNET-Go detections heard per day' })}</p>
            </div>
        </div>

        <section class="min-w-0 border-y border-slate-200/80 py-6 dark:border-slate-800">
            <h4 class="text-base font-bold text-slate-900 dark:text-white">{$_('audio.chart.daily_title', { default: 'Activity over time' })}</h4>
            {#if loading}
                <div class="mt-3 h-[240px] animate-pulse bg-slate-100/80 dark:bg-slate-800/60"></div>
            {:else if hasDaily}
                {#key `${days}-${isDark}-${reduceMotion}`}
                    <div use:chart={dailyChartOptions()} class="mt-3 w-full"></div>
                {/key}
            {:else}
                <div class="flex h-[240px] items-center justify-center text-sm font-semibold text-slate-400 dark:text-slate-500">{$_('audio.chart.empty', { default: 'No activity in this window.' })}</div>
            {/if}
        </section>

        <div class="grid min-w-0 border-b border-slate-200/80 lg:grid-cols-2 lg:divide-x lg:divide-slate-200/80 dark:border-slate-800 dark:lg:divide-slate-800">
            <section class="min-w-0 border-b border-slate-200/80 py-6 lg:border-b-0 lg:pr-6 dark:border-slate-800">
                <h4 class="text-base font-bold text-slate-900 dark:text-white">{$_('audio.chart.hourly_title', { default: 'Time of day' })}</h4>
                {#if loading}
                    <div class="mt-3 h-[240px] animate-pulse bg-slate-100/80 dark:bg-slate-800/60"></div>
                {:else if hasHourly}
                    {#key `${days}-${isDark}-${reduceMotion}`}
                        <div use:chart={hourlyChartOptions()} class="mt-3 w-full"></div>
                    {/key}
                {:else}
                    <div class="flex h-[240px] items-center justify-center text-sm font-semibold text-slate-400 dark:text-slate-500">{$_('audio.chart.empty', { default: 'No activity in this window.' })}</div>
                {/if}
            </section>
            <section class="min-w-0 py-6 lg:pl-6">
                <h4 class="text-base font-bold text-slate-900 dark:text-white">{$_('audio.chart.species_title', { default: 'Species mix' })}</h4>
                {#if loading}
                    <div class="mt-3 h-[240px] animate-pulse bg-slate-100/80 dark:bg-slate-800/60"></div>
                {:else if hasSpecies}
                    {#key `${days}-${isDark}-${reduceMotion}`}
                        <div use:chart={speciesDonutOptions()} class="mt-3 w-full"></div>
                    {/key}
                {:else}
                    <div class="flex h-[240px] items-center justify-center text-sm font-semibold text-slate-400 dark:text-slate-500">{$_('audio.chart.empty', { default: 'No activity in this window.' })}</div>
                {/if}
            </section>
        </div>

        <div class="grid gap-8 lg:grid-cols-[minmax(0,1fr)_18rem]">
            <section>
                <h4 class="text-base font-bold text-slate-900 dark:text-white">{$_('audio.top_species', { default: 'Top heard species' })}</h4>
                {#if hasSpecies}
                    <ol class="mt-4 grid border-y border-slate-200/80 sm:grid-cols-2 dark:border-slate-800">
                        {#each (summary?.top_species ?? []).slice(0, 6) as item, index}
                            {@const thumb = cachedSpeciesThumb(item.species)}
                            <li class="min-w-0 border-b border-slate-200/80 sm:odd:pr-4 sm:even:border-l sm:even:pl-4 dark:border-slate-800">
                                <button
                                    type="button"
                                    data-audio-top-species-button
                                    onclick={() => selectedSpecies = item.species}
                                    aria-label={$_('leaderboard.view_species', { values: { species: item.species } })}
                                    class="group flex min-h-11 w-full items-center gap-3 py-3 text-left transition-colors hover:bg-slate-50/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand-500 dark:hover:bg-slate-800/35"
                                >
                                    <span class="w-6 flex-none text-center text-xs font-bold tabular-nums text-slate-400 dark:text-slate-500">{index + 1}</span>
                                    <span class="h-11 w-11 flex-none overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
                                        {#if thumb}
                                            <img src={thumb} alt={item.species} loading="lazy" class="h-full w-full object-cover" />
                                        {:else}
                                            <span class="flex h-full w-full items-center justify-center text-slate-400 dark:text-slate-500">
                                                <svg aria-hidden="true" class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path stroke-linecap="round" stroke-linejoin="round" d="M12 3a4 4 0 00-4 4v4a4 4 0 008 0V7a4 4 0 00-4-4Z M6 11a6 6 0 0012 0 M12 17v4 M9 21h6" /></svg>
                                            </span>
                                        {/if}
                                    </span>
                                    <span class="min-w-0 flex-1">
                                        <span class="block truncate font-bold text-slate-900 transition-colors group-hover:text-brand-700 dark:text-white dark:group-hover:text-brand-300">{item.species}</span>
                                        <span class="mt-0.5 block truncate text-xs text-slate-500 dark:text-slate-400">{$_('audio.card.last_heard', { default: 'Last heard' })} {item.last_heard ? formatDateTime(item.last_heard) : '—'}</span>
                                    </span>
                                    <span class="flex-none text-right">
                                        <span class="block font-bold tabular-nums text-brand-700 dark:text-brand-300">{item.count.toLocaleString()}</span>
                                        <span class="block text-xs font-semibold tabular-nums text-slate-500 dark:text-slate-400">{$_('audio.card.avg', { default: 'avg' })} {confidencePercent(item.avg_confidence)}</span>
                                    </span>
                                    <svg aria-hidden="true" class="h-4 w-4 flex-none text-slate-400 transition-transform group-hover:translate-x-0.5 dark:text-slate-500" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8"><path stroke-linecap="round" stroke-linejoin="round" d="m8 5 5 5-5 5" /></svg>
                                </button>
                            </li>
                        {/each}
                    </ol>
                {:else}
                    <p class="mt-4 border-y border-slate-200/80 py-6 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">{$_('audio.chart.empty', { default: 'No activity in this window.' })}</p>
                {/if}
            </section>

            <section class="lg:border-l lg:border-slate-200/80 lg:pl-8 dark:lg:border-slate-800">
                <h4 class="text-base font-bold text-slate-900 dark:text-white">{$_('audio.sources.title', { default: 'Sources' })}</h4>
                <div class="mt-4 divide-y divide-slate-200/80 border-y border-slate-200/80 dark:divide-slate-800 dark:border-slate-800">
                    {#each (summary?.sources ?? []).slice(0, 8) as item}
                        <div class="flex items-center justify-between gap-3 py-3">
                            <div class="min-w-0">
                                <p class="truncate text-sm font-bold text-slate-800 dark:text-slate-100">{item.source_name}</p>
                                <p class="mt-0.5 truncate text-xs text-slate-500 dark:text-slate-400">{$_('audio.card.last_heard', { default: 'Last heard' })} {formatDateTime(item.last_heard)}</p>
                            </div>
                            <span class="flex-none text-sm font-bold tabular-nums text-slate-700 dark:text-slate-200">{item.count.toLocaleString()}</span>
                        </div>
                    {:else}
                        <p class="py-6 text-sm text-slate-500 dark:text-slate-400">{$_('audio.sources.empty', { default: 'No sources yet.' })}</p>
                    {/each}
                </div>
            </section>
        </div>
    </section>
</div>

{#if selectedSpecies}
    <SpeciesDetailModal speciesName={selectedSpecies} onclose={() => selectedSpecies = null} />
{/if}
{/if}
