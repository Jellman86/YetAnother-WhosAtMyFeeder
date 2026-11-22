<script lang="ts">
    import type { ComponentProps } from 'svelte';
    import { _ } from 'svelte-i18n';
    import LazyRoute from '../../LazyRoute.svelte';
    import type IntegrationSettingsView from '../IntegrationSettings.svelte';
    import type HaWeatherSettingsView from '../HaWeatherSettings.svelte';
    import type BirdnetSettingsView from '../BirdnetSettings.svelte';
    import type { AiDraft } from '../../../settings/ai-section';
    import type { EnrichmentDraft } from '../../../settings/enrichment-section';
    import { toAppPath } from '../../../app/url-base';
    import { settingsPartPath, type SettingsPart } from '../../../settings/settings-route';
    import { settingsSectionName } from '../../../settings/settings-place';
    import {
        loadAiSettings,
        loadBirdnetSettings,
        loadEnrichmentSettings,
        loadHaWeatherSettings,
        loadIntegrationSettings
    } from './part-loaders';
    import SectionMore from './SectionMore.svelte';

    // Integrations: every other service YA-WAMF reads from or reports to, one group each with its
    // own switch, state and test: BirdNET-Go, Home Assistant weather, eBird, iNaturalist,
    // BirdWeather and the AI provider. Where species pages get their information is a result of
    // these, so it is under More options. Frigate and MQTT are the pipeline itself and the feeder's
    // location is a fact about the feeder, so both are in Cameras & connection, named here in words.
    type Props = ComponentProps<typeof IntegrationSettingsView>
        & ComponentProps<typeof HaWeatherSettingsView>
        & ComponentProps<typeof BirdnetSettingsView>
        & {
            enrichmentDraft: EnrichmentDraft;
            onOpenEbird: () => void;
            aiDraft: AiDraft;
            onAiChange: (edit: Partial<AiDraft>) => void;
            /** Opens a part of another section, where Frigate, MQTT and the location are set. */
            onOpenPart: (part: SettingsPart) => void;
        };

    let {
        weatherUnitSystem,
        birdweatherEnabled = $bindable(),
        birdweatherStationToken = $bindable(),
        birdweatherStationTokenSaved = $bindable(),
        haWeatherEnabled = $bindable(),
        haWeatherBaseUrl = $bindable(),
        haWeatherAccessToken = $bindable(),
        haWeatherAccessTokenSaved = $bindable(),
        haWeatherEntity = $bindable(),
        haWeatherTemperatureEntity = $bindable(),
        haWeatherWindSpeedEntity = $bindable(),
        haWeatherWindDirectionEntity = $bindable(),
        haWeatherCloudCoverEntity = $bindable(),
        haWeatherPrecipitationEntity = $bindable(),
        haWeatherRainEntity = $bindable(),
        haWeatherSnowfallEntity = $bindable(),
        haWeatherIlluminanceEntity = $bindable(),
        ebirdEnabled = $bindable(),
        ebirdApiKey = $bindable(),
        ebirdApiKeySaved = $bindable(),
        ebirdDefaultRadiusKm = $bindable(),
        ebirdDefaultDaysBack = $bindable(),
        ebirdMaxResults = $bindable(),
        ebirdLocale = $bindable(),
        inaturalistEnabled = $bindable(),
        inaturalistClientId = $bindable(),
        inaturalistClientSecret = $bindable(),
        inaturalistClientIdSaved = $bindable(),
        inaturalistClientSecretSaved = $bindable(),
        inaturalistDefaultLat = $bindable(),
        inaturalistDefaultLon = $bindable(),
        inaturalistDefaultPlace = $bindable(),
        inaturalistConnectedUser = $bindable(),
        locationLat,
        locationLon,
        prepareInaturalistOAuth,
        initiateInaturalistOAuth,
        disconnectInaturalistOAuth,
        refreshInaturalistStatus,
        exportEbirdCsv,
        onActionFeedback,
        birdnetEnabled = $bindable(),
        birdnetUrl = $bindable(),
        birdnetExternalUrl = $bindable(),
        audioTopic = $bindable(),
        audioBufferHours = $bindable(),
        audioCorrelationWindowSeconds = $bindable(),
        cameraAudioMapping = $bindable(),
        birdnetSourceOptions,
        loadingBirdnetSources,
        birdnetSourcesError,
        availableCameras,
        enrichmentDraft,
        onOpenEbird,
        aiDraft,
        onAiChange,
        onOpenPart
    }: Props = $props();

    function openPart(event: MouseEvent, part: SettingsPart): void {
        if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        event.preventDefault();
        onOpenPart(part);
    }

    const linkClass = 'focus-ring rounded-sm text-accent-ink underline decoration-1 underline-offset-2';
</script>

