<script lang="ts">
    /**
     * Garden visitors are a beta, so everything that configures them sits with the switch that
     * turns them on: which cameras are watched, which Frigate labels count, and how confident
     * the motion detector must be. A camera's Garden role is independent of its bird role.
     */
    import { _ } from 'svelte-i18n';
    import SettingsRow from './_primitives/SettingsRow.svelte';
    import SettingsToggle from './_primitives/SettingsToggle.svelte';
    import { gardenThresholdStep } from '../../utils/garden-threshold';

    interface Props {
        enabled: boolean;
        cameras: string[];
        motionCameras: string[];
        labels: string;
        motionConfidence: number;
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

{#if enabled}
    <div class="space-y-5 border-t border-line-soft pt-4" data-garden-beta-settings>
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
                                    class="btn btn-secondary min-h-11 px-3 py-2"
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
                                        class="btn btn-secondary min-h-11 px-3 py-2"
                                        aria-pressed={motionCameras.includes(camera)}
                                        aria-label={$_('settings.beta.garden_motion_toggle', { values: { camera }, default: 'Collect motion review photos on {camera}' })}
                                        onclick={() => toggleMotion(camera)}
                                    >
                                        {$_('garden.motion_toggle', { default: 'Collect motion review photos' })}
                                        <span aria-hidden="true">{motionCameras.includes(camera) ? '✓' : '+'}</span>
                                    </button>
                                    <p class="text-xs text-slate-600 dark:text-slate-400">{$_('garden.motion_camera_help', { default: 'Optional CPU scans of retained motion footage. Download the detector on Garden animals; bird detection keeps its current settings.' })}</p>
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

        <div class="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line-soft p-3">
            <p class="min-w-0 flex-1 text-xs text-slate-600 dark:text-slate-400">{$_('settings.beta.garden_page_help', { default: 'Models, collection status and reviews are on the Garden animals page.' })}</p>
            {#if onNavigate}
                <button type="button" class="btn btn-secondary min-h-11 px-3 py-2" onclick={() => onNavigate?.('/garden')}>
                    {$_('settings.beta.garden_page_open', { default: 'Open Garden animals' })}
                </button>
            {/if}
        </div>
    </div>
{/if}
