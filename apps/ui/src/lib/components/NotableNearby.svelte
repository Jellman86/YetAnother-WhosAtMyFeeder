<script lang="ts">
    import { _ } from 'svelte-i18n';
    import { onDestroy } from 'svelte';
    import { fetchEbirdNotable, type EbirdNotableResult } from '../api';
    import { formatDateTime } from '../utils/datetime';
    import { getErrorMessage } from '../utils/error-handling';
    import { authStore } from '../stores/auth.svelte';
    import { settingsStore } from '../stores/settings.svelte';
    import { formatDistance, resolveWeatherUnitSystem } from '../utils/weather-units';

    interface Props {
        canConfigure?: boolean;
        refreshKey?: number;
        onconfigure?: () => void;
        onselectspecies?: (species: string) => void;
    }

    let { canConfigure = false, refreshKey = 0, onconfigure, onselectspecies }: Props = $props();

    let result = $state<EbirdNotableResult | null>(null);
    let loading = $state(false);
    let loaded = $state(false);
    let error = $state<string | null>(null);
    let requestVersion = 0;

    const ebirdEnabled = $derived(
        settingsStore.settings?.ebird_enabled ?? authStore.ebirdEnabled ?? false
    );
    const enrichmentMode = $derived(
        settingsStore.settings?.enrichment_mode ?? authStore.enrichmentMode ?? 'per_enrichment'
    );
    const raritySource = $derived(
        enrichmentMode === 'single'
            ? (settingsStore.settings?.enrichment_single_provider ?? authStore.enrichmentSingleProvider ?? 'wikipedia')
            : (settingsStore.settings?.enrichment_rarity_source ?? authStore.enrichmentRaritySource ?? 'disabled')
    );
    const sourceEnabled = $derived(ebirdEnabled && raritySource === 'ebird');
    const radius = $derived(
        settingsStore.settings?.ebird_default_radius_km ?? authStore.ebirdDefaultRadiusKm ?? 25
    );
    const daysBack = $derived(settingsStore.settings?.ebird_default_days_back ?? 14);
    const weatherUnitSystem = $derived(
        resolveWeatherUnitSystem(
            settingsStore.settings?.location_weather_unit_system ?? authStore.locationWeatherUnitSystem,
            settingsStore.settings?.location_temperature_unit ?? authStore.locationTemperatureUnit
        )
    );
    const radiusLabel = $derived(
        formatDistance(radius, weatherUnitSystem, {
            metric: $_('common.unit_km', { default: 'km' }),
            imperial: $_('common.unit_mi', { default: 'mi' })
        })
    );

    async function loadNotableNearby(distKm: number, daysBack: number): Promise<void> {
        const version = ++requestVersion;
        loading = true;
        loaded = false;
        error = null;
        result = null;
        try {
            const response = await fetchEbirdNotable({ distKm, daysBack });
            if (version !== requestVersion) return;
            if (response.status === 'error') {
                error = response.message || $_('dashboard.notable_nearby.error');
                return;
            }
            result = response;
        } catch (cause) {
            if (version !== requestVersion) return;
            error = getErrorMessage(cause) || $_('dashboard.notable_nearby.error');
        } finally {
            if (version === requestVersion) {
                loading = false;
                loaded = true;
            }
        }
    }

    $effect(() => {
        // A dashboard refresh changes this key even when the search settings stay the same.
        refreshKey;
        if (!sourceEnabled) {
            requestVersion += 1;
            result = null;
            loading = false;
            loaded = false;
            error = null;
            return;
        }
        const searchRadius = radius;
        const searchDays = daysBack;
        void loadNotableNearby(searchRadius, searchDays);
    });

    onDestroy(() => {
        requestVersion += 1;
    });
</script>

<section
    class="space-y-3 border-t border-slate-200/70 pt-5 dark:border-slate-700/50"
    data-dashboard-notable-nearby
    aria-labelledby="dashboard-notable-nearby-title"
