<script lang="ts">
    import type { ComponentProps } from 'svelte';
    import { _ } from 'svelte-i18n';
    import LazyRoute from '../../LazyRoute.svelte';
    import type DetectionSettingsView from '../DetectionSettings.svelte';
    import type ModelSettingsView from '../ModelSettings.svelte';
    import type GardenBetaSettingsView from '../GardenBetaSettings.svelte';
    import { loadDetectionSettings, loadGardenBetaSettings, loadModelSettings } from './part-loaders';

    // Identifying birds: how sure a name must be, the models that find and name birds, and the
    // features still in Beta. Holds what were the Detection, Models and Beta features tabs. Models
    // reads the same video setting Detection edits, and both open the location the same way. Each
    // part's props keep its component's own names.
    type Props = ComponentProps<typeof DetectionSettingsView>
        & Omit<ComponentProps<typeof ModelSettingsView>, 'autoVideoClassification' | 'onopenlocationsettings'>
        & ComponentProps<typeof GardenBetaSettingsView>;

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
        onopenmodels,
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
</script>

<div class="space-y-8" data-settings-section="identification">
    <div class="space-y-8" data-settings-part="detection">
        <LazyRoute loader={loadDetectionSettings} label={$_('settings.tabs.detection')}>
        {#snippet content(DetectionSettings)}
        <DetectionSettings
            bind:threshold
            bind:minConfidence
            bind:trustFrigateSublabel
            bind:writeFrigateSublabel
            bind:personalizedRerankEnabled
            bind:autoVideoClassification
            bind:videoClassificationDelay
            bind:videoClassificationMaxRetries
            bind:videoClassificationFrames
            bind:blockedLabels
            bind:blockedSpecies
            {videoCircuitOpen}
            {videoCircuitUntil}
            {videoCircuitFailures}
            {onopenlocationsettings}
            bind:rangeFilterEnabled
            bind:rangeFilterRegionLevel
            {onopenebirdsettings}
            {onopenactivitylog}
            {onopenmanualobservation}
            {onopenmodels}
        />
        {/snippet}
        </LazyRoute>
    </div>

    <div class="space-y-8" data-settings-part="models">
        <LazyRoute loader={loadModelSettings} label={$_('settings.tabs.models', { default: 'Models' })}>
        {#snippet content(ModelSettings)}
        <ModelSettings
            bind:liveWorkerCount
            bind:backgroundWorkerCount
            {autoVideoClassification}
            bind:birdModelRegionOverride
            bind:birdFinder
            bind:birdFinderProvider
            bind:imageExecutionMode
            bind:inferenceProvider
            bind:strictNonFiniteOutput
            {debugUiEnabled}
            {classifierStatus}
            {onrefreshclassifierstatus}
            {onopenlocationsettings}
            {onopenmodelevaluation}
        />
        {/snippet}
        </LazyRoute>
    </div>

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
                    bind:automaticNaming
                    bind:namingThreshold
                    bind:domesticBirds
                    {onNavigate}
                    {onOpenCameras}
                />
                {/snippet}
                </LazyRoute>
            </li>
        </ul>
    </div>
</div>
