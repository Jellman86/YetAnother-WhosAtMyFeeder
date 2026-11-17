<script lang="ts">
    import { _, locale } from 'svelte-i18n';
    import { fetchEbirdNearby, fetchSpeciesInfo, type EbirdNearbyResult, type SpeciesInfo } from '../../api';
    import { authStore } from '../../stores/auth.svelte';
    import { publicSettingsStore } from '../../stores/public_settings.svelte';
    import { settingsStore } from '../../stores/settings.svelte';
    import { formatDateTime } from '../../utils/datetime';
    import { getErrorMessage } from '../../utils/error-handling';
    import { summaryInAnotherLanguage } from '../../utils/summary-language';
    import { formatDistance, type WeatherUnitSystem } from '../../utils/weather-units';
    import Map from '../Map.svelte';
    import { toAppPath } from '../../app/url-base';
    import { settingsPartPath } from '../../settings/settings-route';

    /**
     * What the record can say about the species beyond this sighting: a few lines to recognise it by,
     * with a link for the rest, and eBird's recent sightings nearby when a provider is chosen. Each is
     * fetched once per species and provider choice.
     */
    type Props = {
        speciesName: string;
        scientificName?: string | null;
        primaryName: string;
        unitSystem: WeatherUnitSystem;
        /** The fetched summary, for the reference photograph beside the identification. */
        info?: SpeciesInfo | null;
    };

    let { speciesName, scientificName, primaryName, unitSystem, info = $bindable(null) }: Props = $props();

    const mode = $derived(settingsStore.settings?.enrichment_mode ?? authStore.enrichmentMode ?? 'per_enrichment');
    const singleProvider = $derived(settingsStore.settings?.enrichment_single_provider ?? authStore.enrichmentSingleProvider ?? 'wikipedia');
    const summaryProvider = $derived(mode === 'single' ? singleProvider : (settingsStore.settings?.enrichment_summary_source ?? authStore.enrichmentSummarySource ?? 'wikipedia'));
    const sightingsProvider = $derived(mode === 'single' ? singleProvider : (settingsStore.settings?.enrichment_sightings_source ?? authStore.enrichmentSightingsSource ?? 'disabled'));
    const seasonalityProvider = $derived(mode === 'single' ? singleProvider : (settingsStore.settings?.enrichment_seasonality_source ?? authStore.enrichmentSeasonalitySource ?? 'disabled'));
    const ebirdEnabled = $derived(settingsStore.settings?.ebird_enabled ?? authStore.ebirdEnabled ?? false);
    const ebirdRadius = $derived(settingsStore.settings?.ebird_default_radius_km ?? authStore.ebirdDefaultRadiusKm ?? 25);
    const ebirdDaysBack = $derived(settingsStore.settings?.ebird_default_days_back ?? publicSettingsStore.settings?.ebird_default_days_back ?? 14);
    const showSightings = $derived(sightingsProvider === 'ebird' || seasonalityProvider === 'ebird');
    const radiusLabel = $derived(formatDistance(ebirdRadius, unitSystem, { metric: $_('common.unit_km', { default: 'km' }), imperial: $_('common.unit_mi', { default: 'mi' }) }));

    let infoLoading = $state(false);
    let infoError = $state<string | null>(null);
    let sightings = $state.raw<EbirdNearbyResult | null>(null);
    let sightingsLoading = $state(false);
    let sightingsError = $state<string | null>(null);
    let loadedFor: string | null = null;

    async function loadInfo(name: string): Promise<void> {
        infoLoading = true;
        infoError = null;
        try {
            info = await fetchSpeciesInfo(name);
        } catch (e) {
            infoError = getErrorMessage(e) || 'Failed to load species info';
        } finally {
            infoLoading = false;
        }
    }

    async function loadSightings(name: string, scientific?: string): Promise<void> {
        sightingsLoading = true;
        sightingsError = null;
        try {
            const result = await fetchEbirdNearby(name, scientific);
            if (result.status === 'error') {
                sightingsError = result.message || 'Failed to load eBird sightings';
                sightings = null;
            } else {
                sightings = result;
            }
        } catch (e) {
            sightingsError = getErrorMessage(e) || 'Failed to load eBird sightings';
        } finally {
            sightingsLoading = false;
        }
    }

    // Fetching is the outside system here: ask again only when the species or a provider choice changes.
    $effect(() => {
        const key = [speciesName, summaryProvider, sightingsProvider, seasonalityProvider, ebirdEnabled, ebirdRadius, ebirdDaysBack].join('|');
        if (key === loadedFor) return;
        loadedFor = key;
        info = null;
        infoError = null;
        sightings = null;
        sightingsError = null;
        if (summaryProvider !== 'disabled') void loadInfo(speciesName);
        if (ebirdEnabled && showSightings) void loadSightings(speciesName, scientificName ?? undefined);
    });

    const shown = $derived(infoLoading || !!info || !!infoError || showSightings);

    function observedLabel(value?: string | null): string {
        return value ? formatDateTime(value) : '—';
    }
