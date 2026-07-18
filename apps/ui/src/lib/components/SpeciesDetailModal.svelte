<script lang="ts">
    import { onMount } from 'svelte';
    import Map from './Map.svelte';
    import {
        fetchSpeciesStats,
        fetchSpeciesInfo,
        fetchEbirdNearby,
        fetchSeasonality,
        fetchSpeciesRange,
        reclassifyDetection,
        type SpeciesStats,
        type SpeciesInfo,
        type EbirdNearbyResult,
        type Detection,
        getThumbnailUrl
    } from '../api';
    import { getBirdNames } from '../naming';
    import { settingsStore } from '../stores/settings.svelte';
    import { authStore } from '../stores/auth.svelte';
    import { detectionsStore } from '../stores/detections.svelte';
    import { toastStore } from '../stores/toast.svelte';
    import SimpleBarChart from './SimpleBarChart.svelte';
    import VideoPlayer from './VideoPlayer.svelte';
    import RangeMap from './RangeMap.svelte';
    import { _, locale } from 'svelte-i18n';
    import { get } from 'svelte/store';
    import { trapFocus } from '../utils/focus-trap';
    import { toAppPath } from '../app/url-base';
    import { formatDate as formatDateValue, formatDateTime, formatTime } from '../utils/datetime';
    import { getErrorMessage } from '../utils/error-handling';

    interface Props {
        speciesName: string;
        onclose: () => void;
    }

    let { speciesName, onclose }: Props = $props();

    function getLocaleTag(localeValue: string | null | undefined) {
        if (!localeValue) return 'en';
        const base = localeValue.split(/[-_]/)[0];
        return base || 'en';
    }

    const HOUR_LABELS = $derived.by(() => {
        const localeTag = getLocaleTag($locale);
        const formatter = new Intl.DateTimeFormat(localeTag, { hour: 'numeric' });
        return Array.from({ length: 24 }, (_, i) => formatter.format(new Date(2000, 0, 1, i, 0, 0)));
    });

    const DAY_LABELS = $derived.by(() => {
        const localeTag = getLocaleTag($locale);
        const formatter = new Intl.DateTimeFormat(localeTag, { weekday: 'short' });
        const start = new Date(2000, 0, 2); // Sunday
        return Array.from({ length: 7 }, (_, i) => formatter.format(new Date(start.getTime() + i * 86400000)));
    });

    const MONTH_LABELS = $derived.by(() => {
        const localeTag = getLocaleTag($locale);
        const formatter = new Intl.DateTimeFormat(localeTag, { month: 'short' });
        return Array.from({ length: 12 }, (_, i) => formatter.format(new Date(2000, i, 1)));
    });

    let modalElement = $state<HTMLElement | null>(null);
    let stats = $state<SpeciesStats | null>(null);
    const debugUiEnabled = $derived(settingsStore.settings?.debug_ui_enabled ?? false);

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
    let seasonality = $state<{ month_counts: number[], total: number, local: boolean } | null>(null);
    let seasonalityLoading = $state(false);
    let rangeMap = $state<{ tileUrl: string; source: string | null; sourceUrl: string | null } | null>(null);
    let rangeMapLoading = $state(false);
    let rangeMapError = $state<string | null>(null);

    // Video playback state
    let showVideo = $state(false);
    let selectedSighting = $state<Detection | null>(null);

    // Reclassification state
    let reclassifying = $state(false);

    let showCommon = $state(true);
    let preferSci = $state(false);
    $effect(() => {
        showCommon = settingsStore.settings?.display_common_names ?? authStore.displayCommonNames ?? true;
        preferSci = settingsStore.settings?.scientific_name_primary ?? authStore.scientificNamePrimary ?? false;
    });

    const enrichmentModeSetting = $derived(settingsStore.settings?.enrichment_mode ?? authStore.enrichmentMode ?? 'per_enrichment');
    const enrichmentSingleProviderSetting = $derived(settingsStore.settings?.enrichment_single_provider ?? authStore.enrichmentSingleProvider ?? 'wikipedia');
    const enrichmentSummaryProvider = $derived(
        enrichmentModeSetting === 'single'
            ? enrichmentSingleProviderSetting
            : (settingsStore.settings?.enrichment_summary_source ?? authStore.enrichmentSummarySource ?? 'wikipedia')
    );
    const enrichmentSightingsProvider = $derived(
        enrichmentModeSetting === 'single'
            ? enrichmentSingleProviderSetting
            : (settingsStore.settings?.enrichment_sightings_source ?? authStore.enrichmentSightingsSource ?? 'disabled')
    );
    const enrichmentSeasonalityProvider = $derived(
        enrichmentModeSetting === 'single'
            ? enrichmentSingleProviderSetting
            : (settingsStore.settings?.enrichment_seasonality_source ?? authStore.enrichmentSeasonalitySource ?? 'disabled')
    );
    const ebirdEnabled = $derived(settingsStore.settings?.ebird_enabled ?? authStore.ebirdEnabled ?? false);
    const ebirdRadius = $derived(settingsStore.settings?.ebird_default_radius_km ?? 25);
    const ebirdDaysBack = $derived(settingsStore.settings?.ebird_default_days_back ?? 14);
    const rangeMapCenter = $derived(
        authStore.canModify && settingsStore.settings?.location_latitude && settingsStore.settings?.location_longitude
            ? [settingsStore.settings.location_latitude, settingsStore.settings.location_longitude] as [number, number]
            : null
    );
    const showEbirdNearby = $derived(
        enrichmentSightingsProvider === 'ebird' || enrichmentSeasonalityProvider === 'ebird'
    );
    const showEbirdNearbyCard = $derived(showEbirdNearby && ebirdEnabled);
    const rangeMapHeightClass = 'h-[280px] sm:h-[360px] lg:h-[420px]';
    const enrichmentLinksProviders = $derived(
        enrichmentModeSetting === 'single'
            ? [enrichmentSingleProviderSetting]
            : (settingsStore.settings?.enrichment_links_sources ?? authStore.enrichmentLinksSources ?? ['wikipedia', 'inaturalist'])
    );
    const enrichmentLinksProvidersNormalized = $derived(
        enrichmentLinksProviders.map((provider) => String(provider || '').toLowerCase())
    );
    const summaryEnabled = $derived(enrichmentSummaryProvider !== 'disabled');
    const seasonalityEnabled = $derived(enrichmentSeasonalityProvider === 'inaturalist');

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
            return getBirdNames(item, showCommon, preferSci);
        }
        if (info) {
            const item = {
                species: speciesName,
                scientific_name: info.scientific_name,
                common_name: null // info doesn't always have common name separate
            };
            return getBirdNames(item, showCommon, preferSci);
        }
        return { primary: speciesName, secondary: null };
    });

    let primaryName = $derived(naming.primary);
    let subName = $derived(naming.secondary);

    let infoSourceChips = $derived.by(() => {
        const currentInfo = info;
        if (!currentInfo) return [];
        const items: { label: string; url: string | null }[] = [];
        const push = (label: string | null, url: string | null) => {
            if (!label) return;
            const normalized = label.toLowerCase();
            
            // Always show the source of the displayed content
            const isContentSource = label === currentInfo.source || label === currentInfo.summary_source;
            
            if (!isContentSource && !enrichmentLinksProvidersNormalized.includes(normalized)) return;
            const existing = items.find((item) => item.label === label);
            if (existing) {
                if (!existing.url && url) existing.url = url;
                return;
            }
            items.push({ label, url: url || null });
        };

        push(currentInfo.source, currentInfo.source_url);
        push(currentInfo.summary_source, currentInfo.summary_source_url);

        if (items.length === 0 && currentInfo.wikipedia_url) {
            if (enrichmentLinksProvidersNormalized.includes('wikipedia')) {
                items.push({ label: 'Wikipedia', url: currentInfo.wikipedia_url });
            }
        }

        return items;
    });

    async function loadEbirdNearby(name: string, sciName?: string) {
        ebirdNearbyLoading = true;
        ebirdNearbyError = null;
        try {
            const res = await fetchEbirdNearby(name, sciName);
            if (res.status === 'error') {
                ebirdNearbyError = res.message || 'Failed to load eBird sightings';
                ebirdNearby = null;
            } else {
                ebirdNearby = res;
            }
        } catch (e) {
            ebirdNearbyError = getErrorMessage(e) || 'Failed to load eBird sightings';
        } finally {
            ebirdNearbyLoading = false;
        }
    }

    async function loadSeasonality(taxonId: number) {
        seasonalityLoading = true;
        try {
            // Use local coords if available for local context
            const lat = settingsStore.settings?.location_latitude ?? undefined;
            const lng = settingsStore.settings?.location_longitude ?? undefined;
            const res = await fetchSeasonality(taxonId, lat, lng);
            seasonality = { month_counts: res.month_counts, total: res.total_observations, local: res.local };
        } catch (e) {
            console.error('Failed to load seasonality', e);
        } finally {
            seasonalityLoading = false;
        }
    }

    async function loadRangeMap(name: string, scientificName?: string) {
        rangeMapLoading = true;
        rangeMapError = null;
        try {
            const res = await fetchSpeciesRange(name, scientificName);
            if (res.status === 'ok' && res.map_tile_url) {
                rangeMap = { tileUrl: res.map_tile_url, source: res.source ?? null, sourceUrl: res.source_url ?? null };
            } else {
                rangeMap = null;
                rangeMapError = res.message || 'Range map unavailable';
            }
        } catch (e) {
            rangeMapError = getErrorMessage(e) || 'Range map unavailable';
            rangeMap = null;
        } finally {
            rangeMapLoading = false;
        }
    }


    async function loadSpeciesDetails() {
        loading = true;
        error = null;
        stats = null;
        info = null;
        ebirdNearby = null;
        seasonality = null;
        rangeMap = null;
        rangeMapError = null;
        isUnknownBird = isUnknownLabel(speciesName);

        try {
            const statsData = await fetchSpeciesStats(isUnknownBird ? UNKNOWN_SPECIES_NAME : speciesName);
            stats = statsData;

            if (!isUnknownBird) {
                const statsTaxaId = statsData?.recent_sightings?.[0]?.taxa_id ?? null;
                if (summaryEnabled || (seasonalityEnabled && !statsTaxaId)) {
                    info = await fetchSpeciesInfo(speciesName);
                }
            }

            const sciName = info?.scientific_name || stats?.scientific_name || undefined;

            if (!isUnknownBird && ebirdEnabled && showEbirdNearby) {
                void loadEbirdNearby(speciesName, sciName);
            }

            const taxonId = info?.taxa_id || stats?.recent_sightings?.[0]?.taxa_id;
            if (seasonalityEnabled && taxonId) {
                void loadSeasonality(taxonId);
            }

            if (!isUnknownBird) {
                void loadRangeMap(speciesName, sciName);
            }
        } catch (e) {
            console.error('Failed to load species details', e);
            error = getErrorMessage(e) || 'Failed to load species details';
        } finally {
            loading = false;
        }
    }

    // Async work is kicked off separately so onMount can return a cleanup function.
    onMount(() => {
        const previousOverflow = document.body.style.overflow;
        document.body.style.overflow = 'hidden';
        void loadSpeciesDetails();

        return () => {
            document.body.style.overflow = previousOverflow;
        };
    });

    function formatDate(dateStr: string | null): string {
        if (!dateStr) return 'N/A';
        return formatDateValue(dateStr);
    }

    function formatEbirdDate(dateStr?: string | null): string {
        if (!dateStr) return '—';
        return formatDateTime(dateStr);
    }

    function handleKeydown(e: KeyboardEvent) {
        if (e.key === 'Escape') {
            onclose();
        }
    }

    function handleOpenExplorer() {
        window.location.assign(toAppPath(`/events?species=${encodeURIComponent(UNKNOWN_SPECIES_NAME)}`));
    }

    async function handleReclassify(strategy: 'snapshot' | 'video') {
        // Get the most recent sighting for reclassification
        const recentSighting = stats?.recent_sightings?.[0];
        if (!recentSighting || reclassifying) return;
        const eventId = recentSighting.frigate_event;

        reclassifying = true;
        try {
            const result = await reclassifyDetection(eventId, strategy);

            // Check if backend used a different strategy (fallback occurred)
            if (result.actual_strategy && result.actual_strategy !== strategy) {
                toastStore.warning('Video not available — snapshot used instead');
            }

            toastStore.success(`Reclassification complete: ${result.new_species} (${(result.new_score * 100).toFixed(0)}%)`);

            // Close modal after successful reclassification
            setTimeout(() => {
                onclose();
            }, 2000);
        } catch (e) {
            detectionsStore.dismissReclassification(eventId);
            console.error('Failed to reclassify', e);
            toastStore.error(`Failed to reclassify: ${getErrorMessage(e)}`);
        } finally {
            reclassifying = false;
        }
    }
