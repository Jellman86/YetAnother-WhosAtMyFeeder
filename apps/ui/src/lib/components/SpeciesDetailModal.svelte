<script lang="ts">
    import { onMount } from 'svelte';
    import {
        fetchSpeciesStats,
        fetchSpeciesInfo,
        type SpeciesStats,
        type SpeciesInfo,
        getThumbnailUrl
    } from '../api';
    import { getBirdNames } from '../naming';
    import { settingsStore } from '../stores/settings';
    import SimpleBarChart from './SimpleBarChart.svelte';

    interface Props {
        speciesName: string;
        onclose: () => void;
    }

    let { speciesName, onclose }: Props = $props();

    const HOUR_LABELS = Array.from({ length: 24 }, (_, i) => `${i}:00`);
    const DAY_LABELS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    const MONTH_LABELS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

    let stats = $state<SpeciesStats | null>(null);
    let info = $state<SpeciesInfo | null>(null);
    let loading = $state(true);
    let error = $state<string | null>(null);

    let showCommon = $state(true);
    let preferSci = $state(false);
    $effect(() => {
        showCommon = $settingsStore?.display_common_names ?? true;
        preferSci = $settingsStore?.scientific_name_primary ?? false;
    });

    // Content
    let naming = $derived.by(() => {
        if (stats) {
            // Create a pseudo-summary object for naming utility
            const item = {
                species: stats.species_name,
                scientific_name: stats.scientific_name,
                common_name: stats.common_name
            };
            return getBirdNames(item as any, showCommon, preferSci);
        }
        if (info) {
            const item = {
                species: speciesName,
                scientific_name: info.scientific_name,
                common_name: null // info doesn't always have common name separate
            };
            return getBirdNames(item as any, showCommon, preferSci);
        }
        return { primary: speciesName, secondary: null };
    });

    let primaryName = $derived(naming.primary);
    let subName = $derived(naming.secondary);

    onMount(async () => {
        try {
            const [statsData, infoData] = await Promise.all([
                fetchSpeciesStats(speciesName),
                fetchSpeciesInfo(speciesName)
            ]);
            stats = statsData;
            info = infoData;
        } catch (e: any) {
            console.error('Failed to load species details', e);
            error = e.message || 'Failed to load species details';
        } finally {
            loading = false;
        }
    });

    function formatDate(dateStr: string | null): string {
        if (!dateStr) return 'N/A';
        try {
            return new Date(dateStr).toLocaleDateString(undefined, {
                year: 'numeric',
                month: 'short',
                day: 'numeric'
            });
        } catch {
            return 'N/A';
        }
    }

    function formatTime(dateStr: string): string {
        try {
            return new Date(dateStr).toLocaleTimeString(undefined, {
                hour: '2-digit',
                minute: '2-digit'
            });
        } catch {
            return '';
        }
    }

    function handleKeydown(e: KeyboardEvent) {
        if (e.key === 'Escape') {
            onclose();
        }
    }
</script>

<svelte:window onkeydown={handleKeydown} />

<!-- Backdrop -->
<div
    class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
    onclick={onclose}
    onkeydown={(e) => e.key === 'Escape' && onclose()}
    role="dialog"
    aria-modal="true"
    aria-labelledby="modal-title"
    tabindex="-1"
