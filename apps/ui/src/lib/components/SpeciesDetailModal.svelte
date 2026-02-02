<script lang="ts">
    import { onMount } from 'svelte';
    import {
        fetchSpeciesStats,
        fetchSpeciesInfo,
        fetchEbirdNearby,
        fetchEbirdNotable,
        reclassifyDetection,
        type SpeciesStats,
        type SpeciesInfo,
        type EbirdNearbyResult,
        type EbirdNotableResult,
        type Detection,
        getThumbnailUrl
    } from '../api';
    import { getBirdNames } from '../naming';
    import { settingsStore } from '../stores/settings.svelte';
    import { toastStore } from '../stores/toast.svelte';
    import SimpleBarChart from './SimpleBarChart.svelte';
    import VideoPlayer from './VideoPlayer.svelte';
    import { _ } from 'svelte-i18n';
    import { trapFocus } from '../utils/focus-trap';

    interface Props {
        speciesName: string;
        onclose: () => void;
    }

    let { speciesName, onclose }: Props = $props();

    const HOUR_LABELS = Array.from({ length: 24 }, (_, i) => `${i}:00`);
    const DAY_LABELS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    const MONTH_LABELS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

    let modalElement = $state<HTMLElement | null>(null);
    let stats = $state<SpeciesStats | null>(null);

    $effect(() => {
        if (modalElement) {
            return trapFocus(modalElement);
        }
    });

    let info = $state<SpeciesInfo | null>(null);
    let loading = $state(true);
    let error = $state<string | null>(null);
    let isUnknownBird = $state(false);

    // Enrichment (eBird)
    let ebirdNearby = $state<EbirdNearbyResult | null>(null);
    let ebirdNearbyLoading = $state(false);
    let ebirdNearbyError = $state<string | null>(null);
    let ebirdNotable = $state<EbirdNotableResult | null>(null);
    let ebirdNotableLoading = $state(false);
    let ebirdNotableError = $state<string | null>(null);

    // Video playback state
    let showVideo = $state(false);
    let selectedSighting = $state<Detection | null>(null);

    // Reclassification state
    let reclassifying = $state(false);

    let showCommon = $state(true);
    let preferSci = $state(false);
    $effect(() => {
        showCommon = settingsStore.settings?.display_common_names ?? true;
        preferSci = settingsStore.settings?.scientific_name_primary ?? false;
    });

    const enrichmentModeSetting = $derived(settingsStore.settings?.enrichment_mode ?? 'per_enrichment');
    const enrichmentSingleProviderSetting = $derived(settingsStore.settings?.enrichment_single_provider ?? 'wikipedia');
    const enrichmentSightingsProvider = $derived(
        enrichmentModeSetting === 'single'
            ? enrichmentSingleProviderSetting
            : (settingsStore.settings?.enrichment_sightings_source ?? 'disabled')
    );
    const enrichmentSeasonalityProvider = $derived(
        enrichmentModeSetting === 'single'
            ? enrichmentSingleProviderSetting
            : (settingsStore.settings?.enrichment_seasonality_source ?? 'disabled')
    );
    const enrichmentRarityProvider = $derived(
        enrichmentModeSetting === 'single'
            ? enrichmentSingleProviderSetting
            : (settingsStore.settings?.enrichment_rarity_source ?? 'disabled')
    );
    const ebirdEnabled = $derived(settingsStore.settings?.ebird_enabled ?? false);
    const ebirdRadius = $derived(settingsStore.settings?.ebird_default_radius_km ?? 25);
    const ebirdDaysBack = $derived(settingsStore.settings?.ebird_default_days_back ?? 14);
    const showEbirdNearby = $derived(
        enrichmentSightingsProvider === 'ebird' || enrichmentSeasonalityProvider === 'ebird'
    );
    const showEbirdNotable = $derived(enrichmentRarityProvider === 'ebird');
    const enrichmentLinksProviders = $derived(
        enrichmentModeSetting === 'single'
            ? [enrichmentSingleProviderSetting]
            : (settingsStore.settings?.enrichment_links_sources ?? ['wikipedia', 'inaturalist'])
    );
    const enrichmentLinksProvidersNormalized = $derived(enrichmentLinksProviders.map((provider) => provider.toLowerCase()));

    const UNKNOWN_SPECIES_NAME = 'Unknown Bird';
    const UNKNOWN_LABELS = new Set(['unknown bird', 'unknown', 'background']);

    function isUnknownLabel(label: string | null | undefined) {
        const normalized = (label || '').trim().toLowerCase();
        return UNKNOWN_LABELS.has(normalized);
    }

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

    let infoSourceChips = $derived.by(() => {
        if (!info) return [];
        const items: { label: string; url: string | null }[] = [];
        const push = (label: string | null, url: string | null) => {
            if (!label) return;
            const normalized = label.toLowerCase();
            if (!enrichmentLinksProvidersNormalized.includes(normalized)) return;
            const existing = items.find((item) => item.label === label);
            if (existing) {
                if (!existing.url && url) existing.url = url;
                return;
            }
            items.push({ label, url: url || null });
        };

        push(info.source, info.source_url);
        push(info.summary_source, info.summary_source_url);

        if (items.length === 0 && info.wikipedia_url) {
            if (enrichmentLinksProvidersNormalized.includes('wikipedia')) {
                items.push({ label: 'Wikipedia', url: info.wikipedia_url });
            }
        }

        return items;
    });

    async function loadEbirdNearby(name: string) {
        ebirdNearbyLoading = true;
        ebirdNearbyError = null;
        try {
            ebirdNearby = await fetchEbirdNearby(name);
        } catch (e: any) {
            ebirdNearbyError = e?.message || 'Failed to load eBird sightings';
        } finally {
            ebirdNearbyLoading = false;
        }
    }

    async function loadEbirdNotable() {
        ebirdNotableLoading = true;
        ebirdNotableError = null;
        try {
            ebirdNotable = await fetchEbirdNotable();
        } catch (e: any) {
            ebirdNotableError = e?.message || 'Failed to load eBird notable sightings';
        } finally {
            ebirdNotableLoading = false;
        }
    }


    onMount(async () => {
        // Check if this is an unknown bird detection
        isUnknownBird = isUnknownLabel(speciesName);

        try {
            // Always fetch stats
            const statsData = await fetchSpeciesStats(isUnknownBird ? UNKNOWN_SPECIES_NAME : speciesName);
            stats = statsData;

            // Only fetch Wikipedia info for identified species
            if (!isUnknownBird) {
                const infoData = await fetchSpeciesInfo(speciesName);
                info = infoData;
            }

            if (!isUnknownBird && ebirdEnabled && showEbirdNearby) {
                void loadEbirdNearby(speciesName);
            }
            if (!isUnknownBird && ebirdEnabled && showEbirdNotable) {
                void loadEbirdNotable();
            }
        } catch (e: any) {
            console.error('Failed to load species details', e);
            if (!isUnknownBird) {
                error = e.message || 'Failed to load species details';
            }
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

    function formatEbirdDate(dateStr?: string | null): string {
        if (!dateStr) return '—';
        try {
            return new Date(dateStr).toLocaleString();
        } catch {
            return '—';
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

    function handleOpenExplorer() {
        window.location.assign(`/events?species=${encodeURIComponent(UNKNOWN_SPECIES_NAME)}`);
    }

    async function handleReclassify(strategy: 'snapshot' | 'video') {
        // Get the most recent sighting for reclassification
        const recentSighting = stats?.recent_sightings?.[0];
        if (!recentSighting || reclassifying) return;

        reclassifying = true;
        try {
            const result = await reclassifyDetection(recentSighting.frigate_event, strategy);

            // Check if backend used a different strategy (fallback occurred)
            if (result.actual_strategy && result.actual_strategy !== strategy) {
                toastStore.warning(`⚠️ Video not available - snapshot used instead`);
            }

            toastStore.success(`Reclassification complete: ${result.new_species} (${(result.new_score * 100).toFixed(0)}%)`);

            // Close modal after successful reclassification
            setTimeout(() => {
                onclose();
            }, 2000);
        } catch (e: any) {
            console.error('Failed to reclassify', e);
            toastStore.error(`Failed to reclassify: ${e.message || 'Unknown error'}`);
        } finally {
            reclassifying = false;
        }
    }
</script>

<svelte:window onkeydown={handleKeydown} />

<!-- Backdrop -->
<div
    class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
    onclick={(e) => {
        if (e.target === e.currentTarget) {
            onclose();
        }
    }}
    onkeydown={(e) => e.key === 'Escape' && onclose()}
    role="dialog"
    aria-modal="true"
    aria-labelledby="modal-title"
    tabindex="-1"
>
    <!-- Modal Container -->
    <div
        bind:this={modalElement}
        class="bg-white dark:bg-slate-800 rounded-2xl shadow-2xl w-full max-w-4xl max-h-[90vh] overflow-hidden
               border border-slate-200 dark:border-slate-700 animate-fade-in"
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
                type="button"
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
            {:else}
                <!-- Unknown Bird Message and Reclassify Options -->
                {#if isUnknownBird}
                    <section class="bg-amber-50 dark:bg-amber-900/20 rounded-2xl p-6 border-2 border-amber-200 dark:border-amber-800">
                        <div class="flex items-start gap-4">
                            <!-- Icon -->
                            <div class="flex-shrink-0 w-12 h-12 rounded-full bg-amber-500 flex items-center justify-center">
                                <span class="text-2xl text-white">?</span>
                            </div>

                            <!-- Content -->
                            <div class="flex-1">
                                <h3 class="text-xl font-bold text-amber-900 dark:text-amber-100 mb-2">
                                    {$_('leaderboard.needs_review')}
                                </h3>
                                <p class="text-sm text-amber-800 dark:text-amber-200 mb-4">
                                    {$_('leaderboard.unidentified_desc')}
                                </p>

                                <!-- Reclassify Buttons -->
                                <div class="flex flex-wrap gap-3">
                                    <button
                                        onclick={() => handleReclassify('snapshot')}
                                        disabled={reclassifying || !stats?.recent_sightings?.[0]}
                                        class="px-4 py-2 bg-teal-600 hover:bg-teal-700 disabled:bg-slate-400 disabled:cursor-not-allowed text-white font-semibold rounded-lg transition-colors shadow-md flex items-center gap-2"
                                    >
                                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                                        </svg>
                                        {reclassifying ? $_('common.testing') : $_('actions.deep_reclassify')}
                                    </button>

                                    <button
                                        onclick={() => handleReclassify('video')}
                                        disabled={reclassifying || !stats?.recent_sightings?.[0]?.has_clip || !stats?.recent_sightings?.[0]}
                                        class="px-4 py-2 bg-brand-600 hover:bg-brand-700 disabled:bg-slate-400 disabled:cursor-not-allowed text-white font-semibold rounded-lg transition-colors shadow-md flex items-center gap-2"
                                        title={!stats?.recent_sightings?.[0]?.has_clip ? 'Video clip not available' : ''}
                                    >
                                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                                        </svg>
                                        {reclassifying ? $_('common.testing') : $_('actions.reclassify')}
                                    </button>

                                    <button
                                        type="button"
                                        onclick={handleOpenExplorer}
                                        class="px-4 py-2 bg-white/80 dark:bg-slate-900/40 border border-amber-200 dark:border-amber-700 text-amber-800 dark:text-amber-100 font-semibold rounded-lg transition-colors shadow-sm flex items-center gap-2"
                                    >
                                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 10h16M4 14h16M4 18h16" />
                                        </svg>
                                        {$_('detection.review_in_explorer')}
                                    </button>
                                </div>

                                {#if !stats?.recent_sightings?.[0]}
                                    <p class="text-xs text-amber-700 dark:text-amber-300 mt-2 italic">
                                        {$_('detection.review_in_explorer_hint')}
                                    </p>
                                {/if}
                            </div>
                        </div>
                    </section>
                {/if}

                {#if stats}
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
                                <div class="absolute bottom-4 right-4">
                                    {#if info.source_url}
                                        <a
                                            href={info.source_url}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            class="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-white/70 text-slate-600 text-[10px] font-black uppercase tracking-widest backdrop-blur-sm border border-white/60"
                                        >
                                            {info.source || 'Source'}
                                        </a>
                                    {/if}
                                </div>
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
                {/if}

                <!-- Species Description -->
                {#if info}
                    <section class="relative overflow-hidden rounded-2xl border border-slate-200/70 dark:border-slate-600/40 bg-white/70 dark:bg-slate-800/60 p-5 shadow-sm">
                        <div class="absolute inset-0 pointer-events-none bg-gradient-to-br from-teal-500/10 via-transparent to-brand-500/10"></div>
                        <div class="relative flex items-start gap-3">
                            <div class="w-8 h-8 rounded-full bg-slate-100 dark:bg-slate-700 flex items-center justify-center flex-shrink-0 shadow-inner">
                                <svg class="w-5 h-5 text-slate-500 dark:text-slate-400" fill="currentColor" viewBox="0 0 24 24">
                                    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 17h-2v-2h2v2zm2.07-7.75l-.9.92C13.45 12.9 13 13.5 13 15h-2v-.5c0-1.1.45-2.1 1.17-2.83l1.24-1.26c.37-.36.59-.86.59-1.41 0-1.1-.9-2-2-2s-2 .9-2 2H8c0-2.21 1.79-4 4-4s4 1.79 4 4c0 .88-.36 1.68-.93 2.25z"/>
                                </svg>
                            </div>
                            <div class="flex-1 min-w-0">
                                <div class="flex flex-wrap items-center justify-between gap-2 mb-2">
                                    <h4 class="text-xs font-black uppercase tracking-[0.2em] text-slate-500">{$_('actions.species_info')}</h4>
                                    {#if infoSourceChips.length}
                                        <div class="flex flex-wrap items-center gap-1.5">
                                            {#each infoSourceChips as chip}
                                                {#if chip.url}
                                                    <a
                                                        href={chip.url}
                                                        target="_blank"
                                                        rel="noopener noreferrer"
                                                        class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-white/80 dark:bg-slate-900/60 text-[10px] font-black uppercase tracking-widest text-slate-600 dark:text-slate-300 border border-slate-200/60 dark:border-slate-600/50 hover:text-teal-600 dark:hover:text-teal-300 transition-colors"
                                                    >
                                                        {chip.label}
                                                        <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                                                        </svg>
                                                    </a>
                                                {:else}
                                                    <span class="inline-flex items-center px-2 py-0.5 rounded-full bg-white/80 dark:bg-slate-900/60 text-[10px] font-black uppercase tracking-widest text-slate-600 dark:text-slate-300 border border-slate-200/60 dark:border-slate-600/50">
                                                        {chip.label}
                                                    </span>
                                                {/if}
                                            {/each}
                                        </div>
                                    {/if}
                                </div>
                                {#if info.extract}
                                    <p class="text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
                                        {info.extract}
                                    </p>
                                {:else}
                                    <p class="text-sm text-slate-500 dark:text-slate-400 italic">
                                        {$_('species_detail.no_info')}
                                    </p>
                                {/if}
                            </div>
                        </div>
                    </section>
                {/if}

                {#if !isUnknownBird && (showEbirdNearby || showEbirdNotable)}
                    <section class="grid grid-cols-1 lg:grid-cols-2 gap-4">
                        {#if showEbirdNearby}
                            <div class="rounded-2xl border border-sky-200/70 dark:border-slate-600/40 bg-sky-50/70 dark:bg-slate-800/60 p-5">
                                <div class="flex items-center justify-between gap-3 mb-3">
                                    <h4 class="text-xs font-black uppercase tracking-[0.2em] text-sky-600">Recent sightings</h4>
                                    <span class="text-[10px] font-black uppercase tracking-widest text-slate-500">{ebirdDaysBack} days · {ebirdRadius} km</span>
                                </div>
                                {#if !ebirdEnabled}
                                    <p class="text-xs text-slate-500">Enable eBird integration to show sightings.</p>
                                {:else if ebirdNearbyLoading}
                                    <div class="flex items-center gap-2 text-xs text-slate-500">
                                        <div class="w-3 h-3 border-2 border-sky-500 border-t-transparent rounded-full animate-spin"></div>
                                        Loading eBird sightings...
                                    </div>
                                {:else if ebirdNearbyError}
                                    <p class="text-xs text-rose-600">{ebirdNearbyError}</p>
                                {:else if ebirdNearby?.warning}
                                    <p class="text-xs text-amber-600">{ebirdNearby.warning}</p>
                                {:else if (ebirdNearby?.results?.length || 0) === 0}
                                    <p class="text-xs text-slate-500 italic">No recent sightings reported.</p>
                                {:else if ebirdNearby}
                                    <div class="space-y-2">
                                        {#each ebirdNearby.results.slice(0, 6) as obs}
                                            <div class="flex items-center justify-between gap-3 text-xs text-slate-600 dark:text-slate-300">
                                                <div class="min-w-0">
                                                    <p class="font-semibold truncate">{obs.location_name || 'Unknown location'}</p>
                                                    <p class="text-[10px] uppercase tracking-widest text-slate-400">{formatEbirdDate(obs.observed_at)}</p>
                                                </div>
                                                {#if obs.how_many}
                                                    <span class="text-[10px] font-black text-slate-500">x{obs.how_many}</span>
                                                {/if}
                                            </div>
                                        {/each}
                                    </div>
                                {/if}
                            </div>
                        {/if}

                        {#if showEbirdNotable}
                            <div class="rounded-2xl border border-amber-200/70 dark:border-slate-600/40 bg-amber-50/70 dark:bg-slate-800/60 p-5">
                                <div class="flex items-center justify-between gap-3 mb-3">
                                    <h4 class="text-xs font-black uppercase tracking-[0.2em] text-amber-600">Notable nearby</h4>
                                    <span class="text-[10px] font-black uppercase tracking-widest text-slate-500">eBird</span>
                                </div>
                                {#if !ebirdEnabled}
                                    <p class="text-xs text-slate-500">Enable eBird integration to show notable sightings.</p>
                                {:else if ebirdNotableLoading}
                                    <div class="flex items-center gap-2 text-xs text-slate-500">
                                        <div class="w-3 h-3 border-2 border-amber-500 border-t-transparent rounded-full animate-spin"></div>
                                        Loading notable sightings...
                                    </div>
                                {:else if ebirdNotableError}
                                    <p class="text-xs text-rose-600">{ebirdNotableError}</p>
                                {:else if (ebirdNotable?.results?.length || 0) === 0}
                                    <p class="text-xs text-slate-500 italic">No notable sightings reported.</p>
                                {:else if ebirdNotable}
                                    <div class="space-y-2">
                                        {#each ebirdNotable.results.slice(0, 6) as obs}
                                            <div class="flex items-center justify-between gap-3 text-xs text-slate-600 dark:text-slate-300">
                                                <div class="min-w-0">
                                                    <p class="font-semibold truncate">{obs.common_name || obs.scientific_name || 'Unknown species'}</p>
                                                    <p class="text-[10px] uppercase tracking-widest text-slate-400">{obs.location_name || 'Unknown location'}</p>
                                                </div>
                                                <span class="text-[10px] font-black text-slate-500">{formatEbirdDate(obs.observed_at)}</span>
                                            </div>
                                        {/each}
                                    </div>
                                {/if}
                            </div>
                        {/if}
                    </section>
                {/if}

                <!-- Quick Facts -->
                <section>
                    <h3 class="text-lg font-semibold text-slate-900 dark:text-white mb-4">{$_('common.statistics')}</h3>
                    <div class="grid grid-cols-2 sm:grid-cols-4 gap-4">
                        <div class="rounded-2xl p-4 bg-gradient-to-br from-teal-500 to-emerald-600 text-white shadow-lg">
                            <p class="text-3xl font-black">{stats.total_sightings}</p>
                            <p class="text-[11px] uppercase tracking-widest opacity-90">{$_('common.detections')}</p>
                        </div>
                        <div class="rounded-2xl p-4 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 shadow-sm">
                            <p class="text-2xl font-black text-slate-900 dark:text-white">
                                {(stats.avg_confidence * 100).toFixed(0)}%
                            </p>
                            <p class="text-[11px] uppercase tracking-widest text-slate-500">{$_('species_detail.avg_confidence')}</p>
                        </div>
                        <div class="rounded-2xl p-4 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 shadow-sm">
                            <p class="text-sm font-semibold text-slate-900 dark:text-white">
                                {formatDate(stats.first_seen)}
                            </p>
                            <p class="text-[11px] uppercase tracking-widest text-slate-500">{$_('species_detail.first_seen')}</p>
                        </div>
                        <div class="rounded-2xl p-4 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 shadow-sm">
                            <p class="text-sm font-semibold text-slate-900 dark:text-white">
                                {formatDate(stats.last_seen)}
                            </p>
                            <p class="text-[11px] uppercase tracking-widest text-slate-500">{$_('species_detail.last_seen')}</p>
                        </div>
                    </div>
                </section>

                <!-- Time Distribution Charts -->
                <section>
                    <h3 class="text-lg font-semibold text-slate-900 dark:text-white mb-4">{$_('species_detail.activity_patterns')}</h3>

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
                        <h3 class="text-lg font-semibold text-slate-900 dark:text-white mb-4">{$_('species_detail.camera_breakdown')}</h3>
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
                        <h3 class="text-lg font-semibold text-slate-900 dark:text-white mb-4">{$_('species_detail.recent_sightings')}</h3>
                        <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
                            {#each stats.recent_sightings as sighting}
                                <button
                                    type="button"
                                    class="bg-slate-100 dark:bg-slate-700 rounded-lg overflow-hidden group cursor-pointer relative text-left"
                                    aria-label="{$_('detection.play_video', { values: { species: sighting.display_name } })}"
                                    onclick={() => {
                                        selectedSighting = sighting as Detection;
                                        if (sighting.has_clip) {
                                            showVideo = true;
                                        }
                                    }}
                                >
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
                                        {#if sighting.has_clip}
                                            <!-- Play button overlay -->
                                            <div class="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-all duration-300 bg-black/20">
                                                <div class="w-12 h-12 rounded-full bg-white/90 dark:bg-slate-800/90 flex items-center justify-center shadow-lg transform scale-90 group-hover:scale-100 transition-transform duration-200">
                                                    <svg xmlns="http://www.w3.org/2000/svg" class="w-6 h-6 text-teal-600 dark:text-teal-400 ml-1" viewBox="0 0 24 24" fill="currentColor">
                                                        <path d="M8 5v14l11-7z"/>
                                                    </svg>
                                                </div>
                                            </div>
                                        {/if}
                                    </div>
                                    <div class="p-2">
                                        <p class="text-xs text-slate-600 dark:text-slate-300">
                                            {formatDate(sighting.detection_time)}
                                        </p>
                                        <p class="text-xs text-slate-500 dark:text-slate-400">
                                            {formatTime(sighting.detection_time)} - {(sighting.score * 100).toFixed(0)}%
                                        </p>
                                    </div>
                                </button>
                            {/each}
                        </div>
                    </section>
                {/if}
            {/if}
        </div>

        <!-- Footer -->
        <div class="flex justify-end p-4 border-t border-slate-200 dark:border-slate-700">
            <button
                type="button"
                onclick={onclose}
                class="px-4 py-2 text-sm font-medium text-slate-700 dark:text-slate-300
                       bg-slate-100 dark:bg-slate-700 rounded-lg
                       hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors"
            >
                {$_('common.close')}
            </button>
        </div>
    </div>
</div>

<!-- Video Player Modal -->
{#if showVideo && selectedSighting}
    <VideoPlayer
        frigateEvent={selectedSighting.frigate_event}
        onClose={() => {
            showVideo = false;
            selectedSighting = null;
        }}
    />
{/if}

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

</style>
