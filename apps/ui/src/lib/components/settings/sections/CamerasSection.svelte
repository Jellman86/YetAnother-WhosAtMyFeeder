<script lang="ts">
    import type { ComponentProps } from 'svelte';
    import { _ } from 'svelte-i18n';
    import LazyRoute from '../../LazyRoute.svelte';
    import SectionMore from './SectionMore.svelte';
    import type ConnectionSettingsView from '../ConnectionSettings.svelte';
    import type LocationSettingsView from '../LocationSettings.svelte';
    import { loadConnectionSettings, loadLocationSettings } from './part-loaders';

    // Cameras & connection: where events come from and where the feeder is. First the Frigate
    // address, the MQTT broker, the cameras to watch and the feeder's location, which the weather,
    // the range filter and three integrations all read; under More options the rest of Frigate.
    type Props = Omit<ComponentProps<typeof ConnectionSettingsView>, 'region'> & ComponentProps<typeof LocationSettingsView>;

    let {
        frigateUrl = $bindable(),
        frigateIngestLabels = $bindable(),
        frigateExternalUrl = $bindable(),
        mqttServer = $bindable(),
        mqttPort = $bindable(),
        mqttAuth = $bindable(),
        mqttUsername = $bindable(),
        mqttPassword = $bindable(),
        mqttPasswordSaved = $bindable(),
        selectedCameras = $bindable(),
        gardenCameras = $bindable(),
        gardenMotionCameras = $bindable(),
        betaGardenAnimals,
        cameraRoles = $bindable(),
        nestDedupeMinutes = $bindable(),
        classificationImageSource = $bindable(),
        recordingFrameDelaySeconds = $bindable(),
        clipsEnabled = $bindable(),
        recordingClipEnabled = $bindable(),
        recordingClipBeforeSeconds = $bindable(),
        recordingClipAfterSeconds = $bindable(),
        frigateCameras,
        frigateCamerasFailed,
        recordingClipCapability,
        recordingClipCapabilityLoading,
        camerasLoading,
        loadCameras,
        locationAuto = $bindable(),
        locationLat = $bindable(),
        locationLon = $bindable(),
        locationState = $bindable(),
        locationCountry = $bindable(),
        savedLocation
    }: Props = $props();
</script>

<div class="space-y-8" data-settings-section="cameras">
    <div class="space-y-8" data-settings-part="connection">
        <LazyRoute loader={loadConnectionSettings} label={$_('settings.tabs.connection')}>
        {#snippet content(ConnectionSettings)}
        <ConnectionSettings
            bind:frigateUrl
            bind:frigateIngestLabels
            bind:frigateExternalUrl
            bind:mqttServer
            bind:mqttPort
            bind:mqttAuth
            bind:mqttUsername
            bind:mqttPassword
            bind:mqttPasswordSaved
            bind:selectedCameras
            bind:gardenCameras
            bind:gardenMotionCameras
            {betaGardenAnimals}
            bind:cameraRoles
            bind:nestDedupeMinutes
            bind:classificationImageSource
            bind:recordingFrameDelaySeconds
            bind:clipsEnabled
            bind:recordingClipEnabled
            bind:recordingClipBeforeSeconds
            bind:recordingClipAfterSeconds
            {frigateCameras}
            {frigateCamerasFailed}
            {recordingClipCapability}
            {recordingClipCapabilityLoading}
            {camerasLoading}
            {loadCameras}
            region="main"
        />
        {/snippet}
        </LazyRoute>
    </div>

    <!-- Where the feeder is: a fact about it, like its cameras, on the section Settings opens on. -->
    <div class="space-y-8" data-settings-part="location" data-settings-location>
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

    <SectionMore section="cameras" summary={$_('settings.more.cameras', { default: 'Frigate details, image source and clips' })}>
        <div class="space-y-8" data-settings-part-more="connection">
            <LazyRoute loader={loadConnectionSettings} label={$_('settings.tabs.connection')}>
            {#snippet content(ConnectionSettings)}
            <ConnectionSettings
                bind:frigateUrl
                bind:frigateIngestLabels
                bind:frigateExternalUrl
                bind:mqttServer
                bind:mqttPort
                bind:mqttAuth
                bind:mqttUsername
                bind:mqttPassword
                bind:mqttPasswordSaved
                bind:selectedCameras
                bind:gardenCameras
                bind:gardenMotionCameras
                {betaGardenAnimals}
                bind:cameraRoles
                bind:nestDedupeMinutes
                bind:classificationImageSource
                bind:recordingFrameDelaySeconds
                bind:clipsEnabled
                bind:recordingClipEnabled
                bind:recordingClipBeforeSeconds
                bind:recordingClipAfterSeconds
                {frigateCameras}
                {frigateCamerasFailed}
                {recordingClipCapability}
                {recordingClipCapabilityLoading}
                {camerasLoading}
                {loadCameras}
                region="more"
            />
            {/snippet}
            </LazyRoute>
        </div>
    </SectionMore>
</div>
