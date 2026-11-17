<script lang="ts">
    import { onMount } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { fetchSettings, updateSettings } from '../../api/settings';
    import { fetchFrigateConfig } from '../../api/system';
    import { setupWizardStore } from '../../stores/setup_wizard.svelte';
    import WizardStepLayout from './WizardStepLayout.svelte';
    import { loadBlockedReason } from './continue-blocked';
    import WizardLoadState, { type WizardLoadStatus } from './WizardLoadState.svelte';
    import CameraThumbnail from './CameraThumbnail.svelte';
    import { cameraChoices, parseCameraNames } from './camera-choices';
    import { FRIGATE_CAMERA_READ_LIMIT_MS, readCameraList, type CameraListRead } from './camera-list-read';

    const DOCS_URL = 'https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/blob/main/docs/troubleshooting/frigate-event-not-found.md';

    const READ_LIMIT_SECONDS = FRIGATE_CAMERA_READ_LIMIT_MS / 1000;

    let selected = $state<string[]>([]);
    let savedCameras = $state<string[]>([]);
    /** Frigate's list is read apart from the settings, so a Frigate that is down never holds the step. */
    let cameraRead = $state<CameraListRead>({ state: 'reading' });
    let camerasText = $state('');
    let loadState = $state<WizardLoadStatus>('loading');
    let busy = $state(false);
    let latestRead = 0;

    /** Null until Frigate's list is read: names can then only be typed, unchecked. */
    let frigateCameras = $derived(cameraRead.state === 'read' ? cameraRead.cameras : null);
    let choices = $derived(frigateCameras ? cameraChoices(frigateCameras, savedCameras) : []);
    let chosen = $derived(frigateCameras ? selected : parseCameraNames(camerasText));

    function toggle(camera: string, on: boolean): void {
        selected = on ? [...selected, camera] : selected.filter((name) => name !== camera);
    }

    async function readFrigateCameras(): Promise<void> {
        const read = ++latestRead;
        cameraRead = { state: 'reading' };
        const outcome = await readCameraList(fetchFrigateConfig);
        if (read === latestRead) cameraRead = outcome;
    }

    async function retryFrigate(): Promise<void> {
        // Names typed while Frigate could not be read become the ticked cameras once it can.
        const typed = parseCameraNames(camerasText);
        await readFrigateCameras();
        selected = typed;
        savedCameras = typed;
    }

    async function load(): Promise<void> {
        loadState = 'loading';
        void readFrigateCameras();
        try {
            savedCameras = (await fetchSettings()).cameras ?? [];
        } catch {
            loadState = 'error';
            return;
        }
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
    blockedReason={loadBlockedReason(loadState, $_)}
    {busy}
    onContinue={save}
>
    <WizardLoadState state={loadState} onRetry={load}>
        {#if frigateCameras}
            <fieldset class="space-y-3" data-setup-camera-choices>
                <legend class="text-sm font-medium text-ink">{$_('setup.cameras.pick', { default: 'Cameras to watch' })}</legend>
                <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    {#each choices as choice (choice.camera)}
                        <label class="block cursor-pointer space-y-2 rounded-xl border p-2 {selected.includes(choice.camera) ? 'border-accent-line ring-1 ring-accent-line' : 'border-line'}">
                            <div aria-hidden="true"><CameraThumbnail camera={choice.camera} showName={false} /></div>
                            <span class="flex min-h-11 items-center gap-2 text-sm font-medium text-strong">
                                <input type="checkbox" checked={selected.includes(choice.camera)} onchange={(event) => toggle(choice.camera, event.currentTarget.checked)} class="h-5 w-5 shrink-0 rounded-sm border-line-strong text-accent focus:ring-focus" />
                                <span class="min-w-0 wrap-break-word">{choice.camera}</span>
                            </span>
                            {#if choice.missing}
                                <span class="block text-xs font-semibold text-status-attention" data-setup-camera-missing>{$_('setup.cameras.not_in_frigate', { default: 'Frigate has no camera with this name, so it will never see a bird.' })}</span>
                            {/if}
                        </label>
                    {/each}
                </div>
                <p role="status" class="text-xs leading-relaxed text-muted" data-setup-camera-summary>
                    {#if selected.length === 0}
                        {$_('setup.cameras.watching_all', { default: 'Watching every camera, including any you add to Frigate later. Tick cameras to watch only those.' })}
                    {:else}
                        {$_('setup.cameras.watching_some', { values: { count: selected.length }, default: '{count, plural, one {Watching # camera.} other {Watching # cameras.}} Other cameras are ignored.' })}
                    {/if}
                </p>
            </fieldset>
        {:else if cameraRead.state === 'reading'}
            <p role="status" class="flex items-start gap-3 text-sm leading-relaxed text-ink" data-setup-camera-reading>
                <span class="mt-0.5 h-5 w-5 shrink-0 animate-spin rounded-full border-2 border-accent-line border-t-accent-ink motion-reduce:animate-none" aria-hidden="true"></span>
                <span>{$_('setup.cameras.reading', { values: { seconds: READ_LIMIT_SECONDS }, default: 'Asking Frigate for its cameras, for up to {seconds} seconds. You can continue without waiting: the cameras already saved stay as they are.' })}</span>
            </p>
        {:else}
            <div>
                <label for="setup-cameras" class="text-sm font-medium text-ink">{$_('setup.cameras.list', { default: 'Cameras (comma-separated)' })}</label>
                <input id="setup-cameras" type="text" placeholder="feeder, nestbox" bind:value={camerasText} class="input-base mt-1" />
                <p class="mt-1 text-xs font-semibold text-status-attention" role="status" data-setup-camera-unread>
                    {#if cameraRead.state === 'unavailable' && cameraRead.cause === 'timed_out'}
                        {$_('setup.cameras.list_timed_out', { values: { seconds: READ_LIMIT_SECONDS }, default: 'Frigate did not answer within {seconds} seconds, so these names cannot be checked. A name that does not match exactly never sees a bird. Leave this empty to watch every camera.' })}
                    {:else}
                        {$_('setup.cameras.list_unread', { default: "Frigate's camera list could not be read, so these names cannot be checked. A name that does not match exactly never sees a bird. Leave this empty to watch every camera." })}
                    {/if}
                </p>
                <button type="button" class="btn btn-secondary mt-2 min-h-11 px-4" onclick={retryFrigate}>{$_('setup.cameras.retry', { default: "Read Frigate's cameras again" })}</button>
            </div>
        {/if}

        <div class="flex items-start gap-2 rounded-lg bg-surface-raised p-3 text-xs text-muted">
            <svg class="mt-0.5 h-4 w-4 shrink-0 text-accent-ink" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 18h6M10 22h4M8.5 14.5A7 7 0 1 1 15.5 14.5C14.5 15.2 14 16 14 17h-4c0-1-.5-1.8-1.5-2.5Z" /></svg>
            <span>
                {$_('setup.cameras.gates_hint', { default: "Missing detections? Frigate's own min_score / threshold / min_initialized gates decide whether a snapshot ever reaches YA-WAMF." })}
                <a href={DOCS_URL} target="_blank" rel="noopener noreferrer" class="font-semibold text-accent-ink underline">{$_('setup.cameras.gates_link', { default: 'Tuning guide →' })}</a>
            </span>
        </div>
    </WizardLoadState>
</WizardStepLayout>
