<script lang="ts">
    import type { ComponentProps } from 'svelte';
    import { _ } from 'svelte-i18n';
    import LazyRoute from '../../LazyRoute.svelte';
    import type IntegrationSettingsView from '../IntegrationSettings.svelte';
    import type HaWeatherSettingsView from '../HaWeatherSettings.svelte';
    import type LocationSettingsView from '../LocationSettings.svelte';
    import type AuthenticationSettingsView from '../AuthenticationSettings.svelte';
    import type TelemetrySettingsView from '../TelemetrySettings.svelte';
    import type { AiDraft } from '../../../settings/ai-section';
    import type { EnrichmentDraft } from '../../../settings/enrichment-section';
    import { authStore } from '../../../stores/auth.svelte';
    import {
        loadAiSettings,
        loadAuthenticationSettings,
        loadEnrichmentSettings,
        loadHaWeatherSettings,
        loadIntegrationSettings,
        loadLocationSettings,
        loadTelemetrySettings
    } from './part-loaders';
    import SectionMore from './SectionMore.svelte';

    // Sharing & integrations: where the feeder is and who can open this install first; the services
    // YA-WAMF reads from or reports to, AI descriptions and telemetry under More options. Holds what
    // were the Integrations, AI and Security tabs.
    type Props = Omit<ComponentProps<typeof IntegrationSettingsView>, 'locationLat' | 'locationLon'>
        & ComponentProps<typeof HaWeatherSettingsView>
        & ComponentProps<typeof LocationSettingsView>
        & ComponentProps<typeof AuthenticationSettingsView>
        & ComponentProps<typeof TelemetrySettingsView>
        & {
            enrichmentDraft: EnrichmentDraft;
            onOpenEbird: () => void;
            aiDraft: AiDraft;
            onAiChange: (edit: Partial<AiDraft>) => void;
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
        locationAuto = $bindable(),
        locationLat = $bindable(),
        locationLon = $bindable(),
        locationState = $bindable(),
        locationCountry = $bindable(),
        prepareInaturalistOAuth,
        initiateInaturalistOAuth,
        disconnectInaturalistOAuth,
        refreshInaturalistStatus,
        exportEbirdCsv,
        onActionFeedback,
        savedLocation,
        authEnabled = $bindable(),
        authUsername = $bindable(),
        authHasPassword = $bindable(),
        authPassword = $bindable(),
        authPasswordConfirm = $bindable(),
        authSessionExpiryHours = $bindable(),
        trustedProxyHosts = $bindable(),
        trustedProxyHostsSuggested = $bindable(),
        newTrustedProxyHost = $bindable(),
        publicAccessEnabled = $bindable(),
        publicAccessShowCameraNames = $bindable(),
        publicAccessShowAiConversation = $bindable(),
        publicAccessAllowClipDownloads = $bindable(),
        publicAccessShowAudio = $bindable(),
        publicAccessShowSnapshots = $bindable(),
        publicAccessShowClips = $bindable(),
        publicAccessLocationPrecision = $bindable(),
        publicAccessHistoricalDaysMode = $bindable(),
        publicAccessHistoricalDays = $bindable(),
        publicAccessMediaDaysMode = $bindable(),
        publicAccessMediaHistoricalDays = $bindable(),
        publicAccessRateLimitPerMinute = $bindable(),
        publicAccessExternalBaseUrl = $bindable(),
        retentionDays,
        addTrustedProxyHost,
        removeTrustedProxyHost,
        acceptTrustedProxySuggestions,
        telemetryEnabled = $bindable(),
        telemetryHealthEnabled = $bindable(),
        telemetryInstallationId,
        telemetryPlatform,
        telemetryPayloadPreview,
        versionInfo,
        enrichmentDraft,
        onOpenEbird,
        aiDraft,
        onAiChange
    }: Props = $props();
</script>

