<script lang="ts">
    /**
     * Garden animals as one card on Settings → Beta features. The switch stages the beta in the
     * page draft; its settings appear only while it is on, grouped into sections in the order
     * setup runs, with anything still left to do stated above them. Everything Garden decides is
     * set here, alerts included. Which cameras it watches stays one choice per camera, with the
     * camera's bird role, in Connection, so a camera is never set two ways; this card summarises it.
     * The channels alerts go through are set up once, in Notifications. Daily review is in the
     * Explorer.
     */
    import { tick } from 'svelte';
    import { _, locale } from 'svelte-i18n';
    import BetaFeatureCard from './BetaFeatureCard.svelte';
    import BetaSection from './BetaSection.svelte';
    import { useDisclosure } from '../../settings/disclosures.svelte';
    import SettingsRow from './_primitives/SettingsRow.svelte';
    import SettingsToggle from './_primitives/SettingsToggle.svelte';
    import SettingsInput from './_primitives/SettingsInput.svelte';
    import SettingsSlider from './_primitives/SettingsSlider.svelte';
    import GardenModelSetup from './GardenModelSetup.svelte';
    import GardenCollectionStatus from './GardenCollectionStatus.svelte';
    import GardenNotificationSettings from './GardenNotificationSettings.svelte';
    import type { GardenNotificationChannel } from '../../api/garden';
    import type { PolicyChannel } from '../../settings/notification-policy';
    import { GardenServiceStatus } from './garden-service-status.svelte';
    import { settingsStore } from '../../stores/settings.svelte';
    import { thresholdPercentText } from '../../utils/garden-threshold';
    import { formatCameraList, gardenMotionWithinGarden } from '../../utils/camera-watch';
    import { DOMESTIC_BIRD_KEYS, domesticBirdKind, type DomesticBirdKey } from '../../utils/domestic-birds';
    import { GARDEN_MODEL_NAME, gardenModelRows, type GardenModelRole } from '../../utils/garden-models';
    import { EXECUTION_DEVICE_LABEL, gardenBetaSummary, type GardenNextStep, type GardenStatusPart } from '../../utils/beta-features';

    const DOCS = 'https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/blob/dev/docs/features/garden-animals.md';

    // A type alias, not an interface: the lazy tab loader needs props it can treat as a record.
    type Props = {
        enabled: boolean;
        /** Cameras watched for Garden animals, chosen in Connection. */
        cameras: string[];
        motionCameras: string[];
        labels: string;
        motionConfidence: number;
        automaticNaming: boolean;
        notificationsEnabled?: boolean;
        notificationsUseBirdChannels?: boolean;
        notificationChannels?: GardenNotificationChannel[];
        notificationsIncludePhoto?: boolean;
        /** The bird channels as the page holds them, which Garden alerts can follow. */
        birdChannels?: PolicyChannel[];
        namingThreshold: number;
        /** Domestic birds the owner keeps: Garden animals on every camera, never bird detections. */
        domesticBirds?: DomesticBirdKey[];
        onNavigate?: (path: string) => void;
        /** Opens Connection at its camera list. */
        onOpenCameras?: () => void;
        /** Opens Notifications, where the channels are set up. */
        onOpenNotifications?: () => void;
        /** Opens Integrations at the location, which gives Garden its country. */
        onOpenLocation?: () => void;
    };

    let {
        enabled = $bindable(false),
        cameras,
        motionCameras,
        labels = $bindable('cat, dog'),
        motionConfidence = $bindable(0.5),
        automaticNaming = $bindable(true),
        notificationsEnabled = $bindable(false),
        notificationsUseBirdChannels = $bindable(true),
        notificationChannels = $bindable<GardenNotificationChannel[]>([]),
        notificationsIncludePhoto = $bindable(true),
        birdChannels = [],
        namingThreshold = $bindable(0.8),
        domesticBirds = $bindable([]),
        onNavigate,
        onOpenCameras,
        onOpenNotifications,
        onOpenLocation
    }: Props = $props();

    const service = new GardenServiceStatus();
    const savedEnabled = $derived(settingsStore.settings?.beta_garden_animals === true);

    // The Garden API answers only while the applied switch is on, so it is read then and only then.
    $effect(() => {
        if (!savedEnabled || !enabled) return;
        const controller = new AbortController();
        void service.refresh(controller.signal);
        return () => {
            controller.abort();
            service.cancel();
        };
    });

    // Cameras and naming are what most visits change; the rest is set once and stays closed.
    const modelsSection = useDisclosure(() => ({ id: 'garden-section-models' }));

    const collectingMotion = $derived(gardenMotionWithinGarden(cameras, motionCameras));
    const listLocale = $derived($locale ?? 'en');
    const addableBirds = $derived(DOMESTIC_BIRD_KEYS.filter((key) => !domesticBirds.includes(key)));
    const kind = (key: DomesticBirdKey): string => domesticBirdKind(key, (id, options) => $_(id, options));
    const modelName = (role: GardenModelRole): string => $_(GARDEN_MODEL_NAME[role].id, { default: GARDEN_MODEL_NAME[role].default });

    const summary = $derived(
        gardenBetaSummary({
            enabled,
            savedEnabled,
            cameras,
            models: gardenModelRows(service.identification, service.motion, collectingMotion),
            country: service.identification ? (service.identification.country ?? null) : undefined,
            lastProvider: service.identification?.last_execution?.provider ?? null
        })
    );
    const statusLine = $derived(summary.parts.map(statusPart).join(' · '));

    function statusPart(part: GardenStatusPart): string {
        switch (part.kind) {
            case 'off': return $_('settings.beta.status_off', { default: 'Off' });
            case 'off_after_apply': return $_('settings.beta.status_off_after_apply', { default: 'Off after you save' });
            case 'on': return $_('settings.beta.status_on', { default: 'On' });
            case 'on_after_apply': return $_('settings.beta.status_on_after_apply', { default: 'On after you save' });
            case 'cameras': return $_('settings.beta.garden_status_cameras', { default: '{count, plural, =0 {no camera chosen} one {# camera} other {# cameras}}', values: { count: part.count } });
            case 'device': return $_('settings.beta.garden_status_device', { default: 'automatic checks on {device}', values: { device: EXECUTION_DEVICE_LABEL[part.provider] } });
            case 'model_missing': return $_('settings.beta.garden_status_model_missing', { default: 'model not downloaded yet' });
            case 'no_country': return $_('settings.beta.garden_status_no_country', { default: 'no country set' });
        }
    }

    function stepText(step: GardenNextStep): string {
        switch (step.kind) {
            case 'choose_camera': return $_('settings.beta.garden_step_camera', { default: 'Choose a camera to watch for Garden animals.' });
            case 'apply': return $_('settings.beta.garden_step_apply', { default: 'Save changes to turn Garden on. Model and country checks then appear here.' });
            case 'download_model': return $_('settings.beta.garden_step_model', { default: 'Download the {model}.', values: { model: modelName(step.role) } });
            case 'set_location': return $_('settings.beta.garden_step_location', { default: 'Set your location, so Garden knows your country and can name animals.' });
        }
    }

    async function openModels(): Promise<void> {
        modelsSection.open = true;
        await tick();
        const toggle = document.getElementById('garden-section-models-toggle');
        toggle?.scrollIntoView({ block: 'start' });
        toggle?.focus({ preventScroll: true });
    }

    function addDomesticBird(event: Event): void {
        const select = event.currentTarget as HTMLSelectElement;
        const key = DOMESTIC_BIRD_KEYS.find((candidate) => candidate === select.value);
        if (key && !domesticBirds.includes(key)) domesticBirds = [...domesticBirds, key];
        select.value = '';
    }
