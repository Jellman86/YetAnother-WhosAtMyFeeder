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
    import { appApiPath } from '../app/url-base';
    import { fetchSettings } from '../api/settings';
    import { formatDate, formatDateTime, formatTime } from '../utils/datetime';
    import { getErrorMessage, isTransientRequestError } from '../utils/error-handling';
    import { logger } from '../utils/logger';
    import type { ApexOptions } from 'apexcharts';

    const PAGE_SIZE = 100;

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

    // Species recognition thumbnails for the "Top heard species" cards, reusing the
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
            // Enrichment disabled or lookup failed — the card falls back to the 🐦 placeholder.
        } finally {
            const { [key]: _discarded, ...rest } = speciesInfoPending;
            speciesInfoPending = rest;
        }
    }

    $effect(() => {
        for (const item of (summary?.top_species ?? []).slice(0, 9)) {
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
            chart: { type: 'area', height: 240, toolbar: { show: false }, animations: { enabled: true, speed: 450 }, fontFamily: 'inherit' },
            series: [{ name: $_('audio.chart.heard', { default: 'Heard' }), type: 'area', data }],
            colors: ['#14b8a6'],
            dataLabels: { enabled: false },
            stroke: { curve: 'smooth', width: 2 },
            fill: { type: 'gradient', gradient: { shadeIntensity: 1, opacityFrom: 0.35, opacityTo: 0.03, stops: [0, 100] } },
            xaxis: { type: 'datetime', labels: { style: { colors: '#94a3b8', fontSize: '10px' } }, axisBorder: { show: false }, axisTicks: { show: false } },
            yaxis: { labels: { style: { colors: '#94a3b8', fontSize: '10px' }, formatter: (v: number) => `${Math.round(v)}` } },
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
            chart: { type: 'bar', height: 240, toolbar: { show: false }, animations: { enabled: true, speed: 350 }, fontFamily: 'inherit' },
            series: [{ name: $_('audio.chart.heard', { default: 'Heard' }), type: 'bar', data: counts.map((c, h) => ({ x: `${String(h).padStart(2, '0')}`, y: c })) }],
            colors: ['#14b8a6'],
            dataLabels: { enabled: false },
            plotOptions: { bar: { borderRadius: 3, columnWidth: '68%' } },
            xaxis: {
                labels: {
                    style: { colors: '#94a3b8', fontSize: '9px' },
                    formatter: (val: string) => (Number(val) % 3 === 0 ? `${val}:00` : '')
                },
                axisBorder: { show: false },
                axisTicks: { show: false },
                tickPlacement: 'on'
            },
            yaxis: { labels: { style: { colors: '#94a3b8', fontSize: '10px' }, formatter: (v: number) => `${Math.round(v)}` } },
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
            chart: { type: 'donut', height: 240, toolbar: { show: false }, animations: { enabled: true, speed: 450 }, fontFamily: 'inherit' },
            series,
            labels,
            colors: audioPalette.slice(0, labels.length),
            dataLabels: { enabled: true, formatter: (val: number) => (val >= 6 ? `${Math.round(val)}%` : ''), style: { fontSize: '10px', fontWeight: 600, colors: ['#fff'] }, dropShadow: { enabled: false } },
            plotOptions: {
                pie: {
                    donut: {
                        size: '62%',
                        labels: {
                            show: true,
                            total: { show: true, showAlways: true, label: $_('audio.chart.heard', { default: 'Heard' }), fontSize: '11px', fontWeight: 600, color: isDark ? '#94a3b8' : '#64748b', formatter: () => total.toLocaleString() },
                            value: { show: true, fontSize: '15px', fontWeight: 700, color: isDark ? '#e2e8f0' : '#1e293b', formatter: (val: string) => Number(val).toLocaleString() },
                            name: { show: true, fontSize: '10px', color: isDark ? '#94a3b8' : '#64748b' }
                        }
                    }
                }
            },
            stroke: { width: 1.5, colors: [isDark ? '#1e293b' : '#ffffff'] },
            legend: { position: 'bottom', fontSize: '11px', labels: { colors: isDark ? '#94a3b8' : '#64748b' }, itemMargin: { horizontal: 6, vertical: 2 } },
            tooltip: { theme: isDark ? 'dark' : 'light' }
        };
    });

    onMount(() => {
        void loadAudioHistory();
        void loadBirdnetUrl();
    });
