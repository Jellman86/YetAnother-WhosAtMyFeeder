<script lang="ts">
    import type { ComponentProps } from 'svelte';
    import { _ } from 'svelte-i18n';
    import LazyRoute from '../../LazyRoute.svelte';
    import type ConnectionSettingsView from '../ConnectionSettings.svelte';
    import { loadConnectionSettings } from './part-loaders';

    // Cameras & connection: where events come from. Holds what was the Connection tab.
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
        loadCameras
    }: ComponentProps<typeof ConnectionSettingsView> = $props();
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
        />
        {/snippet}
        </LazyRoute>
    </div>
</div>