</script>

{#snippet offNote()}
    <div class="space-y-2 text-sm text-slate-600 dark:text-slate-400" data-garden-beta-off>
        <p class="font-medium text-slate-800 dark:text-slate-100" data-garden-beta-off-note>
            {$_('settings.beta.garden_off_note', { default: 'Garden stops collecting new captures. Existing captures and settings are kept and come back when you turn it on again.' })}
        </p>
        <p>{$_('settings.beta.garden_off_effects', { default: 'While it is off, Garden is hidden in the Explorer, its alerts stop, and birds you keep are recorded as wild birds. History retention still applies to saved captures.' })}</p>
        <p class="text-xs" data-garden-beta-requirements>
            {$_('settings.beta.garden_requirements', { default: 'Needs Frigate cameras that track animals or keep motion recordings. Garden downloads its own models only when you ask: 224 MB for automatic checks, plus optional 224 MB and 101 MB models. Your bird model is not changed.' })}
        </p>
    </div>
{/snippet}

<BetaFeatureCard
    id="garden-animals"
    name={$_('settings.beta.garden_animals', { default: 'Garden animals' })}
    description={$_('settings.beta.garden_animals_desc', { default: 'Collects cats, foxes and other non-bird visitors from cameras you choose, for you to review.' })}
    learnMoreHref={DOCS}
    {enabled}
    ontoggle={(next) => (enabled = next)}
    status={statusLine}
    attention={summary.attention}
    off={offNote}
>
    <div class="space-y-4 wrap-break-word" data-garden-beta-settings>
        {#if summary.steps.length > 0}
            <section class="space-y-2" aria-labelledby="garden-next-steps" data-garden-next-steps>
                <h3 id="garden-next-steps" class="text-sm font-semibold text-slate-900 dark:text-white">{$_('settings.beta.garden_next_steps', { default: 'Still to set up' })}</h3>
                <ol class="space-y-2">
                    {#each summary.steps as step (step.kind === 'download_model' ? step.role : step.kind)}
                        <li class="flex flex-wrap items-center justify-between gap-x-3 gap-y-1" data-garden-next-step={step.kind}>
                            <span class="flex min-w-0 flex-1 basis-56 items-start gap-2 text-sm text-slate-700 dark:text-slate-200">
                                {#if step.kind !== 'apply'}<span class="attention-dot mt-2" aria-hidden="true"></span>{/if}
                                <span class="min-w-0 wrap-break-word">{stepText(step)}</span>
                            </span>
                            {#if step.kind === 'choose_camera' && onOpenCameras}
                                <button type="button" class="btn btn-secondary min-h-11 max-w-full px-3 py-2 whitespace-normal" onclick={onOpenCameras}>
                                    {$_('settings.beta.garden_cameras_open', { default: 'Choose cameras in Connection' })}
                                </button>
                            {:else if step.kind === 'download_model'}
                                <button type="button" class="btn btn-secondary min-h-11 max-w-full px-3 py-2 whitespace-normal" onclick={openModels}>
                                    {$_('settings.beta.garden_step_model_open', { default: 'Set up Garden models' })}
                                </button>
                            {:else if step.kind === 'set_location' && onOpenLocation}
                                <button type="button" class="btn btn-secondary min-h-11 max-w-full px-3 py-2 whitespace-normal" onclick={onOpenLocation}>
                                    {$_('settings.beta.garden_step_location_open', { default: 'Set location in Integrations' })}
                                </button>
                            {/if}
                        </li>
                    {/each}
                </ol>
            </section>
        {/if}

        <div class="divide-y divide-line-soft">
            <BetaSection id="garden-section-cameras" title={$_('settings.beta.garden_section_cameras', { default: 'Cameras' })} openByDefault>
                <div class="flex flex-wrap items-center justify-between gap-3" data-garden-camera-summary>
                    <div class="min-w-0 flex-1 basis-56 space-y-1 text-sm text-slate-700 dark:text-slate-300">
                        <p>
                            {cameras.length > 0
                                ? $_('settings.beta.garden_cameras_summary', { default: 'Watching {cameras} for Garden animals.', values: { cameras: formatCameraList(cameras, listLocale) } })
                                : $_('settings.beta.garden_cameras_none', { default: 'No camera watches for Garden animals yet.' })}
                        </p>
                        {#if collectingMotion.length > 0}
                            <p>{$_('settings.beta.garden_motion_summary', { default: 'Motion review photos are collected on {cameras}.', values: { cameras: formatCameraList(collectingMotion, listLocale) } })}</p>
                        {/if}
                    </div>
                    <!-- With no camera, the button is the first step above; one control, one place. -->
                    {#if onOpenCameras && cameras.length > 0}
                        <button type="button" class="btn btn-secondary min-h-11 max-w-full px-3 py-2 whitespace-normal" onclick={onOpenCameras}>
                            {$_('settings.beta.garden_cameras_open', { default: 'Choose cameras in Connection' })}
                        </button>
                    {/if}
                </div>

                <SettingsRow
                    labelId="setting-garden-labels"
                    label={$_('garden.labels', { default: 'Frigate animal labels' })}
                    description={$_('garden.labels_help', { default: 'Comma-separated animal labels tracked by Frigate, for example cat, dog or squirrel. Birds, people and vehicles are excluded; add chickens and other birds you keep under Domestic birds you keep.' })}
                    descriptionId="garden-label-help"
                    layout="stacked"
                >
                    <SettingsInput
                        id="garden-labels"
                        field="garden_labels"
                        value={labels}
                        ariaLabel={$_('garden.labels', { default: 'Frigate animal labels' })}
                        describedBy="garden-label-help"
                        oninput={(value) => (labels = value)}
                    />
                </SettingsRow>

                <SettingsSlider
                    id="garden-motion-confidence"
                    field="garden_motion_confidence"
                    label={$_('garden.confidence', { default: 'Suggest a motion photo when this sure it shows an animal' })}
                    description={$_('garden.confidence_help', { default: 'This decides which motion photos reach Needs review. Photos below it are not kept. Higher means fewer suggestions, and more animals missed.' })}
                    bind:value={motionConfidence}
                    min={0.5}
                    max={0.95}
                    step={0.01}
                    display={(value) => `${thresholdPercentText(value)}%`}
                    lowLabel={$_('garden.confidence_low', { default: 'More suggestions' })}
                    highLabel={$_('garden.confidence_high', { default: 'Fewer suggestions' })}
                />
            </BetaSection>

            <BetaSection id="garden-section-checks" title={$_('settings.beta.garden_section_checks', { default: 'Automatic checks and naming' })} openByDefault>
                <div class="space-y-3" data-garden-naming>
                    <SettingsRow
                        labelId="setting-garden-naming"
                        label={$_('settings.beta.garden_naming', { default: 'Name animals automatically' })}
                        description={$_('settings.beta.garden_naming_help', { default: 'Animals that reach the naming threshold are confirmed and named. Photos below it go to Dismissed, where you can restore them.' })}
                    >
                        <SettingsToggle
                            checked={automaticNaming}
                            labelledBy="setting-garden-naming"
                            srLabel={$_('settings.beta.garden_naming', { default: 'Name animals automatically' })}
                            onchange={(value) => (automaticNaming = value)}
                        />
                    </SettingsRow>
                    {#if automaticNaming}
                        <SettingsSlider
                            id="garden-naming-threshold"
                            field="garden_naming_threshold"
                            label={$_('settings.beta.garden_naming_threshold', { default: 'Name an animal when this sure which one it is' })}
                            description={$_('settings.beta.garden_naming_threshold_help', { default: 'This is a second check, on which animal it is. At or above it, the animal is confirmed and named for you. Below it, its photo goes to Dismissed, where you can restore it.' })}
                            bind:value={namingThreshold}
                            min={0.7}
                            max={0.99}
                            step={0.01}
                            display={(value) => `${thresholdPercentText(value)}%`}
                            lowLabel={$_('garden.naming_low', { default: 'Names more' })}
                            highLabel={$_('garden.naming_high', { default: 'Names fewer' })}
                        />
                    {:else}
                        <p class="text-sm text-slate-600 dark:text-slate-400">{$_('settings.beta.garden_naming_off', { default: 'Every animal waits in Needs review for you to confirm and name it.' })}</p>
                    {/if}
                </div>

                <GardenCollectionStatus {service} blockedBy={summary.steps.some((step) => step.kind === 'download_model') ? 'model' : cameras.length === 0 ? 'camera' : null} />

                <p class="text-xs text-slate-600 dark:text-slate-400">
                    {$_('settings.beta.garden_device_note', { default: 'Automatic checks use the device chosen under Settings › Models › Hardware once it agrees with the CPU, and fall back to the CPU if it fails. Motion scans use the CPU. Garden runs one job at a time while birds and cameras are idle.' })}
                    <a href={`${DOCS}#verify-which-device-ran-a-model`} target="_blank" rel="noopener noreferrer" class="focus-ring font-semibold text-brand-700 underline underline-offset-2 hover:text-brand-800 dark:text-brand-300 dark:hover:text-brand-200">
                        {$_('settings.beta.learn_more', { default: 'Learn more' })}
                    </a>
                </p>

                {#if savedEnabled}
                    <div>
                        <button type="button" class="btn btn-secondary min-h-11 max-w-full self-start px-3 py-2 whitespace-normal" disabled={service.loading} onclick={() => service.refresh()}>
                            {$_('settings.beta.garden_status_refresh', { default: 'Refresh status' })}
                        </button>
                    </div>
                {/if}
            </BetaSection>

            <BetaSection id="garden-section-models" title={$_('settings.beta.garden_section_models', { default: 'Models' })}>
                <GardenModelSetup motionCameras={collectingMotion} {service} />
            </BetaSection>

            <BetaSection
                id="garden-section-domestic"
                title={$_('settings.beta.garden_domestic_birds', { default: 'Domestic birds you keep' })}
                hint={$_('settings.beta.garden_domestic_birds_count', { default: '{count, plural, =0 {None} one {# bird} other {# birds}}', values: { count: domesticBirds.length } })}
            >
                <div class="space-y-3" data-garden-domestic-birds>
                    <p id="garden-domestic-birds-help" class="text-sm text-slate-600 dark:text-slate-400">
                        {$_('settings.beta.garden_domestic_birds_help', { default: 'Only for birds you keep. The bird model knows only wild species, so it names a hen as a Red Junglefowl. Birds added here are recorded as Garden animals, not wild birds, and are never sent to eBird, BirdWeather or iNaturalist.' })}
                    </p>
                    <p class="text-xs text-slate-600 dark:text-slate-400">
                        {$_('settings.beta.garden_domestic_birds_wild', { default: 'Nothing counts as domestic until you add it. Mallards, Greylag Geese, Wild Turkeys and Rock Doves also live wild, so on every camera they are then recorded as your birds.' })}
                        <a href={`${DOCS}#domestic-birds`} target="_blank" rel="noopener noreferrer" class="focus-ring font-semibold text-brand-700 underline underline-offset-2 hover:text-brand-800 dark:text-brand-300 dark:hover:text-brand-200">
                            {$_('settings.beta.learn_more', { default: 'Learn more' })}
                        </a>
                    </p>
                    {#if domesticBirds.length > 0}
                        <ul class="flex flex-wrap gap-2" aria-label={$_('settings.beta.garden_domestic_birds', { default: 'Domestic birds you keep' })} data-garden-domestic-chips>
                            {#each domesticBirds as key (key)}
                                <li class="inline-flex items-center gap-1 rounded-full border border-line-soft bg-surface-raised pl-3 text-sm text-slate-800 dark:text-slate-100">
                                    {kind(key)}
                                    <button
                                        type="button"
                                        class="btn btn-ghost min-h-11 min-w-11 rounded-full px-2"
                                        aria-label={$_('settings.beta.garden_domestic_birds_remove', { default: 'Remove {bird}', values: { bird: kind(key) } })}
                                        onclick={() => (domesticBirds = domesticBirds.filter((value) => value !== key))}
                                    >
                                        <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" d="M6 6l12 12M18 6L6 18" /></svg>
                                    </button>
                                </li>
                            {/each}
                        </ul>
                    {:else}
                        <p class="text-sm text-slate-600 dark:text-slate-400" data-garden-domestic-none>
                            {$_('settings.beta.garden_domestic_birds_none', { default: 'None yet. Chickens and other birds you keep are treated as wild birds.' })}
                        </p>
                    {/if}
                    {#if addableBirds.length > 0}
                        <label class="block max-w-sm space-y-1 text-xs text-slate-600 dark:text-slate-400">
                            <span>{$_('settings.beta.garden_domestic_birds_add', { default: 'Add a domestic bird' })}</span>
                            <select class="select-base w-full" value="" onchange={addDomesticBird} aria-describedby="garden-domestic-birds-help" data-garden-domestic-add>
                                <option value="" disabled>{$_('settings.beta.garden_domestic_birds_choose', { default: 'Choose a bird' })}</option>
                                {#each addableBirds as key (key)}
                                    <option value={key}>{kind(key)}</option>
                                {/each}
                            </select>
                        </label>
                    {/if}
                </div>
            </BetaSection>

            <BetaSection
                id="garden-section-alerts"
                title={$_('settings.beta.garden_section_alerts', { default: 'Alerts' })}
                hint={notificationsEnabled ? $_('settings.beta.status_on', { default: 'On' }) : $_('settings.beta.status_off', { default: 'Off' })}
            >
                <GardenNotificationSettings
                    bind:enabled={notificationsEnabled}
                    bind:useBirdChannels={notificationsUseBirdChannels}
                    bind:channels={notificationChannels}
                    bind:includePhoto={notificationsIncludePhoto}
                    {birdChannels}
                    statusAvailable={savedEnabled}
                />
                {#if onOpenNotifications}
                    <div>
                        <button type="button" class="btn btn-secondary min-h-11 max-w-full px-3 py-2 whitespace-normal" onclick={onOpenNotifications}>
                            {$_('settings.beta.garden_channels_open', { default: 'Set up channels in Notifications' })}
                        </button>
                    </div>
                {/if}
            </BetaSection>

            <BetaSection id="garden-section-outcomes" title={$_('settings.beta.garden_outcomes', { default: 'Where captures go' })}>
                <div class="space-y-3" data-garden-outcomes>
                    <dl class="space-y-2 text-sm text-slate-600 dark:text-slate-400">
                        <div>
                            <dt class="font-semibold text-slate-800 dark:text-slate-100">{$_('garden.pending', { default: 'Needs review' })}</dt>
                            <dd>{$_('settings.beta.garden_outcome_pending_review', { default: 'Checks waiting to run, failed checks waiting for retry, missing setup or catalogue identity, and owner overrides.' })}</dd>
                        </div>
                        <div>
                            <dt class="font-semibold text-slate-800 dark:text-slate-100">{$_('garden.confirmed', { default: 'Confirmed animals' })}</dt>
                            <dd>{$_('settings.beta.garden_outcome_confirmed', { default: 'Animals you confirm, and confident animals named automatically. An automatic name is marked as automatic and can be discarded.' })}</dd>
                        </div>
                        <div>
                            <dt class="font-semibold text-slate-800 dark:text-slate-100">{$_('garden.dismissed', { default: 'Dismissed' })}</dt>
                            <dd>{$_('settings.beta.garden_outcome_dismissed_low_score', { default: 'Captures you dismiss, photos whose species score is below the naming threshold, and photos the check is confident show a bird you do not keep, nothing or a vehicle. Return to review restores one while its photo remains.' })}</dd>
                        </div>
                    </dl>
                    <p class="text-xs text-slate-600 dark:text-slate-400">{$_('settings.beta.garden_outcome_person', { default: 'A capture with person evidence is removed with its photo. Garden visits never count as birds or reach bird notifications and exports.' })}</p>
                    <div class="flex flex-wrap items-center justify-between gap-3">
                        <p class="min-w-0 flex-1 basis-56 text-sm text-slate-700 dark:text-slate-300">{$_('settings.beta.garden_explorer_help', { default: 'New captures wait in the Explorer under Garden animals, Needs review.' })}</p>
                        {#if onNavigate}
                            <button type="button" class="btn btn-secondary min-h-11 max-w-full px-3 py-2 whitespace-normal" onclick={() => onNavigate?.('/events?visitors=garden&review=pending')}>
                                {$_('settings.beta.garden_explorer_open', { default: 'Review Garden animals' })}
                            </button>
                        {/if}
                    </div>
                </div>
            </BetaSection>
        </div>
    </div>
</BetaFeatureCard>
