<script lang="ts">
    import type { ComponentProps } from 'svelte';
    import { onDestroy } from 'svelte';
    import { _ } from 'svelte-i18n';
    import LazyRoute from '../../LazyRoute.svelte';
    import type DetectionSettingsView from '../DetectionSettings.svelte';
    import type ModelSettingsView from '../ModelSettings.svelte';
    import type HardwareSettingsView from '../HardwareSettings.svelte';
    import type NamingSettingsView from '../NamingSettings.svelte';
    import type GardenBetaSettingsView from '../GardenBetaSettings.svelte';
    import DeviceCheckDialog from '../DeviceCheckDialog.svelte';
    import SectionMore from './SectionMore.svelte';
    import { DeviceCheck } from '../../../settings/device-check.svelte';
    import { formatDateTime } from '../../../utils/datetime';
    import {
        loadDetectionSettings,
        loadGardenBetaSettings,
        loadHardwareSettings,
        loadModelSettings,
        loadNamingSettings
    } from './part-loaders';

    // Identifying birds: how sure a name must be and the models that name birds come first; blocked
    // species, the range filter, video checks, the hardware and the features still in Beta are under
    // More options. Holds what were the Detection, Models and Beta features tabs. Each part's props
    // keep its component's own names.
    type Props = ComponentProps<typeof DetectionSettingsView>
        & ComponentProps<typeof NamingSettingsView>
        & Omit<ComponentProps<typeof ModelSettingsView>, 'autoVideoClassification' | 'onopenlocationsettings' | 'deviceCheck' | 'modelsListed'>
        & Omit<ComponentProps<typeof HardwareSettingsView>, 'deviceCheck' | 'classifierStatus' | 'imageExecutionMode'>
        & ComponentProps<typeof GardenBetaSettingsView>
        & {
            imageExecutionMode: string;
            videoCircuitOpen: boolean;
            videoCircuitUntil: string | null;
            videoCircuitFailures: number;
        };

    let {
        threshold = $bindable(),
        minConfidence = $bindable(),
        trustFrigateSublabel = $bindable(),
        writeFrigateSublabel = $bindable(),
        personalizedRerankEnabled = $bindable(),
        autoVideoClassification = $bindable(),
        videoClassificationDelay = $bindable(),
        videoClassificationMaxRetries = $bindable(),
        videoClassificationFrames = $bindable(),
        blockedLabels = $bindable(),
        blockedSpecies = $bindable(),
        videoCircuitOpen,
        videoCircuitUntil,
        videoCircuitFailures,
        onopenlocationsettings,
        rangeFilterEnabled = $bindable(),
        rangeFilterRegionLevel = $bindable(),
        onopenebirdsettings,
        onopenactivitylog,
        onopenmanualobservation,
        liveWorkerCount = $bindable(),
        backgroundWorkerCount = $bindable(),
        birdModelRegionOverride = $bindable(),
        birdFinder = $bindable(),
        birdFinderProvider = $bindable(),
        imageExecutionMode = $bindable(),
        inferenceProvider = $bindable(),
        strictNonFiniteOutput = $bindable(),
        debugUiEnabled,
        classifierStatus,
        onrefreshclassifierstatus,
        onopenmodelevaluation,
        enabled = $bindable(),
        cameras,
        motionCameras,
        labels = $bindable(),
        motionConfidence = $bindable(),
        notificationsEnabled = $bindable(),
        notificationsUseBirdChannels = $bindable(),
        notificationChannels = $bindable(),
        notificationsIncludePhoto = $bindable(),
        birdChannels,
        onOpenNotifications,
        onOpenLocation,
        automaticNaming = $bindable(),
        namingThreshold = $bindable(),
        domesticBirds = $bindable(),
        onNavigate,
        onOpenCameras
    }: Props = $props();

    // One device check for the section: the model list starts one for a bird finder and Hardware one
    // for every model, so they share its state and its dialog.
    const deviceCheck = new DeviceCheck(() => onrefreshclassifierstatus?.() ?? Promise.resolve(true));
    onDestroy(() => deviceCheck.dispose());
    let modelsListed = $state(false);
    const circuitUntil = $derived(videoCircuitUntil ? formatDateTime(videoCircuitUntil) : null);

</script>