<div class="space-y-8" data-settings-section="integrations">
    <!-- What is set elsewhere, in words, so an owner looking for it here is sent to it. -->
    <div class="max-w-prose space-y-1 text-sm leading-relaxed text-muted" data-settings-lead data-integrations-elsewhere>
        <p>
            {$_('settings.integrations.elsewhere_pipeline', { values: { section: settingsSectionName('cameras', $_) }, default: 'Frigate and the MQTT broker are how visits arrive, so they are set in {section}.' })}
            <a class={linkClass} href={toAppPath(settingsPartPath('connection'))} onclick={(event) => openPart(event, 'connection')}>
                {$_('settings.integrations.open_connection', { default: 'Open Frigate and MQTT' })}
            </a>
        </p>
        <p>
            {$_('settings.integrations.elsewhere_location', { values: { section: settingsSectionName('cameras', $_) }, default: 'The weather, eBird, iNaturalist and the range filter all start from your feeder\u2019s location, also set in {section}. The weather itself comes from Open-Meteo and needs no setup.' })}
            <a class={linkClass} href={toAppPath(settingsPartPath('location'))} onclick={(event) => openPart(event, 'location')}>
                {$_('settings.integrations.open_location', { default: 'Open your feeder\u2019s location' })}
            </a>
        </p>
    </div>

    <div class="space-y-8" data-settings-part="birdnet">
        <LazyRoute loader={loadBirdnetSettings} label={$_('settings.integrations.birdnet.title')}>
        {#snippet content(BirdnetSettings)}
        <BirdnetSettings
            bind:birdnetEnabled
            bind:birdnetUrl
            bind:birdnetExternalUrl
            bind:audioTopic
            bind:audioBufferHours
            bind:audioCorrelationWindowSeconds
            bind:cameraAudioMapping
            {birdnetSourceOptions}
            {loadingBirdnetSources}
            {birdnetSourcesError}
            {availableCameras}
        />
        {/snippet}
        </LazyRoute>
    </div>

    <div class="space-y-8" data-settings-part="weather">
        <LazyRoute loader={loadHaWeatherSettings} label={$_('settings.integrations.ha_weather.title', { default: 'Home Assistant weather' })}>
        {#snippet content(HaWeatherSettings)}
        <HaWeatherSettings
            bind:haWeatherEnabled
            bind:haWeatherBaseUrl
            bind:haWeatherAccessToken
            bind:haWeatherAccessTokenSaved
            bind:haWeatherEntity
            bind:haWeatherTemperatureEntity
            bind:haWeatherWindSpeedEntity
            bind:haWeatherWindDirectionEntity
            bind:haWeatherCloudCoverEntity
            bind:haWeatherPrecipitationEntity
            bind:haWeatherRainEntity
            bind:haWeatherSnowfallEntity
            bind:haWeatherIlluminanceEntity
        />
        {/snippet}
        </LazyRoute>
    </div>

    <div class="space-y-8" data-settings-part="networks">
        <LazyRoute loader={loadIntegrationSettings} label={$_('settings.tabs.networks', { default: 'eBird, iNaturalist and BirdWeather' })}>
        {#snippet content(IntegrationSettings)}
        <IntegrationSettings
            {weatherUnitSystem}
            bind:birdweatherEnabled
            bind:birdweatherStationToken
            bind:birdweatherStationTokenSaved
            bind:ebirdEnabled
            bind:ebirdApiKey
            bind:ebirdApiKeySaved
            bind:ebirdDefaultRadiusKm
            bind:ebirdDefaultDaysBack
            bind:ebirdMaxResults
            bind:ebirdLocale
            bind:inaturalistEnabled
            bind:inaturalistClientId
            bind:inaturalistClientSecret
            bind:inaturalistClientIdSaved
            bind:inaturalistClientSecretSaved
            bind:inaturalistDefaultLat
            bind:inaturalistDefaultLon
            bind:inaturalistDefaultPlace
            bind:inaturalistConnectedUser
            {locationLat}
            {locationLon}
            {prepareInaturalistOAuth}
            {initiateInaturalistOAuth}
            {disconnectInaturalistOAuth}
            {refreshInaturalistStatus}
            {exportEbirdCsv}
            {onActionFeedback}
        />
        {/snippet}
        </LazyRoute>
    </div>

    <div class="space-y-8" data-settings-part="ai">
        <LazyRoute
            loader={loadAiSettings}
            label={$_('settings.tabs.ai', { default: 'AI' })}
            props={{ draft: aiDraft, onchange: onAiChange }}
        />
    </div>

    <SectionMore section="integrations" summary={$_('settings.more.integrations', { default: 'Where species pages get their information' })}>
        <!-- Where species pages get their information: chosen from these integrations, so shown with them. -->
        <div class="space-y-8" data-settings-part="enrichment">
            <LazyRoute
                loader={loadEnrichmentSettings}
                label={$_('settings.enrichment.title')}
                props={{ ...enrichmentDraft, onOpenEbird }}
            />
        </div>
    </SectionMore>
</div>
