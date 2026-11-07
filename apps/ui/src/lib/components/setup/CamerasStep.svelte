<script lang="ts">
    import { onMount } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { fetchSettings, updateSettings } from '../../api/settings';
    import { fetchFrigateConfig } from '../../api/system';
    import { setupWizardStore } from '../../stores/setup_wizard.svelte';
    import WizardStepLayout from './WizardStepLayout.svelte';
    import WizardLoadState, { type WizardLoadStatus } from './WizardLoadState.svelte';
    import CameraThumbnail from './CameraThumbnail.svelte';
    import { cameraChoices, frigateCameraNames, parseCameraNames } from './camera-choices';

    const DOCS_URL = 'https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/blob/main/docs/troubleshooting/frigate-event-not-found.md';

    let selected = $state<string[]>([]);
    let savedCameras = $state<string[]>([]);
    /** Null when Frigate's list could not be read: names can then only be typed, unchecked. */
    let frigateCameras = $state<string[] | null>(null);
    let camerasText = $state('');
    let loadState = $state<WizardLoadStatus>('loading');
    let retrying = $state(false);
    let busy = $state(false);

    let choices = $derived(frigateCameras ? cameraChoices(frigateCameras, savedCameras) : []);
    let chosen = $derived(frigateCameras ? selected : parseCameraNames(camerasText));

    function toggle(camera: string, on: boolean): void {
        selected = on ? [...selected, camera] : selected.filter((name) => name !== camera);
    }

    async function readFrigateCameras(): Promise<void> {
        try {
            frigateCameras = frigateCameraNames(await fetchFrigateConfig());
        } catch {
            frigateCameras = null;
        }
    }

    async function retryFrigate(): Promise<void> {
        retrying = true;
        await readFrigateCameras();
        selected = parseCameraNames(camerasText);
        savedCameras = selected;
        retrying = false;
    }

    async function load(): Promise<void> {
        loadState = 'loading';
        const [settingsResult] = await Promise.allSettled([fetchSettings(), readFrigateCameras()]);
        if (settingsResult.status === 'rejected') {
            loadState = 'error';
            return;
        }
        savedCameras = settingsResult.value.cameras ?? [];
        selected = savedCameras;
        camerasText = savedCameras.join(', ');
        loadState = 'ready';
    }

    onMount(() => {
        void load();
    });

    async function save() {
        if (loadState !== 'ready') return;
        busy = true;
        try {
            await updateSettings({ cameras: chosen });
            await setupWizardStore.refresh();
            setupWizardStore.completeStep();
        } finally {
            busy = false;
        }
    }
</script>

<WizardStepLayout
    title={$_('setup.cameras.title', { default: 'Cameras & detection' })}
    description={$_('setup.cameras.description', {
        default: 'Choose which Frigate cameras YA-WAMF watches. Advanced detection and classifier gates stay in Detection settings.'
    })}
    canContinue={loadState === 'ready'}
    {busy}
    onContinue={save}
>
    <WizardLoadState state={loadState} onRetry={load}>
        {#if frigateCameras}
            <fieldset class="space-y-3" data-setup-camera-choices>
                <legend class="text-sm font-medium text-slate-700 dark:text-slate-300">{$_('setup.cameras.pick', { default: 'Cameras to watch' })}</legend>
                <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    {#each choices as choice (choice.camera)}
                        <label class="block cursor-pointer space-y-2 rounded-xl border p-2 {selected.includes(choice.camera) ? 'border-brand-500' : 'border-slate-200 dark:border-slate-700'}">
                            <div aria-hidden="true"><CameraThumbnail camera={choice.camera} showName={false} /></div>
                            <span class="flex min-h-11 items-center gap-2 text-sm font-medium text-slate-800 dark:text-slate-100">
                                <input type="checkbox" checked={selected.includes(choice.camera)} onchange={(event) => toggle(choice.camera, event.currentTarget.checked)} class="h-5 w-5 shrink-0 rounded border-slate-300 text-brand-600 focus:ring-brand-500" />
                                <span class="min-w-0 break-words">{choice.camera}</span>
                            </span>
                            {#if choice.missing}
                                <span class="block text-xs font-semibold text-amber-700 dark:text-amber-300" data-setup-camera-missing>{$_('setup.cameras.not_in_frigate', { default: 'Frigate has no camera with this name, so it will never see a bird.' })}</span>
                            {/if}
                        </label>
                    {/each}
                </div>
                <p role="status" class="text-xs leading-relaxed text-slate-500 dark:text-slate-400" data-setup-camera-summary>
                    {#if selected.length === 0}
                        {$_('setup.cameras.watching_all', { default: 'Watching every camera, including any you add to Frigate later. Tick cameras to watch only those.' })}
                    {:else}
                        {$_('setup.cameras.watching_some', { values: { count: selected.length }, default: '{count, plural, one {Watching # camera.} other {Watching # cameras.}} Other cameras are ignored.' })}
                    {/if}
                </p>
            </fieldset>
        {:else}
            <div>
                <label for="setup-cameras" class="text-sm font-medium text-slate-700 dark:text-slate-300">{$_('setup.cameras.list', { default: 'Cameras (comma-separated)' })}</label>
                <input id="setup-cameras" type="text" placeholder="feeder, nestbox" bind:value={camerasText} class="input-base mt-1" />
                <p class="mt-1 text-xs font-semibold text-amber-700 dark:text-amber-300" role="status" data-setup-camera-unread>{$_('setup.cameras.list_unread', { default: "Frigate's camera list could not be read, so these names cannot be checked. A name that does not match exactly never sees a bird. Leave this empty to watch every camera." })}</p>
                <button type="button" class="btn btn-secondary mt-2 min-h-11 px-4" disabled={retrying} onclick={retryFrigate}>{$_('setup.cameras.retry', { default: "Read Frigate's cameras again" })}</button>
            </div>
        {/if}

        <div class="flex items-start gap-2 rounded-lg bg-slate-50 p-3 text-xs text-slate-600 dark:bg-slate-800/50 dark:text-slate-300">
            <svg class="mt-0.5 h-4 w-4 shrink-0 text-brand-600 dark:text-brand-300" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 18h6M10 22h4M8.5 14.5A7 7 0 1 1 15.5 14.5C14.5 15.2 14 16 14 17h-4c0-1-.5-1.8-1.5-2.5Z" /></svg>
            <span>
                {$_('setup.cameras.gates_hint', { default: "Missing detections? Frigate's own min_score / threshold / min_initialized gates decide whether a snapshot ever reaches YA-WAMF." })}
                <a href={DOCS_URL} target="_blank" rel="noopener noreferrer" class="font-semibold text-brand-600 underline dark:text-brand-400">{$_('setup.cameras.gates_link', { default: 'Tuning guide →' })}</a>
            </span>
        </div>
    </WizardLoadState>
</WizardStepLayout>
