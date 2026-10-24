<script lang="ts">
    /**
     * Garden visitors are a beta, so everything that sets them up sits with the switch that turns
     * them on: its own models, which cameras are watched, which Frigate labels count, how confident
     * the motion detector must be, and when an animal is named without a review, as a bird above
     * the naming threshold is. A camera's Garden role is independent of its bird role. Daily review
     * stays on the Garden animals page.
     */
    import { _ } from 'svelte-i18n';
    import SettingsRow from './_primitives/SettingsRow.svelte';
    import SettingsToggle from './_primitives/SettingsToggle.svelte';
    import GardenModelSetup from './GardenModelSetup.svelte';
    import { gardenThresholdStep } from '../../utils/garden-threshold';

    interface Props {
        enabled: boolean;
        cameras: string[];
        motionCameras: string[];
        labels: string;
        motionConfidence: number;
        automaticNaming: boolean;
        namingThreshold: number;
        /** The saved threshold, so a calibrated value keeps its own precision while edited. */
        savedMotionConfidence?: number;
        availableCameras: string[];
        onNavigate?: (path: string) => void;
    }

    let {
        enabled = $bindable(false),
        cameras = $bindable<string[]>([]),
        motionCameras = $bindable<string[]>([]),
        labels = $bindable('cat, dog'),
        motionConfidence = $bindable(0.5),
        automaticNaming = $bindable(true),
        namingThreshold = $bindable(0.8),
        savedMotionConfidence,
        availableCameras,
        onNavigate
    }: Props = $props();

    function toggleCamera(camera: string): void {
        cameras = cameras.includes(camera) ? cameras.filter(name => name !== camera) : [...cameras, camera];
    }

    function toggleMotion(camera: string): void {
        motionCameras = motionCameras.includes(camera)
            ? motionCameras.filter(name => name !== camera)
            : [...motionCameras, camera];
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
        <section class="space-y-2" aria-labelledby="garden-beta-setup">
            <h4 id="garden-beta-setup" class="text-sm font-semibold text-slate-900 dark:text-white">{$_('settings.beta.garden_setup', { default: 'Set up Garden animals' })}</h4>
            <ol class="list-decimal space-y-1 pl-5 text-xs text-slate-600 dark:text-slate-400">
                <li>{$_('settings.beta.garden_setup_apply', { default: 'Choose cameras and labels below, then Apply Settings.' })}</li>
                <li>{$_('settings.beta.garden_setup_models', { default: 'Download the automatic check model, and the motion detector if a camera collects motion photos.' })}</li>
                <li>{$_('settings.beta.garden_setup_review', { default: 'Review new captures on the Garden animals page.' })}</li>
            </ol>
        </section>

        <GardenModelSetup {motionCameras} />

        <section class="space-y-2" aria-labelledby="garden-beta-cameras">
            <h4 id="garden-beta-cameras" class="text-sm font-semibold text-slate-900 dark:text-white">
                {$_('settings.beta.garden_cameras', { default: 'Cameras to watch' })}
            </h4>
            <p class="text-xs text-slate-600 dark:text-slate-400">{$_('garden.camera_help', { default: 'Independent animal review. Keeps this camera’s bird role.' })}</p>
            {#if availableCameras.length === 0}
                <p class="rounded-xl border border-dashed border-line-soft p-3 text-sm text-slate-600 dark:text-slate-300">
                    {$_('settings.beta.garden_no_cameras', { default: 'Sync the camera list in Settings → Connection to choose cameras.' })}
                </p>
            {:else}
                <ul class="space-y-2">
                    {#each availableCameras as camera (camera)}
                        {@const watched = cameras.includes(camera)}
                        <li class="space-y-2 rounded-xl border border-line-soft bg-surface-raised/40 p-3">
                            <div class="flex flex-wrap items-center justify-between gap-3">
                                <span class="min-w-0 truncate text-sm font-semibold text-slate-800 dark:text-slate-100">{camera}</span>
                                <button
                                    type="button"
                                    class="btn btn-secondary min-h-11 max-w-full px-3 py-2 whitespace-normal"
                                    aria-pressed={watched}
                                    aria-label={$_('settings.beta.garden_camera_toggle', { values: { camera }, default: 'Garden animals on {camera}' })}
                                    onclick={() => toggleCamera(camera)}
                                >
                                    {$_('garden.title', { default: 'Garden animals' })}
                                    <span aria-hidden="true">{watched ? '✓' : '+'}</span>
                                </button>
                            </div>
                            {#if watched}
                                <div class="space-y-1 border-t border-line-soft pt-2">
                                    <button
                                        type="button"
                                        class="btn btn-secondary min-h-11 max-w-full px-3 py-2 whitespace-normal"
                                        aria-pressed={motionCameras.includes(camera)}
                                        aria-label={$_('settings.beta.garden_motion_toggle', { values: { camera }, default: 'Collect motion review photos on {camera}' })}
                                        onclick={() => toggleMotion(camera)}
                                    >
                                        {$_('garden.motion_toggle', { default: 'Collect motion review photos' })}
                                        <span aria-hidden="true">{motionCameras.includes(camera) ? '✓' : '+'}</span>
                                    </button>
                                    <p class="text-xs text-slate-600 dark:text-slate-400">{$_('garden.motion_camera_help', { default: 'Optional CPU scans of retained motion footage. Needs the motion detector under Garden models; bird detection keeps its current settings.' })}</p>
                                </div>
                            {/if}
                        </li>
                    {/each}
                </ul>
            {/if}
        </section>

        <div class="space-y-1">
            <label for="garden-labels" class="text-sm font-semibold text-slate-900 dark:text-white">{$_('garden.labels', { default: 'Frigate animal labels' })}</label>
            <input id="garden-labels" class="input-base w-full" bind:value={labels} aria-describedby="garden-label-help" />
            <p id="garden-label-help" class="text-xs text-slate-600 dark:text-slate-400">{$_('garden.labels_help', { default: 'Comma-separated animal labels tracked by Frigate, for example cat, dog or squirrel. Birds, people and vehicles are excluded.' })}</p>
        </div>

        <div class="space-y-1">
            <label for="garden-motion-confidence" class="text-sm font-semibold text-slate-900 dark:text-white">{$_('garden.confidence', { default: 'Animal proposal threshold' })}</label>
            <input
                id="garden-motion-confidence"
                class="input-base w-full"
                type="number"
                min="0.5"
                max="0.95"
                step={gardenThresholdStep(motionConfidence, savedMotionConfidence)}
                bind:value={motionConfidence}
                aria-describedby="garden-motion-confidence-help"
            />
            <p id="garden-motion-confidence-help" class="text-xs text-slate-600 dark:text-slate-400">{$_('garden.confidence_help', { default: 'Higher values reduce proposals but can miss animals. Applies to new motion photos only; bird detection and person privacy checks are unchanged.' })}</p>
        </div>

        <section class="space-y-2" aria-labelledby="garden-beta-naming">
            <div class="flex flex-wrap items-start justify-between gap-4">
                <div class="min-w-0">
                    <h4 id="garden-beta-naming" class="text-sm font-semibold text-slate-900 dark:text-white">{$_('settings.beta.garden_naming', { default: 'Name animals automatically' })}</h4>
                    <p class="text-xs text-slate-600 dark:text-slate-400">{$_('settings.beta.garden_naming_help', { default: 'When the automatic check is at least this sure of an animal, it is confirmed and named for you, marked as automatic. You can discard the name or dismiss the capture. Below the threshold it waits in Needs review.' })}</p>
                </div>
                <SettingsToggle
                    checked={automaticNaming}
                    labelledBy="garden-beta-naming"
                    srLabel={$_('settings.beta.garden_naming', { default: 'Name animals automatically' })}
                    onchange={(value) => (automaticNaming = value)}
                />
            </div>
            {#if automaticNaming}
                <div class="space-y-1">
                    <label for="garden-naming-threshold" class="text-sm font-semibold text-slate-900 dark:text-white">{$_('settings.beta.garden_naming_threshold', { default: 'Naming threshold' })}</label>
                    <input
                        id="garden-naming-threshold"
                        class="input-base w-full"
                        type="number"
                        min="0.7"
                        max="0.99"
                        step="0.01"
                        bind:value={namingThreshold}
                        aria-describedby="garden-naming-threshold-help"
                    />
                    <p id="garden-naming-threshold-help" class="text-xs text-slate-600 dark:text-slate-400">{$_('settings.beta.garden_naming_threshold_help', { default: 'From 0.7 to 0.99. Higher values name fewer animals and leave more for you. Person and bird checks are unchanged.' })}</p>
                </div>
            {:else}
                <p class="text-xs text-slate-600 dark:text-slate-400">{$_('settings.beta.garden_naming_off', { default: 'Every animal waits in Needs review for you to confirm and name it.' })}</p>
            {/if}
        </section>

        <section class="space-y-2" aria-labelledby="garden-beta-outcomes" data-garden-outcomes>
            <h4 id="garden-beta-outcomes" class="text-sm font-semibold text-slate-900 dark:text-white">{$_('settings.beta.garden_outcomes', { default: 'Where captures go' })}</h4>
            <dl class="space-y-2 text-xs text-slate-600 dark:text-slate-400">
                <div>
                    <dt class="font-semibold text-slate-800 dark:text-slate-100">{$_('garden.pending', { default: 'Needs review' })}</dt>
                    <dd>{$_('settings.beta.garden_outcome_pending', { default: 'Animals that were not named automatically, uncertain or mixed results, and checks that could not run. Failed checks retry after five minutes.' })}</dd>
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
