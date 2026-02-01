<script lang="ts">
    import { onMount } from 'svelte';
    import { analyzeLeaderboardGraph, fetchDetectionsTimeline, fetchLeaderboardAnalysis, fetchSpecies, fetchSpeciesInfo, type DetectionsTimeline, type SpeciesCount, type SpeciesInfo } from '../api';
    import { chart } from '../actions/apexchart';
    import SpeciesDetailModal from '../components/SpeciesDetailModal.svelte';
    import { settingsStore } from '../stores/settings.svelte';
    import { themeStore } from '../stores/theme.svelte';
    import { getBirdNames } from '../naming';
    import { formatTemperature } from '../utils/temperature';
    import { _ } from 'svelte-i18n';

    let species: SpeciesCount[] = $state([]);
    let loading = $state(true);
    let error = $state<string | null>(null);
    let sortBy = $state<'day' | 'week' | 'month'>('week');
    let timelineDays = $state(30);
    let selectedSpecies = $state<string | null>(null);
    let timeline = $state<DetectionsTimeline | null>(null);
    let speciesInfoCache = $state<Record<string, SpeciesInfo>>({});
    let showWeatherBands = $state(false);
    let showTemperature = $state(false);
    let showWind = $state(false);
    let showPrecip = $state(false);
    let chartEl = $state<HTMLDivElement | null>(null);
    let leaderboardAnalysis = $state<string | null>(null);
    let leaderboardAnalysisTimestamp = $state<string | null>(null);
    let leaderboardAnalysisLoading = $state(false);
    let leaderboardAnalysisError = $state<string | null>(null);
    let leaderboardConfigKey = $state<string | null>(null);

    // Derived processed species with naming logic
    let processedSpecies = $derived(() => {
        const showCommon = settingsStore.settings?.display_common_names ?? true;
        const preferSci = settingsStore.settings?.scientific_name_primary ?? false;

        return species.map(item => {
            const naming = getBirdNames(item as any, showCommon, preferSci);
            return {
                ...item,
                displayName: naming.primary,
                subName: naming.secondary
            };
        });
    });

    // Derived sorted species
    let sortedSpecies = $derived(() => {
        const sorted = [...processedSpecies()];
        if (sortBy === 'day') {
            sorted.sort((a, b) => (b.count_1d || 0) - (a.count_1d || 0));
        } else if (sortBy === 'week') {
            sorted.sort((a, b) => (b.count_7d || 0) - (a.count_7d || 0));
        } else {
            sorted.sort((a, b) => (b.count_30d || 0) - (a.count_30d || 0));
        }
        return sorted;
    });

    // Stats
    let totalDetections = $derived(species.reduce((sum, s) => sum + s.count, 0));
    let maxCount = $derived(Math.max(...species.map(s => s.count), 1));
    let totalLast30 = $derived(species.reduce((sum, s) => sum + (s.count_30d || 0), 0));
    let totalLast7 = $derived(species.reduce((sum, s) => sum + (s.count_7d || 0), 0));

    let topByCount = $derived(sortedSpecies()[0]);
    let topBy7d = $derived([...processedSpecies()].sort((a, b) => (b.count_7d || 0) - (a.count_7d || 0))[0]);
    let topByTrend = $derived([...processedSpecies()].sort((a, b) => (b.trend_delta || 0) - (a.trend_delta || 0))[0]);
    let topByStreak = $derived([...processedSpecies()].sort((a, b) => (b.days_seen_14d || 0) - (a.days_seen_14d || 0))[0]);
    let mostRecent = $derived([...processedSpecies()].sort((a, b) => {
        const aTime = a.last_seen ? new Date(a.last_seen).getTime() : 0;
        const bTime = b.last_seen ? new Date(b.last_seen).getTime() : 0;
        return bTime - aTime;
    })[0]);

    onMount(async () => {
        await loadSpecies();
        await loadTimeline(timelineDays);
    });

    async function loadSpecies() {
        loading = true;
        error = null;
        try {
            species = await fetchSpecies();
        } catch (e) {
            error = $_('leaderboard.load_failed');
        } finally {
            loading = false;
        }
    }

    async function loadTimeline(days: number) {
        try {
            timeline = await fetchDetectionsTimeline(days);
        } catch {
            timeline = null;
        }
    }

    async function loadSpeciesInfo(speciesName: string) {
        if (!speciesName || speciesName === "Unknown Bird" || speciesInfoCache[speciesName]) {
            return;
        }
        try {
            const info = await fetchSpeciesInfo(speciesName);
            speciesInfoCache = { ...speciesInfoCache, [speciesName]: info };
        } catch {
            // ignore fetch errors
        }
    }

    $effect(() => {
        if (topByCount?.species) {
            void loadSpeciesInfo(topByCount.species);
        }
        if (topByStreak?.species) {
            void loadSpeciesInfo(topByStreak.species);
        }
        if (topBy7d?.species) {
            void loadSpeciesInfo(topBy7d.species);
        }
        if (topByTrend?.species) {
            void loadSpeciesInfo(topByTrend.species);
        }
        if (mostRecent?.species) {
            void loadSpeciesInfo(mostRecent.species);
        }
    });

    $effect(() => {
        timelineDays = sortBy === 'day' ? 1 : sortBy === 'week' ? 7 : 30;
        void loadTimeline(timelineDays);
    });

    function getBarColor(index: number): string {
        const colors = [
            'bg-amber-500',      // Gold
            'bg-slate-400',      // Silver
            'bg-amber-700',      // Bronze
            'bg-teal-500',
            'bg-blue-500',
            'bg-purple-500',
            'bg-pink-500',
            'bg-indigo-500',
            'bg-cyan-500',
            'bg-emerald-500',
        ];
        return colors[index % colors.length];
    }

    function getMedal(index: number): string {
        if (index === 0) return '🥇';
        if (index === 1) return '🥈';
        if (index === 2) return '🥉';
        return '';
    }

    function formatDate(value?: string | null): string {
        if (!value) return '—';
        try {
            return new Date(value).toLocaleString();
        } catch {
            return '—';
        }
    }

    function formatTrend(delta?: number, percent?: number): string {
        if (!delta) return '0';
        if (percent === undefined || percent === null) {
            return `${delta > 0 ? '+' : ''}${delta}`;
        }
        return `${delta > 0 ? '+' : ''}${delta} (${percent.toFixed(1)}%)`;
    }

    function getHeroBlurb(info: SpeciesInfo | null): string | null {
        if (!info) return null;
        const text = info.description || info.extract || null;
        if (!text) return null;
        const trimmed = text.trim();
        if (trimmed.length <= 220) return trimmed;
        return `${trimmed.slice(0, 217)}...`;
    }

    function getHeroSource(info: SpeciesInfo | null): { label: string; url: string } | null {
        if (!info) return null;
        if (info.wikipedia_url) return { label: 'Wikipedia', url: info.wikipedia_url };
        if (info.summary_source_url) return { label: 'iNaturalist', url: info.summary_source_url };
        if (info.source_url) return { label: 'iNaturalist', url: info.source_url };
        return null;
    }

    let heroInfo = $derived(topByCount ? speciesInfoCache[topByCount.species] : null);
    let heroBlurb = $derived(getHeroBlurb(heroInfo));
    let heroSource = $derived(getHeroSource(heroInfo));
    let streakInfo = $derived(topByStreak ? speciesInfoCache[topByStreak.species] : null);
    let activeInfo = $derived(topBy7d ? speciesInfoCache[topBy7d.species] : null);
    let risingInfo = $derived(topByTrend ? speciesInfoCache[topByTrend.species] : null);
    let recentInfo = $derived(mostRecent ? speciesInfoCache[mostRecent.species] : null);

    let timelineCounts = $derived(timeline?.daily?.map((d) => d.count) || []);
    let timelineMax = $derived(timelineCounts.length ? Math.max(...timelineCounts) : 0);
    let isDark = $derived(() => themeStore.isDark);
    let temperatureUnit = $derived(settingsStore.settings?.location_temperature_unit ?? 'celsius');

    function convertTemperature(value: number | null | undefined) {
        if (value === null || value === undefined || Number.isNaN(value)) return null;
        if (temperatureUnit === 'fahrenheit') {
            return (value * 9) / 5 + 32;
        }
        return value;
    }

    function formatSunTime(value?: string | null) {
        if (!value) return null;
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return null;
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    function getSunRange(key: 'sunrise' | 'sunset') {
        const weather = timeline?.weather || [];
        const times = weather
            .map((w) => (key === 'sunrise' ? w.sunrise : w.sunset))
            .map((t) => formatSunTime(t))
            .filter(Boolean) as string[];
        if (!times.length) return null;
        const sorted = [...times].sort();
        const first = sorted[0];
        const last = sorted[sorted.length - 1];
        return first === last ? first : `${first}–${last}`;
    }

    let sunriseRange = $derived(getSunRange('sunrise'));
    let sunsetRange = $derived(getSunRange('sunset'));
    let weatherAnnotations = $derived(() => {
        const daily = timeline?.daily || [];
        const weather = timeline?.weather || [];
        if (!showWeatherBands || !daily.length || !weather.length) return { xaxis: [] };

        const weatherMap = new Map(weather.map((w) => [w.date, w]));
        const xaxis = [];

        for (const day of daily) {
            const summary = weatherMap.get(day.date);
            if (!summary) continue;
            const am = resolveWeatherBand({
                rain: summary.am_rain,
                snow: summary.am_snow
            });
            const pm = resolveWeatherBand({
                rain: summary.pm_rain,
                snow: summary.pm_snow
            });

            const dayStart = Date.parse(`${day.date}T00:00:00Z`);
            const dayMid = Date.parse(`${day.date}T12:00:00Z`);
            const dayEnd = Date.parse(`${day.date}T24:00:00Z`);

            if (am) {
                xaxis.push({
                    x: dayStart,
                    x2: dayMid,
                    borderColor: 'transparent',
                    fillColor: am.color,
                    opacity: 0.08
                });
            }

            if (pm) {
                xaxis.push({
                    x: dayMid,
                    x2: dayEnd,
                    borderColor: 'transparent',
                    fillColor: pm.color,
                    opacity: 0.08
                });
            }
        }

        return { xaxis };
    });

    function resolveWeatherBand(entry: any) {
        const rain = entry?.rain ?? 0;
        const snow = entry?.snow ?? 0;

        if (snow > 0.1) return { label: $_('detection.weather_snow'), color: '#6366f1' };
        if (rain > 0.2) return { label: $_('detection.weather_rain'), color: '#3b82f6' };
        return null;
    }

    let chartOptions = $derived(() => ({
        chart: {
            type: 'line',
            height: 260,
            width: '100%',
            toolbar: { show: false },
            zoom: { enabled: false },
            animations: { enabled: true, easing: 'easeinout', speed: 500 }
        },
        series: [
            {
                name: 'Detections',
                type: 'area',
                data: timeline?.daily?.map((d) => ({
                    x: Date.parse(`${d.date}T00:00:00Z`),
                    y: d.count
                })) || []
            },
            {
                name: $_('leaderboard.temperature'),
                type: 'line',
                data: showTemperature
                    ? (timeline?.daily || []).map((d) => {
                        const summary = (timeline?.weather || []).find((w) => w.date === d.date);
                        const tempAvg = summary?.temp_avg ?? null;
                        const fallback = (summary?.am_temp != null && summary?.pm_temp != null)
                            ? (summary.am_temp + summary.pm_temp) / 2
                            : (summary?.am_temp ?? summary?.pm_temp ?? null);
                        const temp = convertTemperature(tempAvg ?? fallback);
                        return {
                            x: Date.parse(`${d.date}T00:00:00Z`),
                            y: temp
                        };
                    })
                    : []
            },
            {
                name: $_('leaderboard.wind_avg'),
                type: 'line',
                data: showWind
                    ? (timeline?.daily || []).map((d) => {
                        const summary = (timeline?.weather || []).find((w) => w.date === d.date);
                        return {
                            x: Date.parse(`${d.date}T00:00:00Z`),
                            y: summary?.wind_avg ?? null
                        };
                    })
                    : []
            },
            {
                name: $_('leaderboard.precip'),
                type: 'line',
                data: showPrecip
                    ? (timeline?.daily || []).map((d) => {
                        const summary = (timeline?.weather || []).find((w) => w.date === d.date);
                        return {
                            x: Date.parse(`${d.date}T00:00:00Z`),
                            y: summary?.precip_total ?? null
                        };
                    })
                    : []
            }
        ],
        dataLabels: { enabled: false },
        stroke: {
            curve: 'smooth',
            width: [2, 2, 2, 2],
            colors: ['#10b981', '#f97316', '#0ea5e9', '#a855f7'],
            dashArray: [0, 4, 4, 6]
        },
        fill: {
            type: ['gradient', 'solid'],
            gradient: {
                shadeIntensity: 1,
                opacityFrom: 0.35,
                opacityTo: 0,
                stops: [0, 90, 100]
            }
        },
        markers: { size: [0, showTemperature ? 3 : 0, showWind ? 3 : 0, showPrecip ? 3 : 0], hover: { size: 4 } },
        grid: {
            borderColor: 'rgba(148,163,184,0.2)',
            strokeDashArray: 3,
            padding: { left: 12, right: 12, top: 8, bottom: 4 }
        },
        xaxis: {
            type: 'datetime',
            tickAmount: Math.min(6, (timeline?.daily?.length || 0)),
            labels: { rotate: 0, style: { fontSize: '10px', colors: '#94a3b8' } }
        },
        yaxis: [
            {
                min: 0,
                labels: {
                    style: { fontSize: '10px', colors: '#94a3b8' },
                    formatter: (value: number) => Math.round(value).toString()
                }
            },
            {
                opposite: true,
                show: showTemperature,
                labels: {
                    style: { fontSize: '10px', colors: '#f59e0b' },
                    formatter: (value: number) => formatTemperature(value, temperatureUnit as any)
                }
            },
            {
                opposite: true,
                show: showWind,
                labels: {
                    style: { fontSize: '10px', colors: '#0ea5e9' },
                    formatter: (value: number) => `${Math.round(value)} km/h`
                }
            },
            {
                opposite: true,
                show: showPrecip,
                labels: {
                    style: { fontSize: '10px', colors: '#38bdf8' },
                    formatter: (value: number) => `${value.toFixed(1)} mm`
                }
            }
        ],
        tooltip: {
            theme: isDark() ? 'dark' : 'light',
            x: { format: 'MMM dd' },
            y: [
                { formatter: (value: number) => `${Math.round(value)} detections` },
                { formatter: (value: number) => formatTemperature(value, temperatureUnit as any) },
                { formatter: (value: number) => `${Math.round(value)} km/h` },
                { formatter: (value: number) => `${value.toFixed(1)} mm` }
            ]
        },
        legend: { show: false },
        annotations: weatherAnnotations()
    }));

    function stableStringify(value: any): string {
        if (value === null || typeof value !== 'object') {
            return JSON.stringify(value);
        }
        if (Array.isArray(value)) {
            return `[${value.map(stableStringify).join(',')}]`;
        }
        const keys = Object.keys(value).sort();
        return `{${keys.map((k) => `${JSON.stringify(k)}:${stableStringify(value[k])}`).join(',')}}`;
    }

    async function computeConfigKey(config: Record<string, unknown>): Promise<string> {
        const raw = stableStringify(config);
        const data = new TextEncoder().encode(raw);
        const hash = await crypto.subtle.digest('SHA-256', data);
        return Array.from(new Uint8Array(hash)).map((b) => b.toString(16).padStart(2, '0')).join('');
    }

    function buildLeaderboardConfig() {
        const days = timeline?.days ?? timelineDays;
        const daily = timeline?.daily ?? [];
        const startDate = daily[0]?.date ?? null;
        const endDate = daily[daily.length - 1]?.date ?? null;
        const series = ['Detections'];
        if (showTemperature) series.push($_('leaderboard.temperature'));
        if (showWind) series.push($_('leaderboard.wind_avg'));
        if (showPrecip) series.push($_('leaderboard.precip'));
        return {
            sortBy,
            days,
            startDate,
            endDate,
            totalCount: timeline?.total_count ?? 0,
            showWeatherBands,
            showTemperature,
            showWind,
            showPrecip,
            series
        };
    }

    async function refreshLeaderboardAnalysis() {
        if (!timeline) return;
        leaderboardAnalysisError = null;
        const config = buildLeaderboardConfig();
        const key = await computeConfigKey(config);
        if (leaderboardConfigKey === key && leaderboardAnalysis) return;
        leaderboardConfigKey = key;
        try {
            const result = await fetchLeaderboardAnalysis(key);
            leaderboardAnalysis = result.analysis;
            leaderboardAnalysisTimestamp = result.analysis_timestamp;
        } catch {
            leaderboardAnalysis = null;
            leaderboardAnalysisTimestamp = null;
        }
    }

    $effect(() => {
        if (!timeline) return;
        const _deps = [sortBy, timelineDays, showWeatherBands, showTemperature, showWind, showPrecip];
        void refreshLeaderboardAnalysis();
    });

    async function runLeaderboardAnalysis(force = false) {
        if (!chartEl) return;
        leaderboardAnalysisLoading = true;
        leaderboardAnalysisError = null;
        try {
            const config = buildLeaderboardConfig();
            const key = await computeConfigKey(config);
            leaderboardConfigKey = key;
            const chartInstance = (chartEl as any).__apexchart;
            const dataUri = await chartInstance?.dataURI();
            const imageBase64 = dataUri?.imgURI ?? null;
            if (!imageBase64) {
                throw new Error('Unable to capture chart image');
            }
            const result = await analyzeLeaderboardGraph({
                config: {
                    timeframe: `${config.days} days (${config.startDate ?? 'start'} → ${config.endDate ?? 'end'})`,
                    total_count: config.totalCount,
                    series: config.series,
                    weather_notes: showWeatherBands ? 'AM/PM weather bands are visible.' : '',
                    notes: 'Detections are shown as an area series; other series are weather overlays.'
                },
                image_base64: imageBase64,
                force,
                config_key: key
            });
            leaderboardAnalysis = result.analysis;
            leaderboardAnalysisTimestamp = result.analysis_timestamp;
        } catch (e: any) {
            leaderboardAnalysisError = e?.message || 'Failed to analyze chart';
        } finally {
            leaderboardAnalysisLoading = false;
        }
    }

    function getWindowCount(item: SpeciesCount | undefined): number {
        if (!item) return 0;
        if (sortBy === 'day') return item.count_1d || 0;
        if (sortBy === 'week') return item.count_7d || 0;
        return item.count_30d || 0;
    }

    function getWindowLabel(): string {
        if (sortBy === 'day') return $_('leaderboard.sort_by_day');
        if (sortBy === 'week') return $_('leaderboard.sort_by_week');
        return $_('leaderboard.sort_by_month');
    }
</script>

<div class="space-y-6">
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <h2 class="text-2xl font-bold text-slate-900 dark:text-white">{$_('leaderboard.title')}</h2>

        <div class="flex items-center gap-4">
            <div class="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
                <span>{$_('leaderboard.species_count', { values: { count: species.length } })}</span>
                <span class="text-slate-300 dark:text-slate-600">|</span>
                <span>{$_('leaderboard.detections_count', { values: { count: totalDetections.toLocaleString() } })}</span>
            </div>

            <button
                onclick={loadSpecies}
                disabled={loading}
                class="text-sm text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 disabled:opacity-50"
            >
                ↻ {$_('common.refresh')}
            </button>
        </div>
    </div>

    <!-- Sort Toggle -->
    <div class="flex gap-2">
        <button
            onclick={() => sortBy = 'day'}
            class="tab-button {sortBy === 'day' ? 'tab-button-active' : 'tab-button-inactive'}"
        >
            {$_('leaderboard.sort_by_day')}
        </button>
        <button
            onclick={() => sortBy = 'week'}
            class="tab-button {sortBy === 'week' ? 'tab-button-active' : 'tab-button-inactive'}"
        >
            {$_('leaderboard.sort_by_week')}
        </button>
        <button
            onclick={() => sortBy = 'month'}
            class="tab-button {sortBy === 'month' ? 'tab-button-active' : 'tab-button-inactive'}"
        >
            {$_('leaderboard.sort_by_month')}
        </button>
    </div>

    {#if error}
        <div class="p-4 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 border border-red-200 dark:border-red-800">
            {error}
            <button onclick={loadSpecies} class="ml-2 underline">{$_('common.retry')}</button>
        </div>
    {/if}

    {#if loading && species.length === 0}
        <div class="space-y-3">
            {#each [1, 2, 3, 4, 5, 6] as _}
                <div class="h-16 bg-slate-100 dark:bg-slate-800 rounded-xl animate-pulse"></div>
            {/each}
        </div>
    {:else if species.length === 0}
        <div class="card-base rounded-3xl p-12 text-center">
            <span class="text-6xl mb-4 block">🐦</span>
            <h3 class="text-lg font-semibold text-slate-900 dark:text-white mb-2">{$_('leaderboard.no_species')}</h3>
            <p class="text-slate-500 dark:text-slate-400">
                {$_('leaderboard.no_species_desc')}
            </p>
        </div>
    {:else}
        <div class="grid grid-cols-1 xl:grid-cols-3 gap-4">
            <div class="xl:col-span-2 card-base rounded-3xl p-6 md:p-8 relative overflow-hidden">
                {#if heroInfo?.thumbnail_url}
                    <div
                        class="absolute inset-0 bg-center bg-cover blur-md scale-100 opacity-25 dark:opacity-20"
                        style={`background-image: url('${heroInfo.thumbnail_url}');`}
                    ></div>
                {/if}
                <div class="absolute inset-0 bg-gradient-to-br from-emerald-50 via-transparent to-teal-50 dark:from-emerald-950/30 dark:to-teal-900/20 pointer-events-none"></div>
                <div class="relative space-y-6">
                    <div class="flex items-start justify-between gap-4">
                        <div>
                            <p class="text-[11px] uppercase tracking-[0.24em] font-black text-emerald-600 dark:text-emerald-300">
                                {$_('leaderboard.featured')}
                            </p>
                            <h3 class="text-2xl md:text-3xl font-black text-slate-900 dark:text-white mt-2">
                                {topByCount?.displayName || '—'}
                            </h3>
                            {#if topByCount?.subName}
                                <p class="text-xs italic text-slate-500 dark:text-slate-400">
                                    {topByCount.subName}
                                </p>
                            {/if}
                            {#if heroBlurb}
                                <p class="text-sm text-slate-600 dark:text-slate-300 mt-3 max-w-xl">
                                    {heroBlurb}
                                </p>
                                {#if heroSource}
                                    <a
                                        href={heroSource.url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        class="inline-flex items-center gap-2 text-xs font-semibold text-emerald-700 dark:text-emerald-300 hover:text-emerald-600 dark:hover:text-emerald-200 mt-2"
                                    >
                                        Read more on {heroSource.label}
                                        <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 3h7v7m0-7L10 14m-1 7h11a2 2 0 002-2V9" />
                                        </svg>
                                    </a>
                                {/if}
                            {/if}
                        </div>
                        <button
                            type="button"
                            onclick={() => topByCount && (selectedSpecies = topByCount.species)}
                            class="px-4 py-2 rounded-2xl bg-emerald-500/90 text-white text-xs font-black uppercase tracking-widest shadow-md hover:bg-emerald-500"
                        >
                            {$_('leaderboard.view_details')}
                        </button>
                    </div>

                    <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
                        <div class="rounded-2xl bg-white/80 dark:bg-slate-900/40 border border-slate-200/60 dark:border-slate-700/60 p-3">
                            <p class="text-[10px] uppercase tracking-widest text-slate-400">{$_('leaderboard.total_sightings')}</p>
                            <p class="text-2xl font-black text-slate-900 dark:text-white">
                                {topByCount?.count?.toLocaleString() || '—'}
                            </p>
                        </div>
                        <div class="rounded-2xl bg-white/80 dark:bg-slate-900/40 border border-slate-200/60 dark:border-slate-700/60 p-3">
                            <p class="text-[10px] uppercase tracking-widest text-slate-400">{$_('leaderboard.last_30_days')}</p>
                            <p class="text-xl font-black text-slate-900 dark:text-white">
                                {(topByCount?.count_30d || 0).toLocaleString()}
                            </p>
                        </div>
                        <div class="rounded-2xl bg-white/80 dark:bg-slate-900/40 border border-slate-200/60 dark:border-slate-700/60 p-3">
                            <p class="text-[10px] uppercase tracking-widest text-slate-400">{$_('leaderboard.last_7_days')}</p>
                            <p class="text-xl font-black text-slate-900 dark:text-white">
                                {(topByCount?.count_7d || 0).toLocaleString()}
                            </p>
                        </div>
                        <div class="rounded-2xl bg-white/80 dark:bg-slate-900/40 border border-slate-200/60 dark:border-slate-700/60 p-3">
                            <p class="text-[10px] uppercase tracking-widest text-slate-400">{$_('leaderboard.last_seen')}</p>
                            <p class="text-xs font-semibold text-slate-700 dark:text-slate-300">
                                {formatDate(topByCount?.last_seen)}
                            </p>
                        </div>
                    </div>

                    <div class="flex flex-wrap gap-3 text-[11px] font-semibold text-slate-600 dark:text-slate-300">
                        <span class="px-3 py-1 rounded-full bg-emerald-100/80 dark:bg-emerald-900/30">
                            {$_('leaderboard.trend')}: {formatTrend(topByCount?.trend_delta, topByCount?.trend_percent)}
                        </span>
                        <span class="px-3 py-1 rounded-full bg-slate-100 dark:bg-slate-800/60">
                            {$_('leaderboard.streak_14d')}: {topByCount?.days_seen_14d || 0} {$_('leaderboard.days')}
                        </span>
                        <span class="px-3 py-1 rounded-full bg-slate-100 dark:bg-slate-800/60">
                            {$_('leaderboard.cameras')}:{' '}{topByCount?.camera_count || 0}
                        </span>
                        <span class="px-3 py-1 rounded-full bg-slate-100 dark:bg-slate-800/60">
                            {$_('leaderboard.avg_confidence')}: {(topByCount?.avg_confidence || 0).toFixed(2)}
                        </span>
                    </div>
                </div>
            </div>

            <div class="space-y-3">
                <div class="card-base rounded-2xl p-4 relative overflow-hidden">
                    {#if activeInfo?.thumbnail_url}
                        <div
                            class="absolute inset-0 bg-center bg-cover blur-lg scale-105 opacity-25 dark:opacity-20"
                            style={`background-image: url('${activeInfo.thumbnail_url}');`}
                        ></div>
                    {/if}
                    <p class="text-[10px] uppercase tracking-widest text-slate-400">{$_('leaderboard.most_active')}</p>
                    <div class="flex items-center gap-3 mt-2">
                        {#if activeInfo?.thumbnail_url}
                            <img
                                src={activeInfo.thumbnail_url}
                                alt={topBy7d?.displayName || 'Species'}
                                class="w-10 h-10 rounded-2xl object-cover shadow-md border border-white/70"
                            />
                        {:else}
                            <div class="w-10 h-10 rounded-2xl bg-slate-100 dark:bg-slate-800 flex items-center justify-center text-lg">🐦</div>
                        {/if}
                        <div class="relative">
                            <p class="text-lg font-black text-slate-900 dark:text-white">{topBy7d?.displayName || '—'}</p>
                            <p class="text-xs text-slate-500">{$_('leaderboard.last_7_days')}: {(topBy7d?.count_7d || 0).toLocaleString()}</p>
                        </div>
                    </div>
                </div>
                <div class="card-base rounded-2xl p-4 relative overflow-hidden">
                    {#if streakInfo?.thumbnail_url}
                        <div
                            class="absolute inset-0 bg-center bg-cover blur-lg scale-105 opacity-25 dark:opacity-20"
                            style={`background-image: url('${streakInfo.thumbnail_url}');`}
                        ></div>
                    {/if}
                    <p class="text-[10px] uppercase tracking-widest text-slate-400">{$_('leaderboard.longest_streak')}</p>
                    <div class="flex items-center gap-3 mt-2">
                        {#if streakInfo?.thumbnail_url}
                            <img
                                src={streakInfo.thumbnail_url}
                                alt={topByStreak?.displayName || 'Species'}
                                class="w-10 h-10 rounded-2xl object-cover shadow-md border border-white/70"
                            />
                        {:else}
                            <div class="w-10 h-10 rounded-2xl bg-slate-100 dark:bg-slate-800 flex items-center justify-center text-lg">🐦</div>
                        {/if}
                        <div class="relative">
                            <p class="text-lg font-black text-slate-900 dark:text-white">{topByStreak?.displayName || '—'}</p>
                            <p class="text-xs text-slate-500">{$_('leaderboard.streak_14d')}: {topByStreak?.days_seen_14d || 0} {$_('leaderboard.days')}</p>
                        </div>
                    </div>
                </div>
                <div class="card-base rounded-2xl p-4 relative overflow-hidden">
                    {#if risingInfo?.thumbnail_url}
                        <div
                            class="absolute inset-0 bg-center bg-cover blur-lg scale-105 opacity-25 dark:opacity-20"
                            style={`background-image: url('${risingInfo.thumbnail_url}');`}
                        ></div>
                    {/if}
                    <p class="text-[10px] uppercase tracking-widest text-slate-400">{$_('leaderboard.rising')}</p>
                    <div class="flex items-center gap-3 mt-2">
                        {#if risingInfo?.thumbnail_url}
                            <img
                                src={risingInfo.thumbnail_url}
                                alt={topByTrend?.displayName || 'Species'}
                                class="w-10 h-10 rounded-2xl object-cover shadow-md border border-white/70"
                            />
                        {:else}
                            <div class="w-10 h-10 rounded-2xl bg-slate-100 dark:bg-slate-800 flex items-center justify-center text-lg">🐦</div>
                        {/if}
                        <div class="relative">
                            <p class="text-lg font-black text-slate-900 dark:text-white">{topByTrend?.displayName || '—'}</p>
                            <p class="text-xs text-slate-500">{$_('leaderboard.trend')}: {formatTrend(topByTrend?.trend_delta, topByTrend?.trend_percent)}</p>
                        </div>
                    </div>
                </div>
                <div class="card-base rounded-2xl p-4 relative overflow-hidden">
                    {#if recentInfo?.thumbnail_url}
                        <div
                            class="absolute inset-0 bg-center bg-cover blur-lg scale-105 opacity-25 dark:opacity-20"
                            style={`background-image: url('${recentInfo.thumbnail_url}');`}
                        ></div>
                    {/if}
                    <p class="text-[10px] uppercase tracking-widest text-slate-400">{$_('leaderboard.most_recent')}</p>
                    <div class="flex items-center gap-3 mt-2">
                        {#if recentInfo?.thumbnail_url}
                            <img
                                src={recentInfo.thumbnail_url}
                                alt={mostRecent?.displayName || 'Species'}
                                class="w-10 h-10 rounded-2xl object-cover shadow-md border border-white/70"
                            />
                        {:else}
                            <div class="w-10 h-10 rounded-2xl bg-slate-100 dark:bg-slate-800 flex items-center justify-center text-lg">🐦</div>
                        {/if}
                        <div class="relative">
                            <p class="text-lg font-black text-slate-900 dark:text-white">{mostRecent?.displayName || '—'}</p>
                            <p class="text-xs text-slate-500">{formatDate(mostRecent?.last_seen)}</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <div class="card-base rounded-3xl p-6 md:p-8 relative overflow-hidden flex flex-col">
            {#if heroInfo?.thumbnail_url}
                <div
                    class="absolute inset-0 bg-center bg-cover blur-3xl scale-110 opacity-20 dark:opacity-15"
                    style={`background-image: url('${heroInfo.thumbnail_url}');`}
                ></div>
            {/if}
            <div class="absolute inset-0 bg-gradient-to-br from-slate-50 via-transparent to-emerald-50 dark:from-slate-900/50 dark:to-emerald-900/20 pointer-events-none"></div>
            <div class="relative flex flex-col flex-1">
                <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <div>
                        <p class="text-[10px] uppercase tracking-[0.3em] font-black text-slate-500 dark:text-slate-300">
                            {$_('leaderboard.last_n_days', { values: { days: timeline?.days || timelineDays } })}
                        </p>
                        <h3 class="text-xl md:text-2xl font-black text-slate-900 dark:text-white">{$_('leaderboard.detections_over_time')}</h3>
                    </div>
                    <div class="flex flex-wrap items-center gap-3 text-sm font-semibold text-slate-500 dark:text-slate-400">
                        <span>{$_('leaderboard.detections_count', { values: { count: timeline?.total_count?.toLocaleString() || '0' } })}</span>
                        <button
                            type="button"
                            class="px-3 py-1.5 rounded-full border border-emerald-200/70 dark:border-emerald-800/60 text-[10px] font-black uppercase tracking-widest text-emerald-700 dark:text-emerald-300 bg-emerald-50/70 dark:bg-emerald-900/20 hover:bg-emerald-100/70 dark:hover:bg-emerald-900/40 disabled:opacity-60 disabled:cursor-not-allowed"
                            disabled={!timeline?.daily?.length || leaderboardAnalysisLoading}
                            onclick={() => runLeaderboardAnalysis(!!leaderboardAnalysis)}
                        >
                            {leaderboardAnalysisLoading
                                ? $_('leaderboard.ai_analyzing', { default: 'Analyzing…' })
                                : leaderboardAnalysis
                                    ? $_('leaderboard.ai_rerun', { default: 'Rerun analysis' })
                                    : $_('leaderboard.ai_analyze', { default: 'Analyze chart' })}
                        </button>
                    </div>
                </div>

                <div class="mt-6 w-full flex-1 min-h-[140px] max-h-[240px]">
                    {#if timeline?.daily?.length}
                        {#key timeline.total_count}
                            <div use:chart={chartOptions()} bind:this={chartEl} class="w-full h-[240px]"></div>
                        {/key}
                    {:else}
                        <div class="h-full w-full rounded-2xl bg-slate-100 dark:bg-slate-800/60 animate-pulse"></div>
                    {/if}
                </div>

                <div class="mt-3 flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
                    <span>{timeline?.days || timelineDays}-day total: {timeline?.total_count?.toLocaleString() || '0'}</span>
                    <span>•</span>
                    <span>Peak day: {timelineMax.toLocaleString()}</span>
                    <span>•</span>
                    <span>Avg/day: {timeline?.daily?.length ? Math.round((timeline?.total_count || 0) / timeline.daily.length).toLocaleString() : '0'}</span>
                </div>
                {#if leaderboardAnalysisLoading || leaderboardAnalysisError || leaderboardAnalysis}
                    <div class="mt-4 rounded-2xl border border-slate-200/70 dark:border-slate-700/60 bg-white/70 dark:bg-slate-900/40 px-4 py-3 text-sm text-slate-600 dark:text-slate-300 shadow-sm">
                        <div class="flex flex-wrap items-center justify-between gap-2 text-[10px] uppercase tracking-widest font-black text-slate-400">
                            <span>{$_('leaderboard.ai_summary', { default: 'AI insight' })}</span>
                            {#if leaderboardAnalysisTimestamp}
                                <span class="font-semibold normal-case tracking-normal">{new Date(leaderboardAnalysisTimestamp).toLocaleString()}</span>
                            {/if}
                        </div>
                        {#if leaderboardAnalysisLoading}
                            <p class="mt-2 text-xs text-slate-500">{$_('leaderboard.ai_analyzing', { default: 'Analyzing…' })}</p>
                        {:else if leaderboardAnalysisError}
                            <p class="mt-2 text-xs text-rose-500">{leaderboardAnalysisError}</p>
                        {:else if leaderboardAnalysis}
                            <p class="mt-2 whitespace-pre-wrap">{leaderboardAnalysis}</p>
                        {/if}
                    </div>
                {/if}
                <div class="mt-4 flex flex-wrap items-center gap-3 text-[10px] text-slate-400">
                    <div class="flex items-center gap-2">
                        <button
                            type="button"
                            onclick={() => showWeatherBands = !showWeatherBands}
                            class="px-2 py-1 rounded-full border border-slate-200/70 dark:border-slate-700/60 text-[9px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400"
                        >
                            <span aria-hidden="true">🌦️</span>
                            {showWeatherBands ? $_('leaderboard.hide_weather') : $_('leaderboard.show_weather')}
                        </button>
                        <button
                            type="button"
                            onclick={() => showTemperature = !showTemperature}
                            class="px-2 py-1 rounded-full border border-slate-200/70 dark:border-slate-700/60 text-[9px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400"
                        >
                            <span aria-hidden="true">🌡️</span>
                            {showTemperature ? $_('leaderboard.hide_temperature') : $_('leaderboard.show_temperature')}
                        </button>
                        <button
                            type="button"
                            onclick={() => showWind = !showWind}
                            class="px-2 py-1 rounded-full border border-slate-200/70 dark:border-slate-700/60 text-[9px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400"
                        >
                            <span aria-hidden="true">💨</span>
                            {showWind ? $_('leaderboard.hide_wind') : $_('leaderboard.show_wind')}
                        </button>
                        <button
                            type="button"
                            onclick={() => showPrecip = !showPrecip}
                            class="px-2 py-1 rounded-full border border-slate-200/70 dark:border-slate-700/60 text-[9px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400"
                        >
                            <span aria-hidden="true">🌧️</span>
                            {showPrecip ? $_('leaderboard.hide_precip') : $_('leaderboard.show_precip')}
                        </button>
                    </div>
                    <div class="flex items-center gap-1">
                        <span class="inline-block w-2 h-2 rounded-full bg-blue-500/40"></span>
                        {$_('detection.weather_rain')}
                    </div>
                    <div class="flex items-center gap-1">
                        <span class="inline-block w-2 h-2 rounded-full bg-indigo-500/40"></span>
                        {$_('detection.weather_snow')}
                    </div>
                    <div class="flex items-center gap-1">
                        <span class="inline-block w-2 h-2 rounded-full bg-orange-500/60"></span>
                        {$_('leaderboard.temperature')}
                    </div>
                    <div class="flex items-center gap-1">
                        <span class="inline-block w-2 h-2 rounded-full bg-sky-500/60"></span>
                        {$_('leaderboard.wind_avg')}
                    </div>
                    <div class="flex items-center gap-1">
                        <span class="inline-block w-2 h-2 rounded-full bg-fuchsia-500/70"></span>
                        {$_('leaderboard.precip')}
                    </div>
                    <span class="text-slate-400/70">{$_('leaderboard.am_pm_bands')}</span>
                </div>

                {#if sunriseRange || sunsetRange}
                    <div class="mt-2 flex flex-wrap items-center gap-2 text-[10px] text-slate-500">
                        {#if sunriseRange}
                            <span class="inline-flex items-center gap-1 rounded-full border border-amber-200/60 dark:border-amber-700/50 bg-amber-50/60 dark:bg-amber-900/20 px-2 py-1 text-amber-700 dark:text-amber-300">
                                <span aria-hidden="true">🌅</span>
                                {$_('leaderboard.sunrise')}: {sunriseRange}
                            </span>
                        {/if}
                        {#if sunsetRange}
                            <span class="inline-flex items-center gap-1 rounded-full border border-orange-200/60 dark:border-orange-700/50 bg-orange-50/60 dark:bg-orange-900/20 px-2 py-1 text-orange-700 dark:text-orange-300">
                                <span aria-hidden="true">🌇</span>
                                {$_('leaderboard.sunset')}: {sunsetRange}
                            </span>
                        {/if}
                    </div>
                {/if}
            </div>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
            {#each sortedSpecies().slice(0, 3) as topSpecies, index}
                <button
                    type="button"
                    onclick={() => selectedSpecies = topSpecies.species}
                    class="card-base card-interactive text-left rounded-2xl p-5 transition-all duration-300 relative"
                    title={topSpecies.species === "Unknown Bird" ? $_('leaderboard.unidentified_desc') : ""}
                >
                    {#if topSpecies.species === "Unknown Bird"}
                        <div class="absolute top-2 right-2 bg-amber-500 text-white rounded-full w-7 h-7 flex items-center justify-center text-xs font-black shadow-md" title={$_('leaderboard.needs_review')}>
                            ?
                        </div>
                    {/if}
                    <div class="flex items-center gap-3">
                        <span class="text-3xl">{getMedal(index)}</span>
                        <div class="flex-1 min-w-0">
                            <h4 class="font-semibold text-slate-900 dark:text-white truncate">
                                {topSpecies.displayName}
                            </h4>
                            {#if topSpecies.subName}
                                <p class="text-[10px] italic text-slate-500 dark:text-slate-400 truncate -mt-0.5">
                                    {topSpecies.subName}
                                </p>
                            {/if}
                            <div class="flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-slate-400 mt-2">
                                <span class="font-black text-emerald-600 dark:text-emerald-400">{topSpecies.count.toLocaleString()}</span>
                                <span>•</span>
                                <span>{getWindowLabel()}: {getWindowCount(topSpecies).toLocaleString()}</span>
                                <span>•</span>
                                <span>{$_('leaderboard.trend')}: {formatTrend(topSpecies.trend_delta, topSpecies.trend_percent)}</span>
                            </div>
                        </div>
                    </div>
                </button>
            {/each}
        </div>

        <div class="card-base rounded-2xl overflow-hidden backdrop-blur-sm">
            <div class="p-4 border-b border-slate-200/80 dark:border-slate-700/50 flex items-center justify-between">
                <h3 class="font-semibold text-slate-900 dark:text-white">{$_('leaderboard.all_species')}</h3>
                <div class="text-xs text-slate-500 dark:text-slate-400">
                    {$_('leaderboard.last_30_days')}: {totalLast30.toLocaleString()} · {$_('leaderboard.last_7_days')}: {totalLast7.toLocaleString()}
                </div>
            </div>

            <div class="overflow-x-auto" data-testid="leaderboard-table-wrap">
                <table class="min-w-[900px] w-full text-left text-sm" data-testid="leaderboard-table">
                    <thead class="text-[10px] uppercase tracking-widest text-slate-400 bg-slate-50 dark:bg-slate-900/40">
                        <tr>
                            <th class="px-4 py-3">{$_('leaderboard.rank')}</th>
                            <th class="px-4 py-3">{$_('leaderboard.species')}</th>
                            <th class="px-4 py-3 text-right">{$_('leaderboard.total_sightings')}</th>
                            <th class="px-4 py-3 text-right">{$_('leaderboard.last_30_days')}</th>
                            <th class="px-4 py-3 text-right">{$_('leaderboard.last_7_days')}</th>
                            <th class="px-4 py-3 text-right">{$_('leaderboard.trend')}</th>
                            <th class="px-4 py-3 text-right">{$_('leaderboard.streak_14d')}</th>
                            <th class="px-4 py-3">{$_('leaderboard.last_seen')}</th>
                        </tr>
                    </thead>
                    <tbody>
                        {#each sortedSpecies() as item, index (item.species)}
                            <tr
                                class="border-b border-slate-100/70 dark:border-slate-800/60 hover:bg-slate-50/70 dark:hover:bg-slate-900/30 transition cursor-pointer"
                                role="button"
                                tabindex="0"
                                aria-label={$_('leaderboard.view_species', { values: { species: item.displayName } })}
                                onclick={() => selectedSpecies = item.species}
                                onkeydown={(e) => {
                                    if (e.key === 'Enter' || e.key === ' ') {
                                        e.preventDefault();
                                        selectedSpecies = item.species;
                                    }
                                }}
                                title={item.species === "Unknown Bird" ? $_('leaderboard.unidentified_desc') : ""}
                            >
                                <td class="px-4 py-3 font-semibold text-slate-500 dark:text-slate-400">
                                    {getMedal(index) || `#${index + 1}`}
                                </td>
                                <td class="px-4 py-3">
                                    <div class="flex items-center gap-2">
                                        <span class="font-semibold text-slate-900 dark:text-white">
                                            {item.displayName}
                                        </span>
                                        {#if item.species === "Unknown Bird"}
                                            <span class="inline-flex items-center justify-center bg-amber-500 text-white rounded-full w-5 h-5 text-[10px] font-black" title={$_('leaderboard.needs_review')}>?</span>
                                        {/if}
                                    </div>
                                    {#if item.subName}
                                        <div class="text-[10px] italic text-slate-500 dark:text-slate-400">
                                            {item.subName}
                                        </div>
                                    {/if}
                                </td>
                                <td class="px-4 py-3 text-right font-bold text-slate-700 dark:text-slate-300">
                                    {item.count.toLocaleString()}
                                </td>
                                <td class="px-4 py-3 text-right text-slate-600 dark:text-slate-300">
                                    {(item.count_30d || 0).toLocaleString()}
                                </td>
                                <td class="px-4 py-3 text-right text-slate-600 dark:text-slate-300">
                                    {(item.count_7d || 0).toLocaleString()}
                                </td>
                                <td class="px-4 py-3 text-right text-slate-600 dark:text-slate-300">
                                    {formatTrend(item.trend_delta, item.trend_percent)}
                                </td>
                                <td class="px-4 py-3 text-right text-slate-600 dark:text-slate-300">
                                    {item.days_seen_14d || 0}
                                </td>
                                <td class="px-4 py-3 text-slate-500 dark:text-slate-400 whitespace-nowrap">
                                    {formatDate(item.last_seen)}
                                </td>
                            </tr>
                        {/each}
                    </tbody>
                </table>
            </div>
        </div>
    {/if}
</div>

<!-- Species Detail Modal -->
{#if selectedSpecies}
    <SpeciesDetailModal
        speciesName={selectedSpecies}
        onclose={() => selectedSpecies = null}
    />
{/if}
