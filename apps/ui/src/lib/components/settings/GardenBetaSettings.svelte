<script lang="ts">
    /**
     * Garden animals are a beta, so everything that sets them up sits with the switch that turns
     * them on, in the order the setup steps give: which cameras and labels are collected, Garden's
     * own models, when an animal is named without a review (as a bird above the naming threshold
     * is), then alerts. Cameras are chosen once, with their bird role, in Connection, and alerts
     * with their channels in Notifications; this view only summarises both. Daily review is in
     * the Explorer.
     */
    import { _, locale } from 'svelte-i18n';
    import SettingsRow from './_primitives/SettingsRow.svelte';
    import SettingsToggle from './_primitives/SettingsToggle.svelte';
    import SettingsInput from './_primitives/SettingsInput.svelte';
    import GardenModelSetup from './GardenModelSetup.svelte';
    import { gardenThresholdPercentStep, percentToThreshold, thresholdPercentText } from '../../utils/garden-threshold';
    import { formatCameraList, gardenMotionWithinGarden } from '../../utils/camera-watch';
    import { DOMESTIC_BIRD_KEYS, domesticBirdKind, type DomesticBirdKey } from '../../utils/domestic-birds';

    interface Props {
        enabled: boolean;
        /** Cameras watched for Garden animals, chosen in Connection. */
        cameras: string[];
        motionCameras: string[];
        labels: string;
        motionConfidence: number;
        automaticNaming: boolean;
        /** Whether Garden alerts are on, as the page holds it; they are set up in Notifications. */
        notificationsEnabled?: boolean;
        namingThreshold: number;
        /** Domestic birds the owner keeps: Garden animals on every camera, never bird detections. */
        domesticBirds?: DomesticBirdKey[];
        /** The saved threshold, so a calibrated value keeps its own precision while edited. */
        savedMotionConfidence?: number;
        onNavigate?: (path: string) => void;
        /** Opens Connection at its camera list. */
        onOpenCameras?: () => void;
        /** Opens Notifications, where Garden alerts are set up. */
        onOpenNotifications?: () => void;
    }

    let {
        enabled = $bindable(false),
        cameras,
        motionCameras,
        labels = $bindable('cat, dog'),
        motionConfidence = $bindable(0.5),
        automaticNaming = $bindable(true),
        notificationsEnabled = false,
        namingThreshold = $bindable(0.8),
        domesticBirds = $bindable([]),
        savedMotionConfidence,
        onNavigate,
        onOpenCameras,
        onOpenNotifications
    }: Props = $props();

    const collectingMotion = $derived(gardenMotionWithinGarden(cameras, motionCameras));
    const listLocale = $derived($locale ?? 'en');
    const addableBirds = $derived(DOMESTIC_BIRD_KEYS.filter((key) => !domesticBirds.includes(key)));
    const kind = (key: DomesticBirdKey): string => domesticBirdKind(key, (id, options) => $_(id, options));

    function addDomesticBird(event: Event): void {
        const select = event.currentTarget as HTMLSelectElement;
        const key = DOMESTIC_BIRD_KEYS.find((candidate) => candidate === select.value);
        if (key && !domesticBirds.includes(key)) domesticBirds = [...domesticBirds, key];
        select.value = '';
    }
</script>

<SettingsRow
    labelId="setting-beta-garden-animals"
    label={$_('settings.beta.garden_animals', { default: 'Garden animals' })}
    description={$_('settings.beta.garden_animals_desc', { default: 'Collects non-bird visitors such as cats, dogs and foxes from cameras you choose, for you to review. Turning it off stops new collection and hides Garden; saved captures are kept.' })}
>
    <SettingsToggle
        checked={enabled}
        labelledBy="setting-beta-garden-animals"
        srLabel={$_('settings.beta.garden_animals', { default: 'Garden animals' })}
        onchange={(value) => (enabled = value)}
    />
</SettingsRow>