<div class="space-y-8" data-settings-section="identification">
    <!-- Video checks are under More options, but a paused one needs a look, so its alert is here. -->
    {#if autoVideoClassification && videoCircuitOpen}
        <div role="alert" class="rounded-2xl border border-status-attention-line bg-status-attention-soft px-4 py-3 text-status-attention" data-video-circuit data-settings-lead>
            <p class="mb-2 text-sm font-semibold">{$_('settings.video_circuit.title')}</p>
            <p class="text-sm font-bold leading-relaxed">{$_('settings.video_circuit.message', { values: { failures: videoCircuitFailures } })}</p>
            {#if circuitUntil}
                <p class="mt-2 text-xs">{$_('settings.video_circuit.until', { values: { time: circuitUntil } })}</p>
            {/if}
        </div>
    {/if}

    <div class="space-y-8" data-settings-part="detection">
        <LazyRoute loader={loadNamingSettings} label={$_('settings.naming.title', { default: 'Naming threshold' })}>
        {#snippet content(NamingSettings)}
        <NamingSettings
            bind:threshold
            bind:minConfidence
            bind:personalizedRerankEnabled
            gardenEnabled={enabled}
            bind:automaticNaming
            bind:namingThreshold
        />
        {/snippet}
        </LazyRoute>
    </div>

    <div class="space-y-8" data-settings-part="models">
        <LazyRoute loader={loadModelSettings} label={$_('settings.tabs.models', { default: 'Models' })}>
        {#snippet content(ModelSettings)}
        <ModelSettings
            {autoVideoClassification}
            bind:birdModelRegionOverride
            bind:birdFinder
            bind:birdFinderProvider
            {imageExecutionMode}
            {classifierStatus}
            bind:modelsListed
            {deviceCheck}
            {onrefreshclassifierstatus}
            {onopenlocationsettings}
            {onopenmodelevaluation}
        />
        {/snippet}
        </LazyRoute>
    </div>

    <SectionMore section="identification" summary={$_('settings.more.identification', { default: 'Blocked species, the range filter, video checks, hardware and Beta features' })}>
        <div class="space-y-8" data-settings-detection-more>
            <LazyRoute loader={loadDetectionSettings} label={$_('settings.tabs.detection')}>
            {#snippet content(DetectionSettings)}
            <DetectionSettings
                bind:trustFrigateSublabel
                bind:writeFrigateSublabel
                bind:autoVideoClassification
                bind:videoClassificationDelay
                bind:videoClassificationMaxRetries
                bind:videoClassificationFrames
                bind:blockedLabels
                bind:blockedSpecies
                {onopenlocationsettings}
                bind:rangeFilterEnabled
                bind:rangeFilterRegionLevel
                {onopenebirdsettings}
                {onopenactivitylog}
                {onopenmanualobservation}
            />
            {/snippet}
            </LazyRoute>
        </div>

        <!-- Shown once the model list has its first answer, so its height moves nothing below it. -->
        {#if modelsListed}
            <div class="space-y-8" data-settings-hardware>
                <LazyRoute loader={loadHardwareSettings} label={$_('settings.detection.hardware_title', { default: 'Hardware' })}>
                {#snippet content(HardwareSettings)}
                <HardwareSettings
                    bind:liveWorkerCount
                    bind:backgroundWorkerCount
                    bind:imageExecutionMode
                    bind:inferenceProvider
                    bind:strictNonFiniteOutput
                    {debugUiEnabled}
                    {classifierStatus}
                    {deviceCheck}
                />
                {/snippet}
                </LazyRoute>
            </div>
        {/if}

        <!-- One card per beta feature. A new feature is another <li> holding its own BetaFeatureCard.
             The line above them says what Beta promises, once for every feature. -->
        <div class="space-y-4" data-settings-part="beta" data-beta-page>
            <p class="max-w-prose pl-1 text-sm leading-relaxed text-muted" data-beta-intro>
                {$_('settings.beta.part_intro', { default: 'Features still being tested. Each is off until you turn it on, and may change or be removed. Turning one off keeps what it has already recorded.' })}
            </p>
            <ul class="space-y-4" aria-label={$_('settings.beta.title', { default: 'Beta features' })} data-beta-feature-list>
                <li>
                    <LazyRoute loader={loadGardenBetaSettings} label={$_('settings.tabs.beta')}>
                    {#snippet content(GardenBetaSettings)}
                    <GardenBetaSettings
                        bind:enabled
                        {cameras}
                        {motionCameras}
                        bind:labels
                        bind:motionConfidence
                        bind:notificationsEnabled
                        bind:notificationsUseBirdChannels
                        bind:notificationChannels
                        bind:notificationsIncludePhoto
                        {birdChannels}
                        {onOpenNotifications}
                        {onOpenLocation}
                        bind:domesticBirds
                        {onNavigate}
                        {onOpenCameras}
                    />
                    {/snippet}
                    </LazyRoute>
                </li>
            </ul>
        </div>
    </SectionMore>
</div>

<DeviceCheckDialog check={deviceCheck} />