>
    <header class="flex flex-wrap items-start justify-between gap-2">
        <div>
            <h2 id="dashboard-notable-nearby-title" class="font-display text-lg font-bold text-slate-950 dark:text-white">
                {$_('dashboard.notable_nearby.title')}
            </h2>
            <p class="text-sm text-slate-500 dark:text-slate-400">
                {$_('dashboard.notable_nearby.subtitle')}
            </p>
        </div>
        {#if sourceEnabled}
            <span class="shrink-0 rounded-full border border-amber-200 px-2.5 py-1 text-xs font-semibold text-amber-800 dark:border-amber-800/60 dark:text-amber-300">
                {$_('dashboard.notable_nearby.scope', { values: { distance: radiusLabel, days: daysBack } })}
            </span>
        {/if}
    </header>

    {#if !sourceEnabled}
        <div class="flex flex-col gap-3 rounded-xl border border-dashed border-slate-200 bg-slate-50/60 px-4 py-4 sm:flex-row sm:items-center sm:justify-between dark:border-slate-700 dark:bg-slate-900/25">
            <p class="max-w-2xl text-sm text-slate-600 dark:text-slate-300">
                {$_('dashboard.notable_nearby.unavailable')}
            </p>
            {#if canConfigure}
                <button type="button" class="btn btn-secondary min-h-11 shrink-0 text-xs" onclick={() => onconfigure?.()}>
                    {$_('dashboard.notable_nearby.configure')}
                </button>
            {/if}
        </div>
    {:else if loading || !loaded}
        <div class="grid gap-2 sm:grid-cols-2" aria-label={$_('common.loading')}>
            {#each [1, 2] as item (item)}
                <div class="h-20 animate-pulse rounded-xl bg-amber-50 dark:bg-amber-950/20 motion-reduce:animate-none"></div>
            {/each}
        </div>
    {:else if error}
        <div role="alert" class="flex flex-col gap-3 rounded-xl border border-rose-200 bg-rose-50 px-4 py-4 sm:flex-row sm:items-center sm:justify-between dark:border-rose-900/60 dark:bg-rose-950/20">
            <p class="text-sm font-medium text-rose-800 dark:text-rose-300">{error}</p>
            <button type="button" class="btn btn-secondary min-h-11 shrink-0 text-xs" onclick={() => void loadNotableNearby(radius, daysBack)}>
                {$_('dashboard.notable_nearby.retry')}
            </button>
        </div>
    {:else if result && result.results.length === 0}
        <div class="rounded-xl border border-dashed border-amber-200 bg-amber-50/40 px-4 py-5 dark:border-amber-900/50 dark:bg-amber-950/10">
            <p class="text-sm font-medium text-slate-700 dark:text-slate-300">
                {$_('dashboard.notable_nearby.empty', { values: { distance: radiusLabel, days: daysBack } })}
            </p>
            <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">
                {$_('dashboard.notable_nearby.empty_hint')}
            </p>
        </div>
    {:else if result}
        <!-- One sighting in a two-column grid leaves half a row empty, which
             reads as something that failed to load rather than as the answer.
             Two or more still pair up. -->
        <ul class="grid gap-2 {result.results.length > 1 ? 'sm:grid-cols-2' : ''}">
            {#each result.results.slice(0, 4) as observation}
                {@const observationName = observation.common_name || observation.scientific_name || ''}
                <li class="min-w-0">
                    <!-- The whole sighting is the control: it opens the same
                         species card the rest of the dashboard uses. -->
                    <button
                        type="button"
                        disabled={!onselectspecies || !observationName}
                        onclick={() => observationName && onselectspecies?.(observationName)}
                        aria-label={$_('dashboard.notable_nearby.open_species', { values: { species: observationName || $_('common.unknown_species') } })}
                        class="flex w-full min-w-0 cursor-pointer items-center gap-3 rounded-xl border border-amber-100 bg-amber-50/45 p-3 text-left transition-colors hover:border-amber-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 focus-visible:ring-offset-2 disabled:cursor-default disabled:hover:border-amber-100 dark:border-amber-900/40 dark:bg-amber-950/10 dark:hover:border-amber-700/60 dark:focus-visible:ring-offset-slate-950 dark:disabled:hover:border-amber-900/40"
                    >
                    {#if observation.thumbnail_url}
                        <img
                            src={observation.thumbnail_url}
                            alt=""
                            width="48"
                            height="48"
                            loading="lazy"
                            class="h-12 w-12 shrink-0 rounded-lg object-cover"
                        />
                    {:else}
                        <span class="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300" aria-hidden="true">
                            <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7">
                                <path stroke-linecap="round" stroke-linejoin="round" d="M5 19c5.5 0 10-4.5 10-10V5l4 4-4 4M5 5v14" />
                            </svg>
                        </span>
                    {/if}
                    <div class="min-w-0">
                        <p class="truncate text-sm font-semibold text-slate-900 dark:text-white">
                            {observation.common_name || observation.scientific_name || $_('common.unknown_species')}
                        </p>
                        {#if observation.common_name && observation.scientific_name}
                            <p class="truncate text-xs italic text-slate-500 dark:text-slate-400">{observation.scientific_name}</p>
                        {/if}
                        <p class="truncate text-xs text-slate-500 dark:text-slate-400">
                            {observation.location_name || '—'} · {observation.observed_at ? formatDateTime(observation.observed_at) : '—'}
                        </p>
                    </div>
                    </button>
                </li>
            {/each}
        </ul>
    {/if}
</section>