{#if !enabled}
    <p class="px-4 pt-3 text-xs text-slate-600 dark:text-slate-400" data-garden-beta-requirements>
        {$_('settings.beta.garden_requirements', { default: 'Needs Frigate cameras that track animals or keep motion recordings. Garden downloads its own models when you ask: 224 MB for automatic checks, plus an optional 224 MB species suggestion model and an optional 101 MB motion detector. Your bird model is not changed.' })}
    </p>
{:else}
    <div class="space-y-5 break-words border-t border-line-soft pt-4" data-garden-beta-settings>
        <section class="space-y-2" aria-labelledby="garden-beta-setup" data-garden-setup-steps>
            <h4 id="garden-beta-setup" class="text-sm font-semibold text-slate-900 dark:text-white">{$_('settings.beta.garden_setup', { default: 'Set up Garden animals' })}</h4>
            <ol class="list-decimal space-y-1 pl-5 text-xs text-slate-600 dark:text-slate-400">
                <li>{$_('settings.beta.garden_setup_apply', { default: 'In Connection, choose Garden animals or Both for each camera. Set the animal labels below, then Apply Settings.' })}</li>
                <li>{$_('settings.beta.garden_setup_models', { default: 'Download the automatic check model, and the motion detector if a camera collects motion photos.' })}</li>
                <li>{$_('settings.beta.garden_setup_review', { default: 'Review new captures in the Explorer.' })}</li>
            </ol>
        </section>

        <section class="space-y-3" aria-labelledby="garden-beta-cameras" data-garden-collect>
            <h4 id="garden-beta-cameras" class="text-sm font-semibold text-slate-900 dark:text-white">
                {$_('settings.beta.garden_cameras', { default: 'Cameras to watch' })}
            </h4>
            <div class="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line-soft p-3" data-garden-camera-summary>
                <div class="min-w-0 flex-1 basis-56 space-y-1 text-xs text-slate-700 dark:text-slate-300">
                    <p>
                        {cameras.length > 0
                            ? $_('settings.beta.garden_cameras_summary', { default: 'Watching {cameras} for Garden animals.', values: { cameras: formatCameraList(cameras, listLocale) } })
                            : $_('settings.beta.garden_cameras_none', { default: 'No camera is watched for Garden animals yet. Choose Garden animals or Both for a camera in Connection.' })}
                    </p>
                    {#if collectingMotion.length > 0}
                        <p>{$_('settings.beta.garden_motion_summary', { default: 'Motion review photos are collected on {cameras}.', values: { cameras: formatCameraList(collectingMotion, listLocale) } })}</p>
                    {/if}
                </div>
                {#if onOpenCameras}
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
                    value={labels}
                    ariaLabel={$_('garden.labels', { default: 'Frigate animal labels' })}
                    describedBy="garden-label-help"
                    oninput={(value) => (labels = value)}
                />
            </SettingsRow>

            <SettingsRow
                labelId="setting-garden-motion-confidence"
                label={$_('garden.confidence', { default: 'Animal proposal threshold' })}
                description={$_('garden.confidence_help', { default: 'From 50% to 95%. Higher values reduce proposals but can miss animals. Applies to new motion photos only; bird detection and person privacy checks are unchanged.' })}
                descriptionId="garden-motion-confidence-help"
                layout="stacked"
            >
                <div class="flex items-center gap-2">
                    <div class="min-w-0 flex-1">
                        <SettingsInput
                            id="garden-motion-confidence"
                            type="number"
                            min={50}
                            max={95}
                            step={gardenThresholdPercentStep(motionConfidence, savedMotionConfidence)}
                            value={thresholdPercentText(motionConfidence)}
                            ariaLabel={$_('garden.confidence', { default: 'Animal proposal threshold' })}
                            describedBy="garden-motion-confidence-help"
                            oninput={(value) => (motionConfidence = percentToThreshold(value))}
                        />
                    </div>
                    <span class="text-sm font-semibold text-slate-600 dark:text-slate-300" aria-hidden="true">%</span>
                </div>
            </SettingsRow>
        </section>

        <section class="space-y-2" aria-labelledby="garden-domestic-birds" data-garden-domestic-birds>
            <h4 id="garden-domestic-birds" class="text-sm font-semibold text-slate-900 dark:text-white">
                {$_('settings.beta.garden_domestic_birds', { default: 'Domestic birds you keep' })}
            </h4>
            <p id="garden-domestic-birds-help" class="text-xs text-slate-600 dark:text-slate-400">
                {$_('settings.beta.garden_domestic_birds_help', { default: 'These are recorded as Garden animals, not wild birds, and are never sent to eBird, BirdWeather or iNaturalist.' })}
            </p>
            <p class="text-xs text-slate-600 dark:text-slate-400">
                {$_('settings.beta.garden_domestic_birds_wild', { default: 'Nothing counts as domestic until you add it. Mallards, Greylag Geese, Wild Turkeys and Rock Doves also live wild, so on every camera they are then recorded as your birds.' })}
            </p>
            {#if domesticBirds.length > 0}
                <ul class="flex flex-wrap gap-2" aria-label={$_('settings.beta.garden_domestic_birds', { default: 'Domestic birds you keep' })} data-garden-domestic-chips>
                    {#each domesticBirds as key (key)}
                        <li class="inline-flex items-center gap-1 rounded-full border border-line-soft bg-slate-50 pl-3 text-sm text-slate-800 dark:bg-slate-800 dark:text-slate-100">
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
                <p class="text-xs text-slate-600 dark:text-slate-400" data-garden-domestic-none>
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
        </section>

        <GardenModelSetup motionCameras={collectingMotion} />

        <div class="space-y-3" data-garden-naming>
            <SettingsRow
                labelId="setting-garden-naming"
                label={$_('settings.beta.garden_naming', { default: 'Name animals automatically' })}
                description={$_('settings.beta.garden_naming_help', { default: 'Animals reaching this species confidence are confirmed and named automatically. An animal below the threshold waits in Needs review; an uncertain photo below it moves to Dismissed and can be restored. Failed checks retry; missing country or catalogue identity is explained.' })}
            >
                <SettingsToggle
                    checked={automaticNaming}
                    labelledBy="setting-garden-naming"
                    srLabel={$_('settings.beta.garden_naming', { default: 'Name animals automatically' })}
                    onchange={(value) => (automaticNaming = value)}
                />
            </SettingsRow>
            {#if automaticNaming}
                <SettingsRow
                    labelId="setting-garden-naming-threshold"
                    label={$_('settings.beta.garden_naming_threshold', { default: 'Naming threshold' })}
                    description={$_('settings.beta.garden_naming_threshold_help', { default: 'From 70% to 99%. Higher values name fewer animals and dismiss more low-confidence photos. Person and bird checks are unchanged.' })}
                    descriptionId="garden-naming-threshold-help"
                    layout="stacked"
                >
                    <div class="flex items-center gap-2">
                        <div class="min-w-0 flex-1">
                            <SettingsInput
                                id="garden-naming-threshold"
                                type="number"
                                min={70}
                                max={99}
                                step={1}
                                value={thresholdPercentText(namingThreshold)}
                                ariaLabel={$_('settings.beta.garden_naming_threshold', { default: 'Naming threshold' })}
                                describedBy="garden-naming-threshold-help"
                                oninput={(value) => (namingThreshold = percentToThreshold(value))}
                            />
                        </div>
                        <span class="text-sm font-semibold text-slate-600 dark:text-slate-300" aria-hidden="true">%</span>
                    </div>
                </SettingsRow>
            {:else}
                <p class="px-4 text-xs text-slate-600 dark:text-slate-400">{$_('settings.beta.garden_naming_off', { default: 'Every animal waits in Needs review for you to confirm and name it.' })}</p>
            {/if}
        </div>

        <div class="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line-soft p-3" data-garden-alerts-summary>
            <p class="min-w-0 flex-1 basis-56 text-xs text-slate-700 dark:text-slate-300">
                {notificationsEnabled
                    ? $_('settings.beta.garden_alerts_on', { default: 'Garden alerts are on. They are set up in Notifications, with their channels.' })
                    : $_('settings.beta.garden_alerts_off', { default: 'Garden alerts are off. Turn them on in Notifications, with their channels.' })}
            </p>
            {#if onOpenNotifications}
                <button type="button" class="btn btn-secondary min-h-11 max-w-full px-3 py-2 whitespace-normal" onclick={onOpenNotifications}>
                    {$_('settings.beta.garden_alerts_open', { default: 'Set up alerts' })}
                </button>
            {/if}
        </div>

        <section class="space-y-2" aria-labelledby="garden-beta-outcomes" data-garden-outcomes>
            <h4 id="garden-beta-outcomes" class="text-sm font-semibold text-slate-900 dark:text-white">{$_('settings.beta.garden_outcomes', { default: 'Where captures go' })}</h4>
            <dl class="space-y-2 text-xs text-slate-600 dark:text-slate-400">
                <div>
                    <dt class="font-semibold text-slate-800 dark:text-slate-100">{$_('garden.pending', { default: 'Needs review' })}</dt>
                    <dd>{$_('settings.beta.garden_outcome_pending', { default: 'Checks waiting to run, failed checks waiting for retry, missing setup or catalogue identity, animals whose species is below the naming threshold, and owner overrides.' })}</dd>
                </div>
                <div>
                    <dt class="font-semibold text-slate-800 dark:text-slate-100">{$_('garden.confirmed', { default: 'Confirmed animals' })}</dt>
                    <dd>{$_('settings.beta.garden_outcome_confirmed', { default: 'Animals you confirm, and confident animals named automatically. An automatic name is marked as automatic and can be discarded.' })}</dd>
                </div>
                <div>
                    <dt class="font-semibold text-slate-800 dark:text-slate-100">{$_('garden.dismissed', { default: 'Dismissed' })}</dt>
                    <dd>{$_('settings.beta.garden_outcome_dismissed', { default: 'Captures you dismiss, uncertain photos below the naming threshold, and photos the check is confident show a bird you do not keep, nothing or a vehicle. Return to review restores one while its photo remains.' })}</dd>
                </div>
            </dl>
            <p class="text-xs text-slate-600 dark:text-slate-400">{$_('settings.beta.garden_outcome_person', { default: 'A capture with person evidence is removed with its photo. Garden visits never count as birds or reach bird notifications and exports.' })}</p>
        </section>

        <div class="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line-soft p-3">
            <p class="min-w-0 flex-1 text-xs text-slate-600 dark:text-slate-400">{$_('settings.beta.garden_explorer_help', { default: 'Garden animals appear in the Explorer beside your birds. Choose Garden animals there, then Needs review, to work through new captures.' })}</p>
            {#if onNavigate}
                <button type="button" class="btn btn-secondary min-h-11 max-w-full px-3 py-2 whitespace-normal" onclick={() => onNavigate?.('/events?visitors=garden&review=pending')}>
                    {$_('settings.beta.garden_explorer_open', { default: 'Review Garden animals' })}
                </button>
            {/if}
        </div>
    </div>
{/if}
