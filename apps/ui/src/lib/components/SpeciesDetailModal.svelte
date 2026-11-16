<script lang="ts">
    import DialogCloseButton from './DialogCloseButton.svelte';
    import { onMount, untrack } from 'svelte';
    import Map from './Map.svelte';
    import TaxonomyLineage from './TaxonomyLineage.svelte';
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
        getThumbnailUrl,
        ApiRequestError
    } from '../api';
    import { birdNames } from '../naming';
    import { settingsStore } from '../stores/settings.svelte';
    import { publicSettingsStore } from '../stores/public_settings.svelte';
    import { authStore } from '../stores/auth.svelte';
    import { createObservationProjectionLoader } from '../app/observation-projection-loader';
    import { detectionsStore } from '../stores/detections.svelte';
    import { toastStore } from '../stores/toast.svelte';
    import SimpleBarChart from './SimpleBarChart.svelte';
    import RangeMap from './RangeMap.svelte';
    import { _, locale } from 'svelte-i18n';
    import { get } from 'svelte/store';
    import { trapFocus } from '../utils/focus-trap';
    import { toAppPath } from '../app/url-base';
    import { formatDate as formatDateValue, formatDateTime, formatHour, formatTime } from '../utils/datetime';
    import { getErrorMessage } from '../utils/error-handling';
    import { formatDistance, resolveWeatherUnitSystem } from '../utils/weather-units';

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

    // The app's own clock, not the language's: an axis reading "5 PM" contradicted every 17:26 beside it.
    const HOUR_LABELS = $derived(Array.from({ length: 24 }, (_, hour) => formatHour(hour, 'axis')));

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
    // The name this feeder's records carry first, as the catalogue resolves those; the reference
    // source's spelling only when no record holds one.
    const lineageName = $derived(stats?.scientific_name || info?.scientific_name || null);
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
    const ebirdRadius = $derived(
        settingsStore.settings?.ebird_default_radius_km ?? authStore.ebirdDefaultRadiusKm ?? 25
    );
    const ebirdDaysBack = $derived(
        settingsStore.settings?.ebird_default_days_back ?? publicSettingsStore.settings?.ebird_default_days_back ?? 14
    );
    const ebirdWeatherUnitSystem = $derived(
        resolveWeatherUnitSystem(
            settingsStore.settings?.location_weather_unit_system ?? authStore.locationWeatherUnitSystem,
            settingsStore.settings?.location_temperature_unit ?? authStore.locationTemperatureUnit
        )
    );
    const ebirdRadiusLabel = $derived(
        formatDistance(ebirdRadius, ebirdWeatherUnitSystem, {
            metric: $_('common.unit_km', { default: 'km' }),
            imperial: $_('common.unit_mi', { default: 'mi' })
        })
    );
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
            return $birdNames(item, showCommon, preferSci);
        }
        if (info) {
            const item = {
                species: speciesName,
                scientific_name: info.scientific_name,
                common_name: null // info doesn't always have common name separate
            };
            return $birdNames(item, showCommon, preferSci);
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


    let destroyed = false;
    let observedLocalRecord = false;
    let statsPending = false;
    const statsLoader = createObservationProjectionLoader<SpeciesStats | null>({
        fetch: async () => {
            try {
                return await fetchSpeciesStats(isUnknownLabel(speciesName) ? UNKNOWN_SPECIES_NAME : speciesName);
            } catch (e) {
                // Catalogue-only species can legitimately have no local record.
                if (e instanceof ApiRequestError && e.status === 404) return null;
                throw e;
            }
        },
        apply: (value) => { stats = value; observedLocalRecord = Boolean(value && value.total_sightings > 0); },
        clear: () => { stats = null; },
        fail: (e) => {
            stats = null;
            error = getErrorMessage(e) || 'Failed to load species details';
        },
        settled: () => { statsPending = false; }
    });

    let handledPublicHistoryVersion = detectionsStore.publicHistoryVersion;
    $effect(() => {
        const version = detectionsStore.publicHistoryVersion;
        if (version <= handledPublicHistoryVersion || !authStore.isGuest) return;
        handledPublicHistoryVersion = version;
        untrack(() => {
            if (!observedLocalRecord && !statsPending) return;
            const hadLocalRecord = observedLocalRecord;
            statsLoader.invalidate();
            statsPending = true;
            void statsLoader.load().then(() => {
                if (destroyed || statsPending || version !== detectionsStore.publicHistoryVersion || !authStore.isGuest) return;
                if (!stats || stats.total_sightings <= 0) {
                    if (hadLocalRecord) onclose();
                }
            });
        });
    });

    function getCurrentStats(): SpeciesStats | null { return stats; }

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
            statsPending = true;
            await statsLoader.load();
            const currentStats = getCurrentStats();

            if (!isUnknownBird) {
                const statsTaxaId = currentStats?.recent_sightings?.[0]?.taxa_id ?? null;
                if (summaryEnabled || (seasonalityEnabled && !statsTaxaId)) {
                    info = await fetchSpeciesInfo(speciesName);
                }
            }

            const sciName = info?.scientific_name || currentStats?.scientific_name || undefined;

            if (!isUnknownBird && ebirdEnabled && showEbirdNearby) {
                void loadEbirdNearby(speciesName, sciName);
            }

            const taxonId = info?.taxa_id || currentStats?.recent_sightings?.[0]?.taxa_id;
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
            destroyed = true;
            statsLoader.dispose();
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
        if (!authStore.canModify || !recentSighting || reclassifying) return;
        const eventId = recentSighting.frigate_event;

        reclassifying = true;
        try {
            const result = await reclassifyDetection(eventId, strategy);

            if (result.status === 'queued') return;
            if (!result.updated) {
                toastStore.warning($_('notifications.reclassify_no_result'));
                return;
            }

            // Check if backend used a different strategy (fallback occurred)
            if (result.actual_strategy && result.actual_strategy !== strategy) {
                toastStore.warning($_('notifications.reclassify_fallback'));
            }

            toastStore.success(
                `${$_('notifications.event_reclassify')}: ${result.new_species} (${(result.new_score * 100).toFixed(0)}%)`
            );

            // Close modal after successful reclassification
            setTimeout(() => {
                onclose();
            }, 2000);
        } catch (e) {
            detectionsStore.dismissReclassification(eventId);
            console.error('Failed to reclassify', e);
            toastStore.error($_('notifications.reclassify_failed', { values: { message: getErrorMessage(e) } }));
        } finally {
            reclassifying = false;
        }
    }
