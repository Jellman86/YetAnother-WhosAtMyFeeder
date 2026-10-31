<script lang="ts">
    /**
     * Garden visitors are a beta, so everything that sets them up sits with the switch that turns
     * them on, in the order the setup steps give: which cameras and labels are collected, Garden's
     * own models, when an animal is named without a review (as a bird above the naming threshold
     * is), then alerts. Cameras are chosen once, with their bird role, in Connection; this view
     * only says which ones watch for Garden animals. Daily review is in the Explorer.
     */
    import { _, locale } from 'svelte-i18n';
    import SettingsRow from './_primitives/SettingsRow.svelte';
    import SettingsToggle from './_primitives/SettingsToggle.svelte';
    import SettingsInput from './_primitives/SettingsInput.svelte';
    import GardenNotificationSettings from './GardenNotificationSettings.svelte';
    import type { GardenNotificationChannel } from '../../api/garden';
    import GardenModelSetup from './GardenModelSetup.svelte';
    import { gardenThresholdPercentStep, percentToThreshold, thresholdPercentText } from '../../utils/garden-threshold';
    import { formatCameraList, gardenMotionWithinGarden } from '../../utils/camera-watch';

    interface Props {
        enabled: boolean;
        /** Cameras watched for Garden animals, chosen in Connection. */
        cameras: string[];
        motionCameras: string[];
        labels: string;
        motionConfidence: number;
        automaticNaming: boolean;
        notificationsEnabled?: boolean;
        notificationChannels?: GardenNotificationChannel[];
        namingThreshold: number;
        /** The saved threshold, so a calibrated value keeps its own precision while edited. */
        savedMotionConfidence?: number;
        onNavigate?: (path: string) => void;
        /** Opens Connection at its camera list. */
        onOpenCameras?: () => void;
    }

    let {
        enabled = $bindable(false),
        cameras,
        motionCameras,
        labels = $bindable('cat, dog'),
        motionConfidence = $bindable(0.5),
        automaticNaming = $bindable(true),
        notificationsEnabled = $bindable(false),
        notificationChannels = $bindable<GardenNotificationChannel[]>([]),
        namingThreshold = $bindable(0.8),
        savedMotionConfidence,
        onNavigate,
        onOpenCameras
    }: Props = $props();

    const collectingMotion = $derived(gardenMotionWithinGarden(cameras, motionCameras));
    const listLocale = $derived($locale ?? 'en');
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
                description={$_('garden.labels_help', { default: 'Comma-separated animal labels tracked by Frigate, for example cat, dog or squirrel. Birds, people and vehicles are excluded.' })}
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

        <GardenModelSetup motionCameras={collectingMotion} />

        <div class="space-y-3" data-garden-naming>
            <SettingsRow
                labelId="setting-garden-naming"
                label={$_('settings.beta.garden_naming', { default: 'Name animals automatically' })}
                description={$_('settings.beta.garden_naming_help', { default: 'When the automatic check is at least this sure of an animal, it is confirmed and named for you, marked as automatic. You can discard the name or dismiss the capture. Below the threshold it moves to Dismissed and can be restored.' })}
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

        <GardenNotificationSettings bind:enabled={notificationsEnabled} bind:channels={notificationChannels} />

        <section class="space-y-2" aria-labelledby="garden-beta-outcomes" data-garden-outcomes>
            <h4 id="garden-beta-outcomes" class="text-sm font-semibold text-slate-900 dark:text-white">{$_('settings.beta.garden_outcomes', { default: 'Where captures go' })}</h4>
            <dl class="space-y-2 text-xs text-slate-600 dark:text-slate-400">
                <div>
                    <dt class="font-semibold text-slate-800 dark:text-slate-100">{$_('garden.pending', { default: 'Needs review' })}</dt>
                    <dd>{$_('settings.beta.garden_outcome_pending', { default: 'Checks waiting to run, failed checks waiting for retry, missing setup or catalogue identity, and owner overrides. Low-confidence completed checks move to Dismissed.' })}</dd>
                </div>
                <div>
                    <dt class="font-semibold text-slate-800 dark:text-slate-100">{$_('garden.confirmed', { default: 'Confirmed animals' })}</dt>
                    <dd>{$_('settings.beta.garden_outcome_confirmed', { default: 'Animals you confirm, and confident animals named automatically. An automatic name is marked as automatic and can be discarded.' })}</dd>
                </div>
                <div>
                    <dt class="font-semibold text-slate-800 dark:text-slate-100">{$_('garden.dismissed', { default: 'Dismissed' })}</dt>
                    <dd>{$_('settings.beta.garden_outcome_dismissed', { default: 'Captures you dismiss, and photos the check is confident show only a bird, nothing or a vehicle. Return to review restores one while its photo remains.' })}</dd>
                </div>
            </dl>
            <p class="text-xs text-slate-600 dark:text-slate-400">{$_('settings.beta.garden_outcome_person', { default: 'A capture with person evidence is removed with its photo. Garden visits never count as birds or reach bird notifications and exports.' })}</p>
        </section>

        <div class="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line-soft p-3">
            <p class="min-w-0 flex-1 text-xs text-slate-600 dark:text-slate-400">{$_('settings.beta.garden_explorer_help', { default: 'Garden visitors appear in the Explorer beside your birds. Choose Garden visitors there, then Needs review, to work through new captures.' })}</p>
            {#if onNavigate}
                <button type="button" class="btn btn-secondary min-h-11 max-w-full px-3 py-2 whitespace-normal" onclick={() => onNavigate?.('/events?visitors=garden&review=pending')}>
                    {$_('settings.beta.garden_explorer_open', { default: 'Review Garden visitors' })}
                </button>
            {/if}
        </div>
    </div>
{/if}
