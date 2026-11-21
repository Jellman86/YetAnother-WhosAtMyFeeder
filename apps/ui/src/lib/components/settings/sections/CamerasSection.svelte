<script lang="ts">
    import type { ComponentProps } from 'svelte';
    import { _ } from 'svelte-i18n';
    import LazyRoute from '../../LazyRoute.svelte';
    import SectionMore from './SectionMore.svelte';
    import type ConnectionSettingsView from '../ConnectionSettings.svelte';
    import type BirdnetSettingsView from '../BirdnetSettings.svelte';
    import { loadBirdnetSettings, loadConnectionSettings } from './part-loaders';

    // Cameras & connection: where events come from. First the Frigate address, the MQTT broker and
    // the cameras to watch; under More options the rest of Frigate and the BirdNET-Go connection.
    type Props = Omit<ComponentProps<typeof ConnectionSettingsView>, 'region'> & ComponentProps<typeof BirdnetSettingsView>;

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
        availableCameras
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

    <SectionMore section="cameras" summary={$_('settings.more.cameras', { default: 'Frigate details, image source, clips and BirdNET-Go' })}>
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
        <div class="space-y-8" data-settings-part-more="birdnet">
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
    </SectionMore>
</div>