</script>

<div class="space-y-6">
    <!-- Stat tiles -->
    <section class="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <div class="card-base rounded-2xl p-4">
            <p class="text-xs font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">{$_('audio.stat.heard', { default: 'Heard' })}</p>
            <p class="mt-2 text-3xl font-black text-slate-900 dark:text-white">{(summary?.total ?? 0).toLocaleString()}</p>
            <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">{$_('audio.stat.heard_sub', { default: 'BirdNET detections in view' })}</p>
        </div>
        <div class="card-base rounded-2xl p-4">
            <p class="text-xs font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">{$_('audio.stat.species', { default: 'Species' })}</p>
            <p class="mt-2 text-3xl font-black text-slate-900 dark:text-white">{summary?.species_count ?? 0}</p>
            <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">{$_('audio.stat.species_sub', { default: 'Audio-derived species' })}</p>
        </div>
        <div class="card-base rounded-2xl p-4">
            <p class="text-xs font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">{$_('audio.stat.peak_hour', { default: 'Peak hour' })}</p>
            <p class="mt-2 text-3xl font-black text-slate-900 dark:text-white">{peakHour ? hourLabel(peakHour.hour) : '—'}</p>
            <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">{peakHour ? $_('audio.stat.peak_hour_sub', { values: { count: peakHour.count }, default: `${peakHour.count} detections` }) : $_('audio.stat.no_activity', { default: 'No activity yet' })}</p>
        </div>
        <div class="card-base rounded-2xl p-4">
            <p class="text-xs font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">{$_('audio.stat.sources', { default: 'Sources' })}</p>
            <p class="mt-2 text-3xl font-black text-slate-900 dark:text-white">{summary?.source_count ?? 0}</p>
            <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">{$_('audio.stat.sources_sub', { default: 'Microphones or streams' })}</p>
        </div>
    </section>

    <!-- Filters -->
    <section class="card-base rounded-2xl p-4">
        <div class="grid grid-cols-1 gap-3 md:grid-cols-5">
            <label class="space-y-1">
                <span class="text-xs font-bold uppercase tracking-widest text-slate-500 dark:text-slate-400">{$_('audio.filter.window', { default: 'Window' })}</span>
                <select bind:value={days} class="select-base font-semibold">
                    <option value={1}>{$_('audio.filter.24h', { default: '24 hours' })}</option>
                    <option value={7}>{$_('audio.filter.7d', { default: '7 days' })}</option>
                    <option value={30}>{$_('audio.filter.30d', { default: '30 days' })}</option>
                    <option value={90}>{$_('audio.filter.90d', { default: '90 days' })}</option>
                    <option value={365}>{$_('audio.filter.1y', { default: '1 year' })}</option>
                </select>
            </label>
            <label class="space-y-1">
                <span class="text-xs font-bold uppercase tracking-widest text-slate-500 dark:text-slate-400">{$_('audio.filter.species', { default: 'Species' })}</span>
                <input bind:value={speciesFilter} class="input-base" placeholder="Dunnock" />
            </label>
            <label class="space-y-1">
                <span class="text-xs font-bold uppercase tracking-widest text-slate-500 dark:text-slate-400">{$_('audio.filter.source', { default: 'Source' })}</span>
                <input bind:value={sourceFilter} class="input-base" placeholder="BirdCam" />
            </label>
            <label class="space-y-1">
                <span class="text-xs font-bold uppercase tracking-widest text-slate-500 dark:text-slate-400">{$_('audio.filter.min_confidence', { default: 'Min confidence' })} · {confidencePercent(minConfidence)}</span>
                <input bind:value={minConfidence} type="range" min="0" max="1" step="0.05" class="h-10 w-full accent-teal-600" />
            </label>
            <div class="flex items-end gap-2">
                <button type="button" class="btn btn-primary flex-1 px-4 py-2.5" onclick={applyFilters}>{$_('common.apply', { default: 'Apply' })}</button>
                <button type="button" class="btn btn-secondary flex-1 px-4 py-2.5" onclick={clearFilters}>{$_('common.clear', { default: 'Clear' })}</button>
            </div>
        </div>
    </section>

    {#if error}
        <div class="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm font-semibold text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-200">
            {error}
        </div>
    {/if}

    <!-- Daily activity timeline -->
    <section class="card-base rounded-2xl p-4">
        <div class="mb-3 flex items-center justify-between gap-3">
            <div>
                <h2 class="text-lg font-black text-slate-900 dark:text-white">{$_('audio.chart.daily_title', { default: 'Activity over time' })}</h2>
                <p class="text-xs text-slate-500 dark:text-slate-400">{$_('audio.chart.daily_sub', { default: 'BirdNET-Go detections heard per day' })}</p>
            </div>
        </div>
        {#if loading}
            <div class="h-[240px] animate-pulse rounded-xl bg-slate-100 dark:bg-slate-800"></div>
        {:else if hasDaily}
            {#key `${days}-${isDark}`}
                <div use:chart={dailyChartOptions()} class="w-full"></div>
            {/key}
        {:else}
            <div class="flex h-[240px] items-center justify-center text-sm font-semibold text-slate-400 dark:text-slate-500">{$_('audio.chart.empty', { default: 'No activity in this window.' })}</div>
        {/if}
    </section>

    <!-- Hourly + species distribution -->
    <div class="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <section class="card-base rounded-2xl p-4">
            <h2 class="mb-3 text-base font-black text-slate-900 dark:text-white">{$_('audio.chart.hourly_title', { default: 'Time of day' })}</h2>
            {#if loading}
                <div class="h-[240px] animate-pulse rounded-xl bg-slate-100 dark:bg-slate-800"></div>
            {:else if hasHourly}
                {#key `${days}-${isDark}`}
                    <div use:chart={hourlyChartOptions()} class="w-full"></div>
                {/key}
            {:else}
                <div class="flex h-[240px] items-center justify-center text-sm font-semibold text-slate-400 dark:text-slate-500">{$_('audio.chart.empty', { default: 'No activity in this window.' })}</div>
            {/if}
        </section>
        <section class="card-base rounded-2xl p-4">
            <h2 class="mb-3 text-base font-black text-slate-900 dark:text-white">{$_('audio.chart.species_title', { default: 'Species mix' })}</h2>
            {#if loading}
                <div class="h-[240px] animate-pulse rounded-xl bg-slate-100 dark:bg-slate-800"></div>
            {:else if hasSpecies}
                {#key `${days}-${isDark}`}
                    <div use:chart={speciesDonutOptions()} class="w-full"></div>
                {/key}
            {:else}
                <div class="flex h-[240px] items-center justify-center text-sm font-semibold text-slate-400 dark:text-slate-500">{$_('audio.chart.empty', { default: 'No activity in this window.' })}</div>
            {/if}
        </section>
    </div>

    <!-- Top heard species cards -->
    {#if hasSpecies}
        <section class="card-base rounded-2xl p-4">
            <h2 class="mb-4 text-base font-black text-slate-900 dark:text-white">{$_('audio.top_species', { default: 'Top heard species' })}</h2>
            <div class="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {#each (summary?.top_species ?? []).slice(0, 9) as item, index}
                    {@const thumb = cachedSpeciesThumb(item.species)}
                    <div class="rounded-xl border border-slate-200/70 bg-slate-50/60 p-3 dark:border-slate-700/60 dark:bg-slate-900/30">
                        <div class="flex items-start justify-between gap-3">
                            <div class="flex min-w-0 items-start gap-3">
                                <div class="h-11 w-11 flex-shrink-0 overflow-hidden rounded-xl border border-slate-200 bg-slate-100 dark:border-slate-700 dark:bg-slate-800">
                                    {#if thumb}
                                        <img src={thumb} alt={item.species} loading="lazy" class="h-full w-full object-cover" />
                                    {:else}
                                        <div class="flex h-full w-full items-center justify-center text-base text-slate-400 dark:text-slate-500">🐦</div>
                                    {/if}
                                </div>
                                <div class="min-w-0">
                                    <div class="flex items-center gap-2">
                                        <span class="text-xs font-black text-slate-400 dark:text-slate-500">#{index + 1}</span>
                                        <span class="truncate font-black text-slate-900 dark:text-white">{item.species}</span>
                                    </div>
                                    <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">
                                        {$_('audio.card.last_heard', { default: 'Last heard' })} {item.last_heard ? formatDateTime(item.last_heard) : '—'}
                                    </p>
                                    <div class="mt-1.5 flex items-center gap-3 text-[11px] font-semibold text-slate-500 dark:text-slate-400">
                                        <span>{$_('audio.card.avg', { default: 'avg' })} {confidencePercent(item.avg_confidence)}</span>
                                        <span>{$_('audio.card.max', { default: 'max' })} {confidencePercent(item.max_confidence)}</span>
                                    </div>
                                </div>
                            </div>
                            <span class="flex-shrink-0 rounded-full bg-teal-100 px-2.5 py-1 text-sm font-black text-teal-700 dark:bg-teal-900/40 dark:text-teal-300">{item.count}</span>
                        </div>
                    </div>
                {/each}
            </div>
        </section>
    {/if}

    <div class="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <!-- Detail table -->
        <section class="card-base rounded-2xl p-4">
            <div class="mb-4 flex items-center justify-between gap-3">
                <div>
                    <h2 class="text-lg font-black text-slate-900 dark:text-white">{$_('audio.history.title', { default: 'Detection history' })}</h2>
                    <p class="text-xs text-slate-500 dark:text-slate-400">{$_('audio.history.sub', { default: 'Persisted BirdNET-Go detections, separate from visual visits.' })}</p>
                </div>
                <button type="button" class="btn btn-secondary px-4 py-2 text-sm" onclick={() => void loadAudioHistory()} disabled={loading}>{$_('common.refresh', { default: 'Refresh' })}</button>
            </div>

            {#if loading}
                <div class="space-y-2">
                    {#each Array.from({ length: 8 }) as _}
                        <div class="h-16 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-800"></div>
                    {/each}
                </div>
            {:else if detections.length === 0}
                <div class="rounded-xl border border-dashed border-slate-300 p-8 text-center text-sm font-semibold text-slate-500 dark:border-slate-700 dark:text-slate-400">
                    {$_('audio.history.empty', { default: 'No BirdNET detections match these filters.' })}
                </div>
            {:else}
                <div class="overflow-x-auto">
                    <table class="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-800">
                        <thead>
                            <tr class="text-left text-xs font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">
                                <th class="py-2 pr-4">{$_('audio.table.sound', { default: 'Sound' })}</th>
                                <th class="py-2 pr-4">{$_('audio.table.time', { default: 'Time' })}</th>
                                <th class="py-2 pr-4">{$_('audio.table.species', { default: 'Species' })}</th>
                                <th class="py-2 pr-4">{$_('audio.table.source', { default: 'Source' })}</th>
                                <th class="py-2 pr-4 text-right">{$_('audio.table.confidence', { default: 'Confidence' })}</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-slate-100 dark:divide-slate-800">
                            {#each detections as detection}
                                {@const spec = spectrogramUrl(detection.birdnet_id)}
                                {@const link = birdnetDetectionUrl(detection.birdnet_id)}
                                <tr class="text-slate-700 dark:text-slate-200">
                                    <td class="py-2.5 pr-4">
                                        {#if spec}
                                            {#if link}
                                                <a href={link} target="_blank" rel="noopener noreferrer" title={$_('audio.table.open_birdnet', { default: 'Open in BirdNET-Go' })}>
                                                    <img src={spec} alt="" loading="lazy" class="h-9 w-24 rounded-md object-cover ring-1 ring-slate-200 dark:ring-slate-700" />
                                                </a>
                                            {:else}
                                                <img src={spec} alt="" loading="lazy" class="h-9 w-24 rounded-md object-cover ring-1 ring-slate-200 dark:ring-slate-700" />
                                            {/if}
                                        {:else}
                                            <div class="flex h-9 w-24 items-center justify-center rounded-md bg-slate-100 text-slate-300 dark:bg-slate-800 dark:text-slate-600">
                                                <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4"/></svg>
                                            </div>
                                        {/if}
                                    </td>
                                    <td class="whitespace-nowrap py-2.5 pr-4">
                                        <div class="font-bold">{formatDate(detection.timestamp)}</div>
                                        <div class="text-xs text-slate-500 dark:text-slate-400">{formatTime(detection.timestamp, { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</div>
                                    </td>
                                    <td class="py-2.5 pr-4 font-black">{detection.species}</td>
                                    <td class="py-2.5 pr-4">{detection.source_name || detection.sensor_id || $_('audio.table.unknown_source', { default: 'Unknown source' })}</td>
                                    <td class="whitespace-nowrap py-2.5 pr-4 text-right">
                                        <span class="font-black {detection.confidence > 0.7 ? 'text-green-600 dark:text-green-300' : 'text-amber-600 dark:text-amber-300'}">{confidencePercent(detection.confidence)}</span>
                                    </td>
                                </tr>
                            {/each}
                        </tbody>
                    </table>
                </div>
                <div class="mt-4 flex items-center justify-between gap-3 border-t border-slate-200 pt-4 text-xs font-semibold text-slate-500 dark:border-slate-800 dark:text-slate-400">
                    <span>{$_('audio.history.showing', { values: { from: offset + 1, to: Math.min(offset + (history?.items.length ?? 0), history?.total ?? 0), total: history?.total ?? 0 }, default: `Showing ${offset + 1}-${Math.min(offset + (history?.items.length ?? 0), history?.total ?? 0)} of ${history?.total ?? 0}` })}</span>
                    <div class="flex gap-2">
                        <button type="button" class="btn btn-secondary px-4 py-1.5 text-sm" onclick={previousPage} disabled={!canPrevious}>{$_('common.previous', { default: 'Previous' })}</button>
                        <button type="button" class="btn btn-secondary px-4 py-1.5 text-sm" onclick={nextPage} disabled={!canNext}>{$_('common.next', { default: 'Next' })}</button>
                    </div>
                </div>
            {/if}
        </section>

        <!-- Sources sidebar -->
        <aside class="space-y-6">
            <section class="card-base rounded-2xl p-4">
                <h2 class="text-base font-black text-slate-900 dark:text-white">{$_('audio.sources.title', { default: 'Sources' })}</h2>
                <div class="mt-4 space-y-3">
                    {#each (summary?.sources ?? []).slice(0, 10) as item}
                        <div class="flex items-start justify-between gap-3">
                            <div class="min-w-0">
                                <p class="truncate text-sm font-black text-slate-800 dark:text-slate-100">{item.source_name}</p>
                                <p class="text-xs text-slate-500 dark:text-slate-400">{$_('audio.card.last_heard', { default: 'Last heard' })} {formatDateTime(item.last_heard)}</p>
                            </div>
                            <span class="flex-shrink-0 rounded-full bg-slate-100 px-2 py-1 text-xs font-black text-slate-700 dark:bg-slate-800 dark:text-slate-200">{item.count}</span>
                        </div>
                    {:else}
                        <p class="text-sm text-slate-500 dark:text-slate-400">{$_('audio.sources.empty', { default: 'No sources yet.' })}</p>
                    {/each}
                </div>
            </section>
        </aside>
    </div>
</div>