</script>

{#if shown}
    <section data-detection-reference class="space-y-4">
        <h4 class="text-xs font-semibold text-muted">
            {$_('detection.reference_disclosure', { values: { species: primaryName }, default: 'About {species}, and nearby sightings' })}
        </h4>

        {#if summaryProvider !== 'disabled'}
            <!-- A few lines to recognise the bird by, and a link for the rest: the full article
                 belongs at its source, not in the record. -->
            <div data-detection-reference-summary>
                {#if infoLoading}
                    <div class="flex flex-col gap-2" role="status" aria-label={$_('common.loading', { default: 'Loading' })}>
                        <div class="h-3 w-3/4 rounded-sm bg-line motion-safe:animate-pulse"></div>
                        <div class="h-3 w-full rounded-sm bg-line motion-safe:animate-pulse"></div>
                        <div class="h-3 w-5/6 rounded-sm bg-line motion-safe:animate-pulse"></div>
                    </div>
                {:else if infoError}
                    <p class="text-xs text-muted" role="status">{infoError}</p>
                {:else if info}
                    {@const summaryText = info.extract || info.description}
                    {@const summaryUrl = info.summary_source_url || info.wikipedia_url || info.source_url}
                    {@const summaryLabel = info.summary_source || info.source}
                    {@const summaryLanguage = summaryInAnotherLanguage(info, $locale)}
                    {#if summaryText}
                        <!-- Only shortened when the rest can be reached. -->
                        <p class="text-sm leading-relaxed text-ink {summaryUrl ? 'line-clamp-3' : ''}" lang={summaryLanguage?.code} data-detection-reference-text>{summaryText}</p>
                        {#if summaryLanguage}
                            <p class="mt-1 text-xs text-muted" data-reference-summary-language={summaryLanguage.code}>
                                {$_('species_detail.summary_language_note', { default: 'Description from {language} Wikipedia', values: { language: summaryLanguage.name } })}
                            </p>
                        {/if}
                    {:else}
                        <p class="text-xs text-muted">{$_('species_detail.no_info')}</p>
                    {/if}
                    <div class="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
                        {#if summaryUrl}
                            <a
                                href={summaryUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                                class="inline-flex min-h-6 items-center gap-1 rounded-sm font-semibold text-accent-ink underline underline-offset-2 focus-ring"
                                data-detection-reference-link
                            >
                                {summaryLabel
                                    ? $_('detection.reference_read_more_on', { values: { source: summaryLabel }, default: 'Read more on {source}' })
                                    : $_('detection.reference_read_more', { default: 'Read more' })}
                                <svg class="h-3 w-3 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                                </svg>
                            </a>
                        {:else if summaryLabel}
                            <span>{$_('detection.reference_source', { values: { source: summaryLabel }, default: 'Source: {source}' })}</span>
                        {/if}
                        {#if info.conservation_status}
                            <span>{$_('detection.reference_conservation', { values: { status: info.conservation_status }, default: 'Conservation status: {status}' })}</span>
                        {/if}
                    </div>
                {/if}
            </div>
        {/if}

        {#if showSightings}
            <!-- Rows under one heading, not a card of cards. -->
            <div class="space-y-3" data-detection-reference-sightings>
                <div>
                    <p class="text-xs font-semibold text-strong">{$_('species_detail.recent_sightings')}</p>
                    <p class="text-xs text-muted">eBird · {radiusLabel} · {ebirdDaysBack}d</p>
                </div>

                {#if !ebirdEnabled}
                    <p class="text-xs text-muted">
                        {$_('detection.ebird_enable_sightings')}
                        <a href={toAppPath(settingsPartPath('integrations'))} class="ml-1 inline-flex min-h-6 items-center rounded-sm font-semibold text-accent-ink underline underline-offset-2 focus-ring">{$_('detection.ebird_configure_settings')}</a>
                    </p>
                {:else if sightingsLoading}
                    <div class="space-y-3" role="status" aria-label={$_('common.loading', { default: 'Loading' })}>
                        {#each [1, 2, 3] as row (row)}
                            <div class="flex justify-between gap-4">
                                <div class="h-3 w-2/3 rounded-sm bg-line motion-safe:animate-pulse"></div>
                                <div class="h-3 w-1/4 rounded-sm bg-line motion-safe:animate-pulse"></div>
                            </div>
                        {/each}
                    </div>
                {:else if sightingsError}
                    <p class="text-xs font-semibold text-status-fail" role="status">{sightingsError}</p>
                {:else if (sightings?.results?.length ?? 0) === 0}
                    <p class="text-sm text-muted">
                        {$_('detection.ebird_none_nearby')}
                        <span class="block text-xs">{$_('detection.ebird_try_radius')}</span>
                    </p>
                {:else if sightings}
                    {@const located = sightings.results.filter((sighting) => sighting.lat && sighting.lng)}
                    {#if located.length > 0}
                        <div class="relative z-0 h-48 overflow-hidden rounded-xl border border-line-soft">
                            <Map
                                markers={located.map((sighting) => ({
                                    lat: sighting.lat ?? 0,
                                    lng: sighting.lng ?? 0,
                                    title: sighting.location_name || 'Unknown Location',
                                    popupLines: [observedLabel(sighting.observed_at), `${$_('species_detail.count_label', { default: 'Count' })}: ${sighting.how_many ?? '?'}`]
                                }))}
                                userLocation={authStore.canModify && settingsStore.settings?.location_latitude && settingsStore.settings?.location_longitude ? [settingsStore.settings.location_latitude, settingsStore.settings.location_longitude] : null}
                                zoom={10}
                                obfuscate={!authStore.canModify}
                            />
                        </div>
                    {/if}
                    <ul class="divide-y divide-line-soft border-y border-line-soft">
                        {#each sightings.results.slice(0, 5) as sighting, index (index)}
                            <li class="flex items-start justify-between gap-3 py-2">
                                <div class="min-w-0">
                                    <p class="text-xs font-semibold text-ink wrap-break-word">{sighting.location_name || $_('common.unknown_location')}</p>
                                    <p class="text-xs text-muted">
                                        {observedLabel(sighting.observed_at)}{#if sighting.obs_valid}{` · ${$_('detection.ebird.valid_observation', { default: 'Valid observation' })}`}{/if}
                                    </p>
                                </div>
                                {#if sighting.how_many}
                                    <span class="shrink-0 text-xs font-semibold tabular-nums text-ink">×{sighting.how_many}</span>
                                {/if}
                            </li>
                        {/each}
                    </ul>
                {/if}
            </div>
        {/if}
    </section>
{/if}