>
    <!-- Modal Container -->
    <div
        class="bg-white dark:bg-slate-800 rounded-2xl shadow-2xl w-full max-w-4xl max-h-[90vh] overflow-hidden
               border border-slate-200 dark:border-slate-700 animate-fade-in"
        onclick={(e) => e.stopPropagation()}
        onkeydown={(e) => e.stopPropagation()}
        role="document"
        tabindex="-1"
    >
        <!-- Header -->
        <div class="flex items-start justify-between p-6 border-b border-slate-200 dark:border-slate-700">
            <div>
                <h2 id="modal-title" class="text-2xl font-bold text-slate-900 dark:text-white">
                    {primaryName}
                </h2>
                {#if subName && subName !== primaryName}
                    <p class="text-sm italic text-slate-500 dark:text-slate-400 mt-1">
                        {subName}
                    </p>
                {/if}
            </div>
            <button
                onclick={onclose}
                class="p-2 rounded-full hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
                aria-label="Close modal"
            >
                <svg class="w-6 h-6 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
            </button>
        </div>

        <!-- Content -->
        <div class="overflow-y-auto max-h-[calc(90vh-140px)] p-6 space-y-6">
            {#if loading}
                <!-- Loading Skeleton -->
                <div class="space-y-6 animate-pulse">
                    <div class="flex gap-4">
                        <div class="w-32 h-32 bg-slate-200 dark:bg-slate-700 rounded-lg"></div>
                        <div class="flex-1 space-y-3">
                            <div class="h-4 bg-slate-200 dark:bg-slate-700 rounded w-3/4"></div>
                            <div class="h-4 bg-slate-200 dark:bg-slate-700 rounded w-full"></div>
                            <div class="h-4 bg-slate-200 dark:bg-slate-700 rounded w-5/6"></div>
                        </div>
                    </div>
                    <div class="grid grid-cols-4 gap-4">
                        {#each [1, 2, 3, 4] as _}
                            <div class="h-24 bg-slate-200 dark:bg-slate-700 rounded-lg"></div>
                        {/each}
                    </div>
                </div>
            {:else if error}
                <div class="text-center py-8">
                    <p class="text-red-500 dark:text-red-400">{error}</p>
                    <button
                        onclick={() => window.location.reload()}
                        class="mt-4 px-4 py-2 text-teal-600 hover:text-teal-700 underline"
                    >
                        Retry
                    </button>
                </div>
            {:else if stats}
                <!-- Hero Image from Wikipedia -->
                {#if info?.thumbnail_url}
                    <section class="relative -mx-6 -mt-6 mb-6">
                        <div class="relative h-48 sm:h-64 overflow-hidden">
                            <img
                                src={info.thumbnail_url}
                                alt={primaryName}
                                class="w-full h-full object-cover"
                                onerror={(e) => {
                                    const target = e.target as HTMLImageElement;
                                    target.parentElement?.classList.add('hidden');
                                }}
                            />
                            <div class="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent"></div>
                            <div class="absolute bottom-4 left-6 right-6">
                                <h3 class="text-2xl font-bold text-white drop-shadow-lg">{primaryName}</h3>
                                {#if subName && subName !== primaryName}
                                    <p class="text-sm italic text-white/80 mt-0.5 drop-shadow">{subName}</p>
                                {/if}
                                {#if info.description}
                                    <p class="text-sm text-white/90 mt-1 drop-shadow">{info.description}</p>
                                {/if}
                            </div>
                        </div>
                    </section>
                {/if}

                <!-- Wikipedia Description -->
                {#if info}
                    <section class="bg-slate-50 dark:bg-slate-700/30 rounded-xl p-4">
                        <div class="flex items-start gap-3">
                            <div class="w-8 h-8 rounded-full bg-slate-200 dark:bg-slate-600 flex items-center justify-center flex-shrink-0">
                                <svg class="w-5 h-5 text-slate-500 dark:text-slate-400" fill="currentColor" viewBox="0 0 24 24">
                                    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 17h-2v-2h2v2zm2.07-7.75l-.9.92C13.45 12.9 13 13.5 13 15h-2v-.5c0-1.1.45-2.1 1.17-2.83l1.24-1.26c.37-.36.59-.86.59-1.41 0-1.1-.9-2-2-2s-2 .9-2 2H8c0-2.21 1.79-4 4-4s4 1.79 4 4c0 .88-.36 1.68-.93 2.25z"/>
                                </svg>
                            </div>
                            <div class="flex-1 min-w-0">
                                {#if info.extract}
                                    <p class="text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
                                        {info.extract}
                                    </p>
                                {:else if !info.thumbnail_url}
                                    <p class="text-sm text-slate-500 dark:text-slate-400 italic">
                                        No Wikipedia information available for this species.
                                    </p>
                                {/if}
                                {#if info.wikipedia_url}
                                    <a
                                        href={info.wikipedia_url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        class="inline-flex items-center gap-1 mt-3 text-sm font-medium text-teal-600 dark:text-teal-400 hover:underline"
                                    >
                                        Read more on Wikipedia
                                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                                        </svg>
                                    </a>
                                {/if}
                            </div>
                        </div>
                    </section>
                {/if}

                <!-- Statistics Overview -->
                <section>
                    <h3 class="text-lg font-semibold text-slate-900 dark:text-white mb-4">Statistics</h3>
                    <div class="grid grid-cols-2 sm:grid-cols-4 gap-4">
                        <div class="bg-gradient-to-br from-teal-500 to-emerald-600 rounded-xl p-4 text-white">
                            <p class="text-3xl font-bold">{stats.total_sightings}</p>
                            <p class="text-sm opacity-90">Total Sightings</p>
                        </div>
                        <div class="bg-slate-100 dark:bg-slate-700 rounded-xl p-4">
                            <p class="text-2xl font-bold text-slate-900 dark:text-white">
                                {(stats.avg_confidence * 100).toFixed(0)}%
                            </p>
                            <p class="text-sm text-slate-500 dark:text-slate-400">Avg Confidence</p>
                        </div>
                        <div class="bg-slate-100 dark:bg-slate-700 rounded-xl p-4">
                            <p class="text-sm font-medium text-slate-900 dark:text-white">
                                {formatDate(stats.first_seen)}
                            </p>
                            <p class="text-sm text-slate-500 dark:text-slate-400">First Seen</p>
                        </div>
                        <div class="bg-slate-100 dark:bg-slate-700 rounded-xl p-4">
                            <p class="text-sm font-medium text-slate-900 dark:text-white">
                                {formatDate(stats.last_seen)}
                            </p>
                            <p class="text-sm text-slate-500 dark:text-slate-400">Last Seen</p>
                        </div>
                    </div>
                </section>

                <!-- Time Distribution Charts -->
                <section>
                    <h3 class="text-lg font-semibold text-slate-900 dark:text-white mb-4">Activity Patterns</h3>

                    <!-- Hourly chart - full width for better visibility -->
                    <div class="bg-slate-50 dark:bg-slate-700/50 rounded-xl p-4 mb-4">
                        <SimpleBarChart
                            data={stats.hourly_distribution}
                            labels={HOUR_LABELS}
                            title="Time of Day"
                            showEveryNthLabel={6}
                        />
                    </div>

                    <!-- Weekly and Monthly side by side -->
                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        <div class="bg-slate-50 dark:bg-slate-700/50 rounded-xl p-4">
                            <SimpleBarChart
                                data={stats.daily_distribution}
                                labels={DAY_LABELS}
                                title="Day of Week"
                            />
                        </div>
                        <div class="bg-slate-50 dark:bg-slate-700/50 rounded-xl p-4">
                            <SimpleBarChart
                                data={stats.monthly_distribution}
                                labels={MONTH_LABELS}
                                title="Month"
                            />
                        </div>
                    </div>
                </section>

                <!-- Camera Breakdown -->
                {#if stats.cameras.length > 0}
                    <section>
                        <h3 class="text-lg font-semibold text-slate-900 dark:text-white mb-4">Camera Breakdown</h3>
                        <div class="space-y-3">
                            {#each stats.cameras as camera}
                                <div class="flex items-center gap-3">
                                    <span class="text-sm font-medium text-slate-700 dark:text-slate-300 w-32 truncate" title={camera.camera_name}>
                                        {camera.camera_name}
                                    </span>
                                    <div class="flex-1 h-4 bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden">
                                        <div
                                            class="h-full bg-teal-500 rounded-full transition-all duration-500"
                                            style="width: {camera.percentage}%"
                                        ></div>
                                    </div>
                                    <span class="text-sm text-slate-500 dark:text-slate-400 w-20 text-right">
                                        {camera.count} ({camera.percentage.toFixed(0)}%)
                                    </span>
                                </div>
                            {/each}
                        </div>
                    </section>
                {/if}

                <!-- Recent Sightings -->
                {#if stats.recent_sightings.length > 0}
                    <section>
                        <h3 class="text-lg font-semibold text-slate-900 dark:text-white mb-4">Recent Sightings</h3>
                        <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
                            {#each stats.recent_sightings as sighting}
                                <div class="bg-slate-100 dark:bg-slate-700 rounded-lg overflow-hidden">
                                    <div class="aspect-square bg-slate-200 dark:bg-slate-600 relative">
                                        <img
                                            src={getThumbnailUrl(sighting.frigate_event)}
                                            alt={sighting.display_name}
                                            class="w-full h-full object-cover"
                                            loading="lazy"
                                            onerror={(e) => {
                                                const target = e.target as HTMLImageElement;
                                                target.style.display = 'none';
                                            }}
                                        />
                                    </div>
                                    <div class="p-2">
                                        <p class="text-xs text-slate-600 dark:text-slate-300">
                                            {formatDate(sighting.detection_time)}
                                        </p>
                                        <p class="text-xs text-slate-500 dark:text-slate-400">
                                            {formatTime(sighting.detection_time)} - {(sighting.score * 100).toFixed(0)}%
                                        </p>
                                    </div>
                                </div>
                            {/each}
                        </div>
                    </section>
                {/if}
            {/if}
        </div>

        <!-- Footer -->
        <div class="flex justify-end p-4 border-t border-slate-200 dark:border-slate-700">
            <button
                onclick={onclose}
                class="px-4 py-2 text-sm font-medium text-slate-700 dark:text-slate-300
                       bg-slate-100 dark:bg-slate-700 rounded-lg
                       hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors"
            >
                Close
            </button>
        </div>
    </div>
</div>

<style>
    .animate-fade-in {
        animation: fadeIn 0.2s ease-out;
    }

    @keyframes fadeIn {
        from {
            opacity: 0;
            transform: scale(0.95);
        }
        to {
            opacity: 1;
            transform: scale(1);
        }
    }

    .line-clamp-4 {
        display: -webkit-box;
        -webkit-line-clamp: 4;
        -webkit-box-orient: vertical;
        overflow: hidden;
    }
</style>
