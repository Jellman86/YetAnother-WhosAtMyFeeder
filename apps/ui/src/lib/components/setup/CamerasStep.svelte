<script lang="ts">
    import { onMount } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { fetchSettings, updateSettings } from '../../api/settings';
    import { fetchEventFilters } from '../../api/events';
    import { setupWizardStore } from '../../stores/setup_wizard.svelte';
    import WizardStepLayout from './WizardStepLayout.svelte';
    import WizardLoadState, { type WizardLoadStatus } from './WizardLoadState.svelte';
    import CameraThumbnail from './CameraThumbnail.svelte';

    const DOCS_URL = 'https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/blob/main/docs/troubleshooting/frigate-event-not-found.md';

    let camerasText = $state('');
    let previewCameras = $state<string[]>([]);
    let detectedCameras = $state<string[]>([]);
    let loadState = $state<WizardLoadStatus>('loading');
    let busy = $state(false);

    // When the list is empty, YA-WAMF monitors all cameras — preview the ones actually
    // producing detections so the step isn't blank.
    let usingDetected = $derived(previewCameras.length === 0 && detectedCameras.length > 0);
    let previewList = $derived(previewCameras.length ? previewCameras : detectedCameras);

    function parseCameras(text: string): string[] {
        return text.split(',').map((c) => c.trim()).filter(Boolean);
    }

    function refreshPreview() {
        previewCameras = parseCameras(camerasText);
    }

    function useDetected() {
        camerasText = detectedCameras.join(', ');
        refreshPreview();
    }

    async function load(): Promise<void> {
        loadState = 'loading';
        const [settingsResult, filtersResult] = await Promise.allSettled([
            fetchSettings(),
            fetchEventFilters()
        ]);
        if (settingsResult.status === 'rejected') {
            loadState = 'error';
            return;
        }
        camerasText = (settingsResult.value.cameras ?? []).join(', ');
        refreshPreview();
        detectedCameras = filtersResult.status === 'fulfilled'
            ? (filtersResult.value.cameras ?? []).filter(Boolean)
            : [];
        loadState = 'ready';
    }

    onMount(() => {
        void load();
    });

    async function save() {
        if (loadState !== 'ready') return;
        busy = true;
        try {
            await updateSettings({ cameras: parseCameras(camerasText) });
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
        <div>
            <label for="setup-cameras" class="text-sm font-medium text-slate-700 dark:text-slate-300">{$_('setup.cameras.list', { default: 'Cameras (comma-separated)' })}</label>
            <input id="setup-cameras" type="text" placeholder="feeder, nestbox" bind:value={camerasText} onblur={refreshPreview} class="input-base mt-1" />
            <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">{$_('setup.cameras.list_hint', { default: 'Use the exact camera names from your Frigate config.' })}</p>
        </div>

        {#if usingDetected}
            <div class="flex items-center justify-between gap-2 rounded-lg bg-brand-50 px-3 py-2 text-xs text-brand-800 dark:bg-brand-950/30 dark:text-brand-200">
                <span>{$_('setup.cameras.detected_note', { default: 'No camera list set — YA-WAMF is watching all cameras. These are producing detections:' })}</span>
                <button type="button" class="btn btn-secondary px-3 py-1.5 shrink-0" onclick={useDetected}>{$_('setup.cameras.use_detected', { default: 'Add these' })}</button>
            </div>
        {/if}

        {#if previewList.length}
            <div class="grid grid-cols-2 gap-3 sm:grid-cols-3">
                {#each previewList as cam (cam)}
                    <CameraThumbnail camera={cam} />
                {/each}
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
