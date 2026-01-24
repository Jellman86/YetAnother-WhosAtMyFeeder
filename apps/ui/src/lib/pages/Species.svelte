<script lang="ts">
    import { onMount } from 'svelte';
    import { fetchDetectionsTimeline, fetchSpecies, fetchSpeciesInfo, type DetectionsTimeline, type SpeciesCount, type SpeciesInfo } from '../api';
    import SpeciesDetailModal from '../components/SpeciesDetailModal.svelte';
    import { settingsStore } from '../stores/settings.svelte';
    import { getBirdNames } from '../naming';
    import { _ } from 'svelte-i18n';

    let species: SpeciesCount[] = $state([]);
    let loading = $state(true);
    let error = $state<string | null>(null);
    let sortBy = $state<'count' | 'name'>('count');
    let selectedSpecies = $state<string | null>(null);
    let timeline = $state<DetectionsTimeline | null>(null);
    let speciesInfoCache = $state<Record<string, SpeciesInfo>>({});

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
        if (sortBy === 'count') {
            sorted.sort((a, b) => b.count - a.count);
        } else {
            sorted.sort((a, b) => a.displayName.localeCompare(b.displayName));
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
        await loadTimeline();
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

    async function loadTimeline() {
        try {
            timeline = await fetchDetectionsTimeline(30);
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

    function buildSparklinePath(points: number[], width = 300, height = 100): string {
        if (!points.length) return '';
        const max = Math.max(...points, 1);
        const min = Math.min(...points, 0);
        const range = Math.max(max - min, 1);
        const step = width / Math.max(points.length - 1, 1);
        return points
            .map((value, idx) => {
                const x = idx * step;
                const normalized = (value - min) / range;
                const y = height - normalized * height;
                return `${idx === 0 ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)}`;
            })
            .join(' ');
    }

    let heroInfo = $derived(topByCount ? speciesInfoCache[topByCount.species] : null);
    let streakInfo = $derived(topByStreak ? speciesInfoCache[topByStreak.species] : null);
    let activeInfo = $derived(topBy7d ? speciesInfoCache[topBy7d.species] : null);
    let risingInfo = $derived(topByTrend ? speciesInfoCache[topByTrend.species] : null);
    let recentInfo = $derived(mostRecent ? speciesInfoCache[mostRecent.species] : null);

    let timelineCounts = $derived(timeline?.daily?.map((d) => d.count) || []);
    let timelineMax = $derived(timelineCounts.length ? Math.max(...timelineCounts) : 0);
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
            onclick={() => sortBy = 'count'}
            class="tab-button {sortBy === 'count' ? 'tab-button-active' : 'tab-button-inactive'}"
        >
            {$_('leaderboard.sort_by_count')}
        </button>
        <button
            onclick={() => sortBy = 'name'}
            class="tab-button {sortBy === 'name' ? 'tab-button-active' : 'tab-button-inactive'}"
        >
            {$_('leaderboard.sort_by_name')}
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
                        class="absolute inset-0 bg-center bg-cover blur-xl scale-105 opacity-35 dark:opacity-25"
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
                <div class="card-base rounded-2xl p-4">
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
                        <div>
                            <p class="text-lg font-black text-slate-900 dark:text-white">{topBy7d?.displayName || '—'}</p>
                            <p class="text-xs text-slate-500">{$_('leaderboard.last_7_days')}: {(topBy7d?.count_7d || 0).toLocaleString()}</p>
                        </div>
                    </div>
                </div>
                <div class="card-base rounded-2xl p-4">
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
                        <div>
                            <p class="text-lg font-black text-slate-900 dark:text-white">{topByStreak?.displayName || '—'}</p>
                            <p class="text-xs text-slate-500">{$_('leaderboard.streak_14d')}: {topByStreak?.days_seen_14d || 0} {$_('leaderboard.days')}</p>
                        </div>
                    </div>
                </div>
                <div class="card-base rounded-2xl p-4">
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
                        <div>
                            <p class="text-lg font-black text-slate-900 dark:text-white">{topByTrend?.displayName || '—'}</p>
                            <p class="text-xs text-slate-500">{$_('leaderboard.trend')}: {formatTrend(topByTrend?.trend_delta, topByTrend?.trend_percent)}</p>
                        </div>
                    </div>
                </div>
                <div class="card-base rounded-2xl p-4">
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
                        <div>
                            <p class="text-lg font-black text-slate-900 dark:text-white">{mostRecent?.displayName || '—'}</p>
                            <p class="text-xs text-slate-500">{formatDate(mostRecent?.last_seen)}</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <div class="card-base rounded-3xl p-6 md:p-8 relative overflow-hidden">
            {#if heroInfo?.thumbnail_url}
                <div
                    class="absolute inset-0 bg-center bg-cover blur-3xl scale-110 opacity-20 dark:opacity-15"
                    style={`background-image: url('${heroInfo.thumbnail_url}');`}
                ></div>
            {/if}
            <div class="absolute inset-0 bg-gradient-to-br from-slate-50 via-transparent to-emerald-50 dark:from-slate-900/50 dark:to-emerald-900/20 pointer-events-none"></div>
            <div class="relative">
                <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <div>
                        <p class="text-[10px] uppercase tracking-[0.3em] font-black text-slate-500 dark:text-slate-300">{$_('leaderboard.last_30_days')}</p>
                        <h3 class="text-xl md:text-2xl font-black text-slate-900 dark:text-white">{$_('leaderboard.detections_over_time')}</h3>
                    </div>
                    <div class="text-sm font-semibold text-slate-500 dark:text-slate-400">
                        {$_('leaderboard.detections_count', { values: { count: timeline?.total_count?.toLocaleString() || '0' } })}
                    </div>
                </div>

                <div class="mt-6 h-28 w-full">
                    {#if timeline?.daily?.length}
                        {#key timeline.total_count}
                            <svg viewBox="0 0 300 100" class="w-full h-full">
                                <defs>
                                    <linearGradient id="detectionsGradient" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="0%" stop-color="#10b981" stop-opacity="0.45" />
                                        <stop offset="100%" stop-color="#10b981" stop-opacity="0" />
                                    </linearGradient>
                                </defs>
                                <path
                                    d={`${buildSparklinePath(timeline.daily.map((d) => d.count))} L300,100 L0,100 Z`}
                                    fill="url(#detectionsGradient)"
                                    stroke="none"
                                />
                                <path
                                    d={buildSparklinePath(timeline.daily.map((d) => d.count))}
                                    fill="none"
                                    stroke="#10b981"
                                    stroke-width="2.5"
                                    stroke-linecap="round"
                                />
                                <line x1="0" y1="100" x2="300" y2="100" stroke="#94a3b8" stroke-width="1" opacity="0.3" />
                                <line x1="0" y1="0" x2="0" y2="100" stroke="#94a3b8" stroke-width="1" opacity="0.3" />
                            </svg>
                        {/key}
                    {:else}
                        <div class="h-full w-full rounded-2xl bg-slate-100 dark:bg-slate-800/60 animate-pulse"></div>
                    {/if}
                </div>

                <div class="mt-2 flex items-center justify-between text-[10px] uppercase tracking-widest text-slate-400">
                    <span>{timeline?.daily?.[0]?.date || '—'}</span>
                    <span>{timeline?.daily?.[timeline.daily.length - 1]?.date || '—'}</span>
                </div>
                <div class="mt-1 flex items-center justify-between text-[10px] font-semibold text-slate-500">
                    <span>0</span>
                    <span>{timelineMax.toLocaleString()}</span>
                </div>
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
                                <span>{$_('leaderboard.last_7_days')}: {(topSpecies.count_7d || 0).toLocaleString()}</span>
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