<div class="space-y-8" data-settings-section="sharing">
    <!-- Where the feeder is, then who can open this install: what most owners set here. -->
    <div class="space-y-8" data-settings-location>
        <LazyRoute loader={loadLocationSettings} label={$_('settings.location.title')}>
        {#snippet content(LocationSettings)}
        <LocationSettings
            bind:locationAuto
            bind:locationLat
            bind:locationLon
            bind:locationState
            bind:locationCountry
            {savedLocation}
        />
        {/snippet}
        </LazyRoute>
    </div>

    <div class="space-y-8" data-settings-part="security">
        {#if authStore.httpsWarning}
            <div class="flex items-start gap-3 rounded-2xl border border-status-attention-line bg-status-attention-soft px-4 py-3 text-sm text-status-attention" data-https-warning>
                <svg xmlns="http://www.w3.org/2000/svg" class="mt-0.5 h-5 w-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                <p>
                    <strong class="font-semibold">{$_('settings.security.https_warning_title', { default: 'Passwords travel unencrypted.' })}</strong>
                    {$_('settings.security.https_warning', { default: 'Sign-in is on, but this page is served over HTTP, so passwords and sessions can be read on the network. Serve YA-WAMF over HTTPS, for example behind your reverse proxy.' })}
                </p>
            </div>
        {/if}
        <LazyRoute loader={loadAuthenticationSettings} label={$_('settings.tabs.security')}>
        {#snippet content(AuthenticationSettings)}
        <AuthenticationSettings
            bind:authEnabled
            bind:authUsername
            bind:authHasPassword
            bind:authPassword
            bind:authPasswordConfirm
            bind:authSessionExpiryHours
            bind:trustedProxyHosts
            bind:trustedProxyHostsSuggested
            bind:newTrustedProxyHost
            bind:publicAccessEnabled
            bind:publicAccessShowCameraNames
            bind:publicAccessShowAiConversation
            bind:publicAccessAllowClipDownloads
            bind:publicAccessShowAudio
            bind:publicAccessShowSnapshots
            bind:publicAccessShowClips
            bind:publicAccessLocationPrecision
            bind:publicAccessHistoricalDaysMode
            bind:publicAccessHistoricalDays
            bind:publicAccessMediaDaysMode
            bind:publicAccessMediaHistoricalDays
            bind:publicAccessRateLimitPerMinute
            bind:publicAccessExternalBaseUrl
            {retentionDays}
            {addTrustedProxyHost}
            {removeTrustedProxyHost}
            {acceptTrustedProxySuggestions}
        />
        {/snippet}
        </LazyRoute>
    </div>

    <SectionMore section="sharing" summary={$_('settings.more.sharing', { default: 'eBird, iNaturalist, BirdWeather, Home Assistant weather, species information, AI and telemetry' })}>
        <div class="space-y-8" data-settings-part="integrations">
            <LazyRoute loader={loadIntegrationSettings} label={$_('settings.tabs.integrations')}>
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
            <!-- Where species pages get their information: chosen from these integrations, so shown with them. -->
            <LazyRoute
                loader={loadEnrichmentSettings}
                label={$_('settings.enrichment.title')}
                props={{ ...enrichmentDraft, onOpenEbird }}
            />
        </div>

        <div class="space-y-8" data-settings-part="ai">
            <LazyRoute
                loader={loadAiSettings}
                label={$_('settings.tabs.ai', { default: 'AI' })}
                props={{ draft: aiDraft, onchange: onAiChange }}
            />
        </div>

        <div class="space-y-8" data-settings-telemetry>
            <!-- What leaves this install: kept with who can reach it. -->
            <LazyRoute loader={loadTelemetrySettings} label={$_('settings.telemetry.title')}>
            {#snippet content(TelemetrySettings)}
            <TelemetrySettings
                bind:telemetryEnabled
                bind:telemetryHealthEnabled
                {telemetryInstallationId}
                {telemetryPlatform}
                {telemetryPayloadPreview}
                {versionInfo}
            />
            {/snippet}
            </LazyRoute>
        </div>
    </SectionMore>
</div>