</script>

<svelte:window onkeydown={handleKeydown} />

<!-- Backdrop -->
<div
    class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/65 p-0 backdrop-blur-xs sm:p-4"
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
        class="animate-fade-in h-dvh w-full max-w-6xl overflow-hidden bg-surface shadow-2xl ring-1 ring-black/5 sm:h-auto sm:max-h-[92dvh] sm:rounded-2xl sm:border sm:border-white/10"
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
        tabindex="-1"
    >
        <!-- Header -->
        <div data-species-modal-header class="flex min-h-[76px] items-center justify-between gap-4 border-b border-brand-100 bg-surface-raised px-4 py-3 dark:border-slate-800 sm:px-6">
            <div class="min-w-0">
                <h2 id="modal-title" class="truncate text-xl font-bold tracking-tight text-slate-900 dark:text-white sm:text-2xl">
                    {primaryName}
                </h2>
                {#if subName && subName !== primaryName}
                    <p class="mt-0.5 truncate text-sm italic text-slate-600 dark:text-slate-400">
                        {subName}
                    </p>
                {/if}
            </div>
            <DialogCloseButton onclick={onclose} />
        </div>

        <!-- Content -->
        <div class="max-h-[calc(100dvh-76px)] space-y-8 overflow-y-auto p-4 sm:max-h-[calc(92dvh-76px)] sm:p-6 lg:p-8">
            {#if loading}
                <!-- Loading Skeleton -->
                <div class="space-y-6 animate-pulse">
                    <div class="flex gap-4">
                        <div class="w-32 h-32 bg-slate-200 dark:bg-slate-700 rounded-lg"></div>
                        <div class="flex-1 space-y-3">
                            <div class="h-4 bg-slate-200 dark:bg-slate-700 rounded-sm w-3/4"></div>
                            <div class="h-4 bg-slate-200 dark:bg-slate-700 rounded-sm w-full"></div>
                            <div class="h-4 bg-slate-200 dark:bg-slate-700 rounded-sm w-5/6"></div>
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
                    <section class="rounded-2xl border border-attention-200 bg-attention-50 p-5 dark:border-attention-800 dark:bg-attention-900/20 sm:p-6">
                        <div class="flex items-start gap-4">
                            <!-- Icon -->
                            <div class="shrink-0 w-12 h-12 rounded-full bg-attention-500 flex items-center justify-center">
                                <span class="text-2xl text-white">?</span>
                            </div>

                            <!-- Content -->
                            <div class="flex-1">
                                <h3 class="text-xl font-bold text-attention-900 dark:text-attention-100 mb-2">
                                    {$_('leaderboard.needs_review')}
                                </h3>
                                <p class="text-sm text-attention-800 dark:text-attention-200 mb-4">
                                    {$_('leaderboard.unidentified_desc')}
                                </p>

                                <!-- Reclassify Buttons -->
                                <div class="flex flex-wrap gap-3">
                                    {#if authStore.canModify}
                                        <button
                                            onclick={() => handleReclassify('snapshot')}
                                            disabled={reclassifying || !stats?.recent_sightings?.[0]}
                                            class="flex min-h-11 items-center gap-2 rounded-lg bg-brand-700 px-4 py-2 font-semibold text-white shadow-xs transition-colors hover:bg-brand-800 disabled:cursor-not-allowed disabled:bg-slate-400"
                                        >
                                            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                                            </svg>
                                            {reclassifying ? $_('common.working') : $_('actions.deep_reclassify')}
                                        </button>

                                        <button
                                            onclick={() => handleReclassify('video')}
                                            disabled={reclassifying || !stats?.recent_sightings?.[0]?.has_clip || !stats?.recent_sightings?.[0]}
                                            class="flex min-h-11 items-center gap-2 rounded-lg bg-brand-700 px-4 py-2 font-semibold text-white shadow-xs transition-colors hover:bg-brand-800 disabled:cursor-not-allowed disabled:bg-slate-400"
                                            title={!stats?.recent_sightings?.[0]?.has_clip ? $_('species_detail.video_unavailable') : ''}
                                        >
                                            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                                            </svg>
                                            {reclassifying ? $_('common.working') : $_('species_detail.reclassify_clip')}
                                        </button>
                                    {/if}

                                    <button
                                        type="button"
                                        onclick={handleOpenExplorer}
                                        class="flex min-h-11 items-center gap-2 rounded-lg border border-attention-200 bg-white/80 px-4 py-2 font-semibold text-attention-800 shadow-xs transition-colors hover:border-attention-300 dark:border-attention-700 dark:bg-slate-900/40 dark:text-attention-100"
                                    >
                                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 10h16M4 14h16M4 18h16" />
                                        </svg>
                                        {$_('detection.review_in_explorer')}
                                    </button>
                                </div>

                                {#if !stats?.recent_sightings?.[0]}
                                    <p class="text-xs text-attention-700 dark:text-attention-300 mt-2 italic">
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
                            <div class="flex items-center gap-2.5">
                                <h3 id="species-record-heading" class="text-base font-semibold text-slate-900 dark:text-white">{$_('common.statistics')}</h3>
                            </div>
                        </div>
                        <dl class="grid grid-cols-2 overflow-hidden border-y border-slate-200 dark:border-slate-700 sm:grid-cols-4">
                            <div class="border-b border-r border-slate-200 px-3 py-4 dark:border-slate-700 sm:border-b-0 sm:px-4">
                                <!-- The unit and the window are both named: this is every identified frame, not the
                                     Leaderboard's visits in a chosen period, and a guest sees only the shared history. -->
                                <dt class="text-xs font-medium text-slate-600 dark:text-slate-400" data-species-detections-label>
                                    {authStore.isGuest
                                        ? $_('species_detail.detections_shared', { default: 'Detections, shared history' })
                                        : $_('species_detail.detections_all_time', { default: 'Detections, all time' })}
                                </dt>
                                <dd class="mt-1 text-2xl font-bold tracking-tight text-brand-700 dark:text-brand-300">{stats.total_sightings}</dd>
                            </div>
                            <div class="border-b border-slate-200 px-3 py-4 dark:border-slate-700 sm:border-b-0 sm:border-r sm:px-4">
                                <dt class="text-xs font-medium text-slate-600 dark:text-slate-400">{$_('species_detail.avg_confidence')}</dt>
                                <dd class="mt-1 text-2xl font-bold tracking-tight text-slate-900 dark:text-white">{(stats.avg_confidence * 100).toFixed(0)}%</dd>
                            </div>
                            <div class="border-r border-slate-200 px-3 py-4 dark:border-slate-700 sm:px-4">
                                <dt class="text-xs font-medium text-slate-600 dark:text-slate-400">{$_('species_detail.first_seen')}</dt>
                                <dd class="mt-1 text-sm font-semibold text-slate-800 dark:text-slate-100">{formatDate(stats.first_seen)}</dd>
                            </div>
                            <div class="px-3 py-4 sm:px-4">
                                <dt class="text-xs font-medium text-slate-600 dark:text-slate-400">{$_('species_detail.last_seen')}</dt>
                                <dd class="mt-1 text-sm font-semibold text-slate-800 dark:text-slate-100">{formatDate(stats.last_seen)}</dd>
                            </div>
                        </dl>
                        <p class="mt-2 text-xs text-slate-600 dark:text-slate-400" data-species-detections-note>
                            {$_('species_detail.detections_note', { default: 'Every identified frame counts once. One visit can hold several frames, so the Leaderboard’s visit counts are lower.' })}
                        </p>
                    </section>

                    {#if stats.recent_sightings.length > 0}
                        <section data-species-recent-sightings aria-labelledby="recent-sightings-heading">
                            <div class="mb-4 flex items-center gap-2.5">
                                <h3 id="recent-sightings-heading" class="text-base font-semibold text-slate-900 dark:text-white">{$_('species_detail.recent_sightings')}</h3>
                            </div>
                            <div class="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-5">
                                {#each stats.recent_sightings as sighting}
                                    <a
                                        href={toAppPath(`/events?event=${encodeURIComponent(sighting.frigate_event)}`)}
                                        class="group relative cursor-pointer overflow-hidden rounded-2xl border border-slate-200 bg-slate-50 text-left transition-colors hover:border-brand-300 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-focus disabled:cursor-default dark:border-slate-700 dark:bg-slate-800/50 dark:hover:border-brand-700"
                                    >
                                        <div class="relative aspect-4/3 bg-slate-200 dark:bg-slate-700">
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
                                                <span class="absolute bottom-2 right-2 flex h-9 w-9 items-center justify-center rounded-full bg-white/90 text-brand-700 shadow-xs transition-transform group-hover:scale-105 group-focus-visible:scale-105 dark:bg-slate-900/90 dark:text-brand-300">
                                                    <svg class="ml-0.5 h-4 w-4" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M5 12h14m-6-6 6 6-6 6" fill="none" stroke="currentColor" stroke-width="2" /></svg>
                                                </span>
                                            {/if}
                                        </div>
                                        <div class="px-3 py-2.5">
                                            <p class="text-xs font-medium text-slate-700 dark:text-slate-200">{formatDate(sighting.detection_time)}</p>
                                            <p class="mt-0.5 text-xs text-slate-600 dark:text-slate-400">{formatTime(sighting.detection_time)} · {(sighting.score * 100).toFixed(0)}%</p>
                                        </div>
                                    </a>
                                {/each}
                            </div>
                        </section>
                    {/if}
                {:else if !isUnknownBird}
                    <section data-species-no-local-visits class="rounded-2xl border border-slate-200 bg-slate-50 p-5 dark:border-slate-700 dark:bg-slate-800/40">
                        <p class="text-sm font-semibold text-slate-800 dark:text-slate-100">
                            {$_('species_detail.no_local_visits_title', { default: 'No visits at your feeder yet' })}
                        </p>
                        <p class="mt-1 text-sm text-slate-600 dark:text-slate-300">
                            {$_('species_detail.no_local_visits_body', { default: 'Your cameras have not recorded this bird. Everything below comes from public reference sources.' })}
                        </p>
                    </section>
                {/if}

                {#if summaryEnabled}
                    <!-- Reference image: preserve the full animal rather than filling a panoramic crop. -->
                    {#if info?.thumbnail_url}
                        <section
                            data-species-hero-image
                            class="relative mx-auto aspect-4/3 w-full max-w-2xl overflow-hidden rounded-2xl bg-slate-100 shadow-xs ring-1 ring-slate-200/80 dark:bg-slate-950/40 dark:ring-slate-700"
                        >
                            <img
                                src={info.thumbnail_url}
                                alt={primaryName}
                                class="block h-full w-full object-contain"
                                onerror={(e) => {
                                    const target = e.target as HTMLImageElement;
                                    target.parentElement?.classList.add('hidden');
                                }}
                            />
                            <div class="absolute bottom-3 right-3 sm:bottom-4 sm:right-4">
                                {#if info.source_url}
                                    <a
                                        href={info.source_url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        class="inline-flex min-h-8 items-center gap-1.5 rounded-full border border-white/60 bg-white/85 px-2.5 py-1 text-xs font-semibold text-slate-700 shadow-xs backdrop-blur-xs transition-colors hover:border-brand-300 hover:text-brand-700 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-focus"
                                    >
                                        {info.source || $_('common.source')}
                                        <svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5h5m0 0v5m0-5L10 14M8 7H6a2 2 0 00-2 2v9a2 2 0 002 2h9a2 2 0 002-2v-2" />
                                        </svg>
                                    </a>
                                {/if}
                            </div>
                        </section>
                    {/if}
                {/if}

                {#if !isUnknownBird && lineageName}
                    <TaxonomyLineage scientificName={lineageName} class="border-t border-slate-200 pt-8 dark:border-slate-700" />
                {/if}

                <!-- Species Description -->
                {#if summaryEnabled && info}
                    <section data-species-reference class="border-t border-slate-200 pt-8 dark:border-slate-700">
                        <div class="mb-4 flex items-center justify-between gap-3">
                            <div class="flex items-center gap-2">
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
                                                class="badge focus-ring border-slate-200/80 bg-white/90 text-slate-600 dark:text-slate-400 shadow-xs transition-colors hover:border-brand-500/40 hover:text-brand-700 dark:border-slate-700/60 dark:bg-slate-800/80 dark:hover:text-brand-400"
                                            >
                                                {chip.label}
                                                <svg class="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                                                </svg>
                                            </a>
                                        {:else}
                                            <span class="badge bg-white/90 dark:bg-slate-800/80 border-slate-200/80 dark:border-slate-700/60 text-slate-600 dark:text-slate-400">
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
                            <p class="text-sm italic text-slate-600 dark:text-slate-400">{$_('species_detail.no_info')}</p>
                        {/if}
                    </section>
                {/if}

                {#if !isUnknownBird && (showEbirdNearby || seasonality || rangeMap || rangeMapLoading || rangeMapError)}
                    {#if showEbirdNearby && !ebirdEnabled}
                        <div class="border-l-2 border-slate-300 px-4 py-3 dark:border-slate-600">
                            <p class="text-sm font-semibold text-slate-800 dark:text-slate-100">{$_('species_detail.ebird_disabled_title')}</p>
                            <p class="text-xs text-slate-600 dark:text-slate-400 mt-1">{$_('species_detail.ebird_disabled_body')}</p>
                        </div>
                    {/if}
                    <section data-species-wild-context class={`grid grid-cols-1 ${showEbirdNearbyCard ? 'lg:grid-cols-2' : 'lg:grid-cols-1'} items-start gap-8 border-t border-slate-200 pt-8 dark:border-slate-700`}>
                        {#if showEbirdNearbyCard}
                            <div>
                                <div class="flex items-center justify-between gap-3 mb-4">
                                    <div class="flex items-center gap-2">
                                        <div class="flex flex-col">
                                        <h3 class="text-sm font-semibold text-slate-900 dark:text-white">eBird · {$_('species_detail.recent_sightings')}</h3>
                                            <div class="flex items-center gap-1.5 mt-0.5">
                                                <span class="text-xs font-medium text-slate-600 dark:text-slate-400">{ebirdRadiusLabel} · {ebirdDaysBack}d</span>
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                {#if ebirdNearbyLoading}
                                    <div class="space-y-3">
                                        {#each [1, 2, 3] as _}
                                            <div class="flex justify-between gap-4">
                                                <div class="h-3 w-2/3 bg-slate-200 dark:bg-slate-700 rounded-sm animate-pulse"></div>
                                                <div class="h-3 w-1/4 bg-slate-200 dark:bg-slate-700 rounded-sm animate-pulse"></div>
                                            </div>
                                        {/each}
                                    </div>
                                {:else if ebirdNearbyError}
                                    <div class="flex items-center gap-2 p-3 rounded-xl bg-rose-50 dark:bg-rose-900/20 text-rose-700 dark:text-rose-400 border border-rose-100 dark:border-rose-800/30">
                                        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                                        <p class="text-xs font-semibold">{ebirdNearbyError}</p>
                                    </div>
                                {:else if ebirdNearby}
                                    {#if ebirdNearby.warning}
                                        <p class="text-xs font-semibold text-attention-800 dark:text-attention-200 mb-2">{ebirdNearby.warning}</p>
                                    {/if}
                                    {#if (ebirdNearby?.results?.length || 0) === 0}
                                        <div class="text-center py-6">
                                            <p class="text-sm text-slate-600 dark:text-slate-400 font-medium">{$_('species_detail.no_recent_sightings')}</p>
                                        </div>
                                    {:else}
                                        {#if ebirdNearby.results.some(r => r.lat && r.lng)}
                                            <div class="h-48 mb-4 rounded-xl overflow-hidden border border-line-soft relative z-0">
                                                <Map
                                                    markers={ebirdNearby.results
                                                        .filter(r => r.lat && r.lng)
                                                        .map(r => ({
                                                            lat: r.lat!,
                                                            lng: r.lng!,
                                                            title: r.location_name || 'Unknown Location',
                                                            popupLines: (() => {
                                                                const t = get(_);
                                                                const countLabel = t('species_detail.count_label', { default: 'Count' });
                                                                return [formatEbirdDate(r.observed_at), `${countLabel}: ${r.how_many ?? '?'}`];
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
                                                <div class="flex items-start justify-between gap-3 p-2.5 rounded-xl bg-white/60 dark:bg-slate-900/40 border border-line-soft transition-colors">
                                                    <div class="min-w-0">
                                                        <p class="text-xs font-bold text-slate-700 dark:text-slate-200 truncate">{obs.location_name || $_('common.unknown_location')}</p>
                                                        <div class="flex items-center gap-2 mt-0.5">
                                                            <p class="text-xs font-medium text-slate-600 dark:text-slate-400">{formatEbirdDate(obs.observed_at)}</p>
                                                            {#if obs.obs_valid}
                                                                <span class="w-1 h-1 rounded-full bg-success-400" title="{$_('species_detail.valid_observation')}"></span>
                                                            {/if}
                                                        </div>
                                                    </div>
                                                    {#if obs.how_many}
                                                        <span class="shrink-0 rounded-lg bg-slate-100 px-2 py-1 text-xs font-bold text-slate-700 dark:bg-slate-800 dark:text-slate-200">
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
                                        <div>
                                            <h3 class="text-sm font-semibold text-slate-900 dark:text-white">
                                                {seasonality.local ? $_('species_detail.seasonality_local') : $_('species_detail.seasonality_global')}
                                            </h3>
                                            <p class="text-xs font-medium text-slate-600 dark:text-slate-400">{$_('species_detail.inat_observations')}</p>
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
                                            <h3 class="text-sm font-semibold text-slate-900 dark:text-white">{$_('species_detail.range_map')}</h3>
                                        </div>
                                        {#if rangeMap?.source}
                                            {#if rangeMap.sourceUrl}
                                                <a
                                                    href={rangeMap.sourceUrl}
                                                    target="_blank"
                                                    rel="noopener noreferrer"
                                                    class="flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-2 py-1 text-xs font-semibold text-slate-600 dark:text-slate-400 shadow-xs transition-colors hover:border-brand-500/40 hover:text-brand-700 dark:border-slate-700 dark:bg-slate-800 dark:hover:text-brand-300"
                                                >
                                                    {rangeMap.source}
                                                    <svg class="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                                                    </svg>
                                                </a>
                                            {:else}
                                                <span class="flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-2 py-1 text-xs font-semibold text-slate-600 dark:text-slate-400 dark:border-slate-700 dark:bg-slate-800">
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
                                        <p class="mt-2 text-xs text-slate-600 dark:text-slate-400">{$_('species_detail.range_map_hint')}</p>
                                    {:else}
                                        <p class="text-xs text-slate-600 dark:text-slate-400 italic">{rangeMapError || $_('species_detail.range_unavailable')}</p>
                                    {/if}
                                </div>
                            {/if}
                        </div>
                    </section>
                {/if}

                {#if stats}
                <!-- Time Distribution Charts -->
                <section data-species-activity class="border-t border-slate-200 pt-8 dark:border-slate-700">
                    <div class="mb-4 flex items-center gap-2.5">
                        <h3 class="text-base font-semibold text-slate-900 dark:text-white">{$_('species_detail.activity_patterns')}</h3>
                    </div>

                    <!-- Hourly chart - full width for better visibility -->
                    <div class="mb-6 border-b border-slate-200 pb-6 dark:border-slate-700">
                        <div class="mb-3 flex items-center gap-2">
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
                        <div class="mb-4 flex items-center gap-2.5">
                            <h3 class="text-base font-semibold text-slate-900 dark:text-white">{$_('species_detail.camera_breakdown')}</h3>
                        </div>
                        <div class="space-y-3">
                            {#each stats.cameras as camera}
                                <div class="grid grid-cols-[minmax(5rem,9rem)_minmax(0,1fr)_5rem] items-center gap-3">
                                    <span class="truncate text-sm font-medium text-slate-700 dark:text-slate-300" title={camera.camera_name}>
                                        {camera.camera_name}
                                    </span>
                                    <div class="h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
                                        <div
                                            class="h-full rounded-full bg-brand-500 transition-all duration-500"
                                            style="width: {camera.percentage}%"
                                        ></div>
                                    </div>
                                    <span class="text-right text-sm tabular-nums text-slate-600 dark:text-slate-400">
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
