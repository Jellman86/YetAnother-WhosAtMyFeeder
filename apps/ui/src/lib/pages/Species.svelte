<script lang="ts">
    import { onMount } from 'svelte';
    import { fetchSpecies, type SpeciesCount } from '../api';
    import SpeciesDetailModal from '../components/SpeciesDetailModal.svelte';
    import { settingsStore } from '../stores/settings';
    import { getBirdNames } from '../naming';

    let species: SpeciesCount[] = $state([]);
    let loading = $state(true);
    let error = $state<string | null>(null);
    let sortBy = $state<'count' | 'name'>('count');
    let selectedSpecies = $state<string | null>(null);

    // Derived processed species with naming logic
    let processedSpecies = $derived(() => {
        const showCommon = $settingsStore?.display_common_names ?? true;
        const preferSci = $settingsStore?.scientific_name_primary ?? false;

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

    onMount(async () => {
        await loadSpecies();
    });

    async function loadSpecies() {
        loading = true;
        error = null;
        try {
            species = await fetchSpecies();
        } catch (e) {
            error = 'Failed to load species data';
        } finally {
            loading = false;
        }
    }

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
</script>

<div class="space-y-6">
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <h2 class="text-2xl font-bold text-slate-900 dark:text-white">Species Leaderboard</h2>

        <div class="flex items-center gap-4">
            <div class="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
                <span>{species.length} species</span>
                <span class="text-slate-300 dark:text-slate-600">|</span>
                <span>{totalDetections.toLocaleString()} detections</span>
            </div>

            <button
                onclick={loadSpecies}
                disabled={loading}
                class="text-sm text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 disabled:opacity-50"
            >
                ↻ Refresh
            </button>
        </div>
    </div>

    <!-- Sort Toggle -->
    <div class="flex gap-2">
        <button
            onclick={() => sortBy = 'count'}
            class="px-3 py-1.5 rounded-lg text-sm font-medium transition-colors
                   {sortBy === 'count'
                       ? 'bg-teal-500 text-white'
                       : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700'}"
        >
            By Count
        </button>
        <button
            onclick={() => sortBy = 'name'}
            class="px-3 py-1.5 rounded-lg text-sm font-medium transition-colors
                   {sortBy === 'name'
                       ? 'bg-teal-500 text-white'
                       : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700'}"
        >
            By Name
        </button>
    </div>

    {#if error}
        <div class="p-4 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 border border-red-200 dark:border-red-800">
            {error}
            <button onclick={loadSpecies} class="ml-2 underline">Retry</button>
        </div>
    {/if}

    {#if loading && species.length === 0}
        <div class="space-y-3">
            {#each [1, 2, 3, 4, 5, 6] as _}
                <div class="h-16 bg-slate-100 dark:bg-slate-800 rounded-xl animate-pulse"></div>
            {/each}
        </div>
    {:else if species.length === 0}
        <div class="text-center py-16">
            <span class="text-6xl mb-4 block">🐦</span>
            <h3 class="text-lg font-semibold text-slate-900 dark:text-white mb-2">No species detected yet</h3>
            <p class="text-slate-500 dark:text-slate-400">
                Bird detections will appear here once they're recorded
            </p>
        </div>
    {:else}
        <!-- Stats Cards -->
        <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {#each sortedSpecies().slice(0, 3) as topSpecies, index}
                <button
                    type="button"
                    onclick={() => selectedSpecies = topSpecies.species}
                    class="text-left bg-white/80 dark:bg-slate-800/50 rounded-2xl border border-slate-200/80 dark:border-slate-700/50 p-5 shadow-card dark:shadow-card-dark backdrop-blur-sm transition-all duration-300 hover:shadow-card-hover dark:hover:shadow-card-dark-hover hover:border-teal-300 dark:hover:border-teal-600"
                >
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
                            <p class="text-2xl font-bold text-teal-600 dark:text-teal-400">
                                {topSpecies.count.toLocaleString()}
                            </p>
                                <p class="text-sm font-bold text-teal-600 dark:text-teal-400">
                                    {(totalDetections > 0 ? (topSpecies.count / totalDetections) * 100 : 0).toFixed(1)}% of total
                                </p>
                        </div>
                    </div>
                </button>
            {/each}
        </div>

        <!-- Full Leaderboard -->
        <div class="bg-white/80 dark:bg-slate-800/50 rounded-2xl border border-slate-200/80 dark:border-slate-700/50 overflow-hidden shadow-card dark:shadow-card-dark backdrop-blur-sm">
            <div class="p-4 border-b border-slate-200/80 dark:border-slate-700/50">
                <h3 class="font-semibold text-slate-900 dark:text-white">All Species</h3>
            </div>

            <div class="divide-y divide-slate-100/80 dark:divide-slate-700/50">
                {#each sortedSpecies() as item, index (item.species)}
                    <button
                        type="button"
                        onclick={() => selectedSpecies = item.species}
                        class="w-full text-left p-4 hover:bg-slate-50 dark:hover:bg-slate-700/50 transition-colors"
                    >
                        <div class="flex items-center gap-4">
                            <!-- Rank -->
                            <div class="w-8 text-center">
                                {#if getMedal(index)}
                                    <span class="text-xl">{getMedal(index)}</span>
                                {:else}
                                    <span class="text-sm font-medium text-slate-400 dark:text-slate-500">
                                        #{index + 1}
                                    </span>
                                {/if}
                            </div>

                            <!-- Species Info -->
                            <div class="flex-1 min-w-0">
                                <div class="flex items-center justify-between mb-0.5">
                                    <span class="font-medium text-slate-900 dark:text-white truncate">
                                        {item.displayName}
                                    </span>
                                    <span class="text-sm font-semibold text-slate-600 dark:text-slate-300 ml-2">
                                        {item.count.toLocaleString()}
                                    </span>
                                </div>
                                {#if item.subName}
                                    <p class="text-[10px] italic text-slate-500 dark:text-slate-400 truncate mb-1.5">
                                        {item.subName}
                                    </p>
                                {/if}

                                <!-- Progress Bar -->
                                <div class="h-2 bg-slate-100 dark:bg-slate-700 rounded-full overflow-hidden">
                                    <div
                                        class="h-full rounded-full transition-all duration-500 {getBarColor(index)}"
                                        style="width: {(item.count / maxCount) * 100}%"
                                    ></div>
                                </div>

                                <div class="flex items-center gap-2 text-[10px] text-slate-500 dark:text-slate-400 mt-1">
                                    <div class="w-1.5 h-1.5 rounded-full bg-slate-300 dark:bg-slate-600"></div>
                                    <span>{(totalDetections > 0 ? (item.count / totalDetections) * 100 : 0).toFixed(1)}% of total</span>
                                </div>
                            </div>
                        </div>
                    </button>
                {/each}
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