</script>

<svelte:window onkeydown={handleKeydown} />

<!-- Backdrop -->
<div
    class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/65 p-0 backdrop-blur-sm sm:p-4"
    onclick={(e) => {
        if (e.target === e.currentTarget) {
            onclose();
        }
    }}
    role="presentation"
>
    <!-- Modal Container -->
    <div
        bind:this={modalElement}
        class="animate-fade-in h-[100dvh] w-full max-w-6xl overflow-hidden bg-white shadow-2xl ring-1 ring-black/5 dark:bg-slate-900 sm:h-auto sm:max-h-[92dvh] sm:rounded-3xl sm:border sm:border-white/10"
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
        tabindex="-1"
    >
        <!-- Header -->
        <header data-species-modal-header class="flex min-h-[76px] items-center justify-between gap-4 border-b border-teal-100 bg-gradient-to-r from-teal-50 via-emerald-50/70 to-white px-4 py-3 dark:border-slate-800 dark:from-teal-950/40 dark:via-emerald-950/20 dark:to-slate-900 sm:px-6">
            <div class="min-w-0">
                <h2 id="modal-title" class="truncate text-xl font-bold tracking-tight text-slate-900 dark:text-white sm:text-2xl">
                    {primaryName}
                </h2>
                {#if subName && subName !== primaryName}
                    <p class="mt-0.5 truncate text-sm italic text-slate-500 dark:text-slate-400">
                        {subName}
                    </p>
                {/if}
                {#if info?.description}
                    <p class="mt-1 hidden truncate text-sm text-slate-600 dark:text-slate-300 sm:block">{info.description}</p>
                {/if}
            </div>
            <button
                type="button"
                onclick={onclose}
                class="flex min-h-11 min-w-11 shrink-0 items-center justify-center rounded-xl text-slate-500 transition-colors hover:bg-white/80 hover:text-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500 dark:hover:bg-slate-800 dark:hover:text-white"
                aria-label={$_('shortcuts.close_modal')}
            >
                <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
            </button>
        </header>

        <!-- Content -->
        <div class="max-h-[calc(100dvh-76px)] space-y-8 overflow-y-auto p-4 sm:max-h-[calc(92dvh-76px)] sm:p-6 lg:p-8">
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
                <div class="mx-auto max-w-lg py-16 text-center" role="alert">
                    <div class="mx-auto flex h-11 w-11 items-center justify-center rounded-full bg-red-50 text-red-600 dark:bg-red-950/40 dark:text-red-300">
                        <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v3m0 4h.01M5.07 19h13.86a2 2 0 001.74-2.99L13.74 4a2 2 0 00-3.48 0L3.33 16.01A2 2 0 005.07 19z" /></svg>
                    </div>
                    <p class="mt-4 text-sm text-slate-600 dark:text-slate-300">{error}</p>
                    <button
                        type="button"
                        onclick={loadSpeciesDetails}
                        class="btn btn-secondary mt-5 min-h-11 px-4"
                    >
                        {$_('common.retry')}
                    </button>
                </div>
            {:else}
                <!-- Unknown Bird Message and Reclassify Options -->
                {#if isUnknownBird}
                    <section class="rounded-2xl border border-amber-200 bg-amber-50 p-5 dark:border-amber-800 dark:bg-amber-900/20 sm:p-6">
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
                                        class="flex min-h-11 items-center gap-2 rounded-lg bg-teal-600 px-4 py-2 font-semibold text-white shadow-sm transition-colors hover:bg-teal-700 disabled:cursor-not-allowed disabled:bg-slate-400"
                                    >
                                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                                        </svg>
                                        {reclassifying ? $_('common.testing') : $_('actions.deep_reclassify')}
                                    </button>

                                    <button
                                        onclick={() => handleReclassify('video')}
                                        disabled={reclassifying || !stats?.recent_sightings?.[0]?.has_clip || !stats?.recent_sightings?.[0]}
                                        class="flex min-h-11 items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 font-semibold text-white shadow-sm transition-colors hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-slate-400"
                                        title={!stats?.recent_sightings?.[0]?.has_clip ? $_('species_detail.video_unavailable') : ''}
                                    >
                                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                                        </svg>
                                        {reclassifying ? $_('common.testing') : $_('actions.reclassify')}
                                    </button>

                                    <button
                                        type="button"
                                        onclick={handleOpenExplorer}
                                        class="flex min-h-11 items-center gap-2 rounded-lg border border-amber-200 bg-white/80 px-4 py-2 font-semibold text-amber-800 shadow-sm transition-colors hover:border-amber-300 dark:border-amber-700 dark:bg-slate-900/40 dark:text-amber-100"
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
                    <section data-species-record-summary aria-labelledby="species-record-heading">
                        <div class="mb-3 flex items-center justify-between gap-4">
                            <h3 id="species-record-heading" class="text-base font-semibold text-slate-900 dark:text-white">{$_('common.statistics')}</h3>
                            <span class="text-xs font-medium text-teal-700 dark:text-teal-300">{$_('common.detections')}</span>
                        </div>
                        <dl class="grid grid-cols-2 overflow-hidden border-y border-slate-200 dark:border-slate-700 sm:grid-cols-4">
                            <div class="border-b border-r border-slate-200 px-3 py-4 dark:border-slate-700 sm:border-b-0 sm:px-4">
                                <dt class="text-xs font-medium text-slate-500 dark:text-slate-400">{$_('common.detections')}</dt>
                                <dd class="mt-1 text-2xl font-bold tracking-tight text-teal-700 dark:text-teal-300">{stats.total_sightings}</dd>
                            </div>
                            <div class="border-b border-slate-200 px-3 py-4 dark:border-slate-700 sm:border-b-0 sm:border-r sm:px-4">
                                <dt class="text-xs font-medium text-slate-500 dark:text-slate-400">{$_('species_detail.avg_confidence')}</dt>
                                <dd class="mt-1 text-2xl font-bold tracking-tight text-slate-900 dark:text-white">{(stats.avg_confidence * 100).toFixed(0)}%</dd>
                            </div>
                            <div class="border-r border-slate-200 px-3 py-4 dark:border-slate-700 sm:px-4">
                                <dt class="text-xs font-medium text-slate-500 dark:text-slate-400">{$_('species_detail.first_seen')}</dt>
                                <dd class="mt-1 text-sm font-semibold text-slate-800 dark:text-slate-100">{formatDate(stats.first_seen)}</dd>
                            </div>
                            <div class="px-3 py-4 sm:px-4">
                                <dt class="text-xs font-medium text-slate-500 dark:text-slate-400">{$_('species_detail.last_seen')}</dt>
                                <dd class="mt-1 text-sm font-semibold text-slate-800 dark:text-slate-100">{formatDate(stats.last_seen)}</dd>
                            </div>
                        </dl>
                    </section>

                    {#if stats.recent_sightings.length > 0}
                        <section data-species-recent-sightings aria-labelledby="recent-sightings-heading">
                            <h3 id="recent-sightings-heading" class="mb-4 text-base font-semibold text-slate-900 dark:text-white">{$_('species_detail.recent_sightings')}</h3>
                            <div class="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-5">
                                {#each stats.recent_sightings as sighting}
                                    <button
                                        type="button"
                                        class="group relative cursor-pointer overflow-hidden rounded-2xl border border-slate-200 bg-slate-50 text-left transition-colors hover:border-teal-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500 disabled:cursor-default dark:border-slate-700 dark:bg-slate-800/50 dark:hover:border-teal-700"
                                        aria-label={sighting.has_clip
                                            ? $_('detection.play_video', { values: { species: sighting.display_name } })
                                            : $_('species_detail.video_unavailable')}
                                        disabled={!sighting.has_clip}
                                        onclick={() => {
                                            selectedSighting = sighting as Detection;
                                            if (sighting.has_clip) showVideo = true;
                                        }}
                                    >
                                        <div class="relative aspect-[4/3] bg-slate-200 dark:bg-slate-700">
                                            <img
                                                src={getThumbnailUrl(sighting.frigate_event)}
                                                alt={sighting.display_name}
                                                class="h-full w-full object-cover"
                                                loading="lazy"
                                                onerror={(e) => {
                                                    const target = e.target as HTMLImageElement;
                                                    target.style.display = 'none';
                                                }}
                                            />
                                            {#if sighting.has_clip}
                                                <span class="absolute bottom-2 right-2 flex h-9 w-9 items-center justify-center rounded-full bg-white/90 text-teal-700 shadow-sm transition-transform group-hover:scale-105 group-focus-visible:scale-105 dark:bg-slate-900/90 dark:text-teal-300">
                                                    <svg class="ml-0.5 h-4 w-4" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M8 5v14l11-7z" /></svg>
                                                </span>
                                            {/if}
                                        </div>
                                        <div class="px-3 py-2.5">
                                            <p class="text-xs font-medium text-slate-700 dark:text-slate-200">{formatDate(sighting.detection_time)}</p>
                                            <p class="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{formatTime(sighting.detection_time)} · {(sighting.score * 100).toFixed(0)}%</p>
                                        </div>
                                    </button>
                                {/each}
                            </div>
                        </section>
                    {/if}
                {/if}

                {#if summaryEnabled && stats}
                    <!-- Hero Image from Wikipedia -->
                    {#if info?.thumbnail_url}
                        <section class="relative overflow-hidden rounded-2xl bg-slate-100 dark:bg-slate-800">
                            <div class="relative h-56 sm:h-72">
                                <img
                                    src={info.thumbnail_url}
                                    alt={primaryName}
                                    class="block h-full w-full object-cover object-center"
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
                                            class="inline-flex items-center gap-2 rounded-full border border-white/60 bg-white/85 px-2.5 py-1 text-xs font-semibold text-slate-700 backdrop-blur-sm"
                                        >
                                            {info.source || $_('common.source')}
                                        </a>
                                    {/if}
                                </div>
                            </div>
                        </section>
                    {/if}
                {/if}

                <!-- Species Description -->
                {#if summaryEnabled && info}
                    <section data-species-reference class="border-t border-slate-200 pt-8 dark:border-slate-700">
                        <div class="mb-4 flex items-center justify-between gap-3">
                            <div class="flex items-center gap-2">
                                <div class="rounded-lg bg-teal-500/10 p-1.5 text-teal-600 dark:text-teal-400">
                                    <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                                        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 17h-2v-2h2v2zm2.07-7.75l-.9.92C13.45 12.9 13 13.5 13 15h-2v-.5c0-1.1.45-2.1 1.17-2.83l1.24-1.26c.37-.36.59-.86.59-1.41 0-1.1-.9-2-2-2s-2 .9-2 2H8c0-2.21 1.79-4 4-4s4 1.79 4 4c0 .88-.36 1.68-.93 2.25z"/>
                                    </svg>
                                </div>
                                <h3 class="text-base font-semibold text-slate-900 dark:text-white">{$_('actions.species_info')}</h3>
                            </div>
                            
                            {#if infoSourceChips.length}
                                <div class="flex flex-wrap items-center gap-1.5">
                                    {#each infoSourceChips as chip}
                                        {#if chip.url}
                                            <a
                                                href={chip.url}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                class="badge border-slate-200/80 bg-white/90 text-slate-500 shadow-sm transition-colors hover:border-teal-500/40 hover:text-teal-600 dark:border-slate-700/60 dark:bg-slate-800/80 dark:hover:text-teal-400"
                                            >
                                                {chip.label}
                                                <svg class="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                                                </svg>
                                            </a>
                                        {:else}
                                            <span class="badge bg-white/90 dark:bg-slate-800/80 border-slate-200/80 dark:border-slate-700/60 text-slate-500">
                                                {chip.label}
                                            </span>
                                        {/if}
                                    {/each}
                                </div>
                            {/if}
                        </div>

                        {#if info.extract}
                            <p class="max-w-3xl text-sm leading-7 text-slate-600 dark:text-slate-300">{info.extract}</p>
                        {:else}
                            <p class="text-sm italic text-slate-500 dark:text-slate-400">{$_('species_detail.no_info')}</p>
                        {/if}
                    </section>
                {/if}

                {#if !isUnknownBird && (showEbirdNearby || seasonality || rangeMap || rangeMapLoading || rangeMapError)}
                    {#if showEbirdNearby && !ebirdEnabled}
                        <div class="border-l-2 border-sky-300 bg-sky-50/60 px-4 py-3 dark:border-sky-700 dark:bg-sky-950/20">
                            <div class="flex items-start gap-3">
                                <div class="p-2 rounded-xl bg-sky-500/10 text-sky-600 dark:text-sky-400">
                                    <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                                    </svg>
                                </div>
                                <div>
                                    <p class="text-xs font-bold uppercase tracking-widest text-sky-600 dark:text-sky-400">{$_('species_detail.ebird_disabled_title')}</p>
                                    <p class="text-xs text-slate-500 dark:text-slate-400 mt-1">{$_('species_detail.ebird_disabled_body')}</p>
                                </div>
                            </div>
                        </div>
                    {/if}
                    <section data-species-wild-context class={`grid grid-cols-1 ${showEbirdNearbyCard ? 'lg:grid-cols-2' : 'lg:grid-cols-1'} items-start gap-8 border-t border-slate-200 pt-8 dark:border-slate-700`}>
                        {#if showEbirdNearbyCard}
                            <div>
                                <div class="flex items-center justify-between gap-3 mb-4">
                                    <div class="flex items-center gap-2">
                                        <div class="p-1.5 rounded-lg bg-sky-500/10 text-sky-600 dark:text-sky-400">
                                            <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                                            </svg>
                                        </div>
                                        <div class="flex flex-col">
                                        <h3 class="text-sm font-semibold text-slate-900 dark:text-white">eBird · {$_('species_detail.recent_sightings')}</h3>
                                            <div class="flex items-center gap-1.5 mt-0.5">
                                                <span class="text-xs font-medium text-slate-500 dark:text-slate-400">{ebirdRadius}km · {ebirdDaysBack}d</span>
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                {#if ebirdNearbyLoading}
                                    <div class="space-y-3">
                                        {#each [1, 2, 3] as _}
                                            <div class="flex justify-between gap-4">
                                                <div class="h-3 w-2/3 bg-sky-100 dark:bg-sky-900/30 rounded animate-pulse"></div>
                                                <div class="h-3 w-1/4 bg-sky-100 dark:bg-sky-900/30 rounded animate-pulse"></div>
                                            </div>
                                        {/each}
                                    </div>
                                {:else if ebirdNearbyError}
                                    <div class="flex items-center gap-2 p-3 rounded-xl bg-rose-50 dark:bg-rose-900/20 text-rose-600 dark:text-rose-400 border border-rose-100 dark:border-rose-800/30">
                                        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                                        <p class="text-xs font-semibold">{ebirdNearbyError}</p>
                                    </div>
                                {:else if ebirdNearby}
                                    {#if ebirdNearby.warning}
                                        <p class="text-xs text-amber-600 mb-2">{ebirdNearby.warning}</p>
                                    {/if}
                                    {#if (ebirdNearby?.results?.length || 0) === 0}
                                        <div class="text-center py-6">
                                            <p class="text-sm text-slate-400 font-medium">{$_('species_detail.no_recent_sightings')}</p>
                                        </div>
                                    {:else}
                                        {#if ebirdNearby.results.some(r => r.lat && r.lng)}
                                            <div class="h-48 mb-4 rounded-xl overflow-hidden border border-sky-100 dark:border-sky-900/30 shadow-sm relative z-0">
                                                <Map
                                                    markers={ebirdNearby.results
                                                        .filter(r => r.lat && r.lng)
                                                        .map(r => ({
                                                            lat: r.lat!,
                                                            lng: r.lng!,
                                                            title: r.location_name || 'Unknown Location',
                                                            popupText: (() => {
                                                                const t = get(_);
                                                                const countLabel = t('species_detail.count_label', { default: 'Count' });
                                                                return `<div class="font-sans"><p class="font-bold text-sm mb-1">${r.location_name}</p><p class="text-xs opacity-75">${formatEbirdDate(r.observed_at)}</p><p class="text-xs font-bold mt-1">${countLabel}: ${r.how_many ?? '?'}</p></div>`;
                                                            })()
                                                        }))}
                                                    userLocation={authStore.canModify && settingsStore.settings?.location_latitude && settingsStore.settings?.location_longitude ? [settingsStore.settings.location_latitude, settingsStore.settings.location_longitude] : null}
                                                    zoom={10}
                                                    obfuscate={!authStore.canModify}
                                                />
                                            </div>
                                        {/if}
                                        <div class="space-y-2">
                                            {#each ebirdNearby.results.slice(0, 6) as obs}
                                                <div class="flex items-start justify-between gap-3 p-2.5 rounded-xl bg-white/60 dark:bg-slate-900/40 border border-sky-100 dark:border-sky-900/30 hover:border-sky-300 dark:hover:border-sky-700/50 transition-colors">
                                                    <div class="min-w-0">
                                                        <p class="text-xs font-bold text-slate-700 dark:text-slate-200 truncate">{obs.location_name || $_('common.unknown_location')}</p>
                                                        <div class="flex items-center gap-2 mt-0.5">
                                                            <p class="text-xs font-medium text-slate-400">{formatEbirdDate(obs.observed_at)}</p>
                                                            {#if obs.obs_valid}
                                                                <span class="w-1 h-1 rounded-full bg-emerald-400" title="{$_('species_detail.valid_observation')}"></span>
                                                            {/if}
                                                        </div>
                                                    </div>
                                                    {#if obs.how_many}
                                                        <span class="flex-shrink-0 rounded-lg bg-sky-100 px-2 py-1 text-xs font-bold text-sky-700 dark:bg-sky-900/40 dark:text-sky-300">
                                                            x{obs.how_many}
                                                        </span>
                                                    {/if}
                                                </div>
                                            {/each}
                                        </div>
                                    {/if}
                                {/if}
                            </div>
                        {/if}

                        <div class="flex h-full flex-col gap-8">
                            {#if seasonality}
                                <div class="border-b border-slate-200 pb-8 dark:border-slate-700 lg:flex lg:flex-1 lg:flex-col">
                                    <div class="flex items-center gap-2 mb-3">
                                        <div class="p-1.5 rounded-lg bg-indigo-500/10 text-indigo-600 dark:text-indigo-400">
                                            <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                                            </svg>
                                        </div>
                                        <div>
                                            <h3 class="text-sm font-semibold text-slate-900 dark:text-white">
                                                {seasonality.local ? $_('species_detail.seasonality_local') : $_('species_detail.seasonality_global')}
                                            </h3>
                                            <p class="text-xs font-medium text-slate-500 dark:text-slate-400">{$_('species_detail.inat_observations')}</p>
                                        </div>
                                    </div>
                                    <div class="h-[140px] sm:h-[160px] lg:flex-1">
                                        <SimpleBarChart
                                            data={seasonality.month_counts}
                                            labels={MONTH_LABELS}
                                            title=""
                                            ariaLabel={seasonality.local ? $_('species_detail.seasonality_local') : $_('species_detail.seasonality_global')}
                                            showEveryNthLabel={2}
                                        />
                                    </div>
                                </div>
                            {/if}

                            {#if rangeMapLoading || rangeMap || rangeMapError}
                                <div class="lg:flex lg:flex-1 lg:flex-col">
                                    <div class="relative flex items-center justify-between gap-3 mb-3">
                                        <div class="flex items-center gap-2">
                                            <div class="p-1.5 rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
                                                <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v18m9-9H3" />
                                                </svg>
                                            </div>
                                            <h3 class="text-sm font-semibold text-slate-900 dark:text-white">{$_('species_detail.range_map')}</h3>
                                        </div>
                                        {#if rangeMap?.source}
                                            {#if rangeMap.sourceUrl}
                                                <a
                                                    href={rangeMap.sourceUrl}
                                                    target="_blank"
                                                    rel="noopener noreferrer"
                                                    class="flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-2 py-1 text-xs font-semibold text-slate-500 shadow-sm transition-colors hover:border-emerald-500/30 hover:text-emerald-600 dark:border-slate-700 dark:bg-slate-800 dark:hover:text-emerald-400"
                                                >
                                                    {rangeMap.source}
                                                    <svg class="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                                                    </svg>
                                                </a>
                                            {:else}
                                                <span class="flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-2 py-1 text-xs font-semibold text-slate-500 dark:border-slate-700 dark:bg-slate-800">
                                                    {rangeMap.source}
                                                </span>
                                            {/if}
                                        {/if}
                                    </div>

                                    {#if rangeMapLoading}
                                        <div class="flex-1 min-h-[140px] rounded-2xl bg-slate-100 dark:bg-slate-800/60 animate-pulse"></div>
                                    {:else if rangeMap?.tileUrl}
                                        {#if rangeMapCenter}
                                            <RangeMap tileUrl={rangeMap.tileUrl} heightClass={rangeMapHeightClass} center={rangeMapCenter} zoom={2} />
                                        {:else}
                                            <RangeMap tileUrl={rangeMap.tileUrl} heightClass={rangeMapHeightClass} />
                                        {/if}
                                        <p class="mt-2 text-xs text-slate-500 dark:text-slate-400">{$_('species_detail.range_map_hint')}</p>
                                    {:else}
                                        <p class="text-xs text-slate-500 italic">{rangeMapError || $_('species_detail.range_unavailable')}</p>
                                    {/if}
                                </div>
                            {/if}
                        </div>
                    </section>
                {/if}

                {#if stats}
                <!-- Time Distribution Charts -->
                <section data-species-activity class="border-t border-slate-200 pt-8 dark:border-slate-700">
                    <h3 class="mb-4 text-base font-semibold text-slate-900 dark:text-white">{$_('species_detail.activity_patterns')}</h3>

                    <!-- Hourly chart - full width for better visibility -->
                    <div class="mb-6 border-b border-slate-200 pb-6 dark:border-slate-700">
                        <div class="mb-3 flex items-center gap-2">
                            <div class="p-1.5 rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
                                <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                                </svg>
                            </div>
                            <h4 class="text-sm font-semibold text-slate-800 dark:text-slate-100">{$_('species_detail.time_of_day')}</h4>
                        </div>
                        <div>
                            <SimpleBarChart
                                data={stats.hourly_distribution}
                                labels={HOUR_LABELS}
                                title=""
                                ariaLabel={$_('species_detail.time_of_day')}
                                showEveryNthLabel={6}
                            />
                        </div>
                    </div>

                    <!-- Weekly and Monthly side by side -->
                    <div class="grid grid-cols-1 gap-8 sm:grid-cols-2">
                        <div class="min-w-0">
                            <div class="mb-3 flex items-center gap-2">
                                <div class="p-1.5 rounded-lg bg-sky-500/10 text-sky-600 dark:text-sky-400">
                                    <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 9h18M9 21V9m6 12V9M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                                    </svg>
                                </div>
                                <h4 class="text-sm font-semibold text-slate-800 dark:text-slate-100">{$_('species_detail.day_of_week')}</h4>
                            </div>
                            <div>
                                <SimpleBarChart
                                    data={stats.daily_distribution}
                                    labels={DAY_LABELS}
                                    title=""
                                    ariaLabel={$_('species_detail.day_of_week')}
                                />
                            </div>
                        </div>
                        <div class="min-w-0 border-t border-slate-200 pt-6 dark:border-slate-700 sm:border-l sm:border-t-0 sm:pl-8 sm:pt-0">
                            <div class="mb-3 flex items-center gap-2">
                                <div class="p-1.5 rounded-lg bg-amber-500/10 text-amber-600 dark:text-amber-400">
                                    <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                                    </svg>
                                </div>
                                <h4 class="text-sm font-semibold text-slate-800 dark:text-slate-100">{$_('species_detail.month')}</h4>
                            </div>
                            <div>
                                <SimpleBarChart
                                    data={stats.monthly_distribution}
                                    labels={MONTH_LABELS}
                                    title=""
                                    ariaLabel={$_('species_detail.month')}
                                />
                            </div>
                        </div>
                    </div>
                </section>

                <!-- Camera Breakdown -->
                {#if stats.cameras.length > 0}
                    <section class="border-t border-slate-200 pt-8 dark:border-slate-700">
                        <h3 class="mb-4 text-base font-semibold text-slate-900 dark:text-white">{$_('species_detail.camera_breakdown')}</h3>
                        <div class="space-y-3">
                            {#each stats.cameras as camera}
                                <div class="grid grid-cols-[minmax(5rem,9rem)_minmax(0,1fr)_5rem] items-center gap-3">
                                    <span class="truncate text-sm font-medium text-slate-700 dark:text-slate-300" title={camera.camera_name}>
                                        {camera.camera_name}
                                    </span>
                                    <div class="h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
                                        <div
                                            class="h-full rounded-full bg-teal-500 transition-all duration-500"
                                            style="width: {camera.percentage}%"
                                        ></div>
                                    </div>
                                    <span class="text-right text-sm tabular-nums text-slate-500 dark:text-slate-400">
                                        {camera.count} ({camera.percentage.toFixed(0)}%)
                                    </span>
                                </div>
                            {/each}
                        </div>
                    </section>
                {/if}

                {/if}
            {/if}
        </div>

    </div>
</div>

<!-- Video Player Modal -->
{#if showVideo && selectedSighting}
    <VideoPlayer
        frigateEvent={selectedSighting.frigate_event}
        playIntent="user"
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

    @media (prefers-reduced-motion: reduce) {
        .animate-fade-in {
            animation: none;
        }
    }

</style>
