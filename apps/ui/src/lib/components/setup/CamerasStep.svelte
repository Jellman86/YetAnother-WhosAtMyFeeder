<script lang="ts">
    import { onMount } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { fetchSettings, updateSettings } from '../../api/settings';
    import { fetchEventFilters } from '../../api/events';
    import { setupWizardStore } from '../../stores/setup_wizard.svelte';
    import WizardStepLayout from './WizardStepLayout.svelte';
    import CameraThumbnail from './CameraThumbnail.svelte';

    const DOCS_URL = 'https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/blob/main/docs/troubleshooting/frigate-event-not-found.md';

    let camerasText = $state('');
    let threshold = $state(0.5);
    let previewCameras = $state<string[]>([]);
    let detectedCameras = $state<string[]>([]);
    let loaded = $state(false);
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

    onMount(async () => {
        try {
            const s = await fetchSettings();
            camerasText = (s.cameras ?? []).join(', ');
            threshold = s.classification_threshold ?? 0.5;
            refreshPreview();
        } catch {
            // Editable defaults remain.
        }
        try {
            const filters = await fetchEventFilters();
            detectedCameras = (filters.cameras ?? []).filter(Boolean);
        } catch {
            // No detected cameras yet — fine on a fresh install.
        }
        loaded = true;
    });

    async function save() {
        busy = true;
        try {
            await updateSettings({ cameras: parseCameras(camerasText), classification_threshold: threshold });
            await setupWizardStore.refresh();
            setupWizardStore.next();
        } finally {
            busy = false;
        }
    }
</script>

<WizardStepLayout
    title={$_('setup.cameras.title', { default: 'Cameras & detection' })}
    description={$_('setup.cameras.description', {
        default: 'Choose which Frigate cameras YA-WAMF watches, and how confident a classification must be to keep.'
    })}
    {busy}
    onContinue={save}
>
    {#if loaded}
        <div>
            <label for="setup-cameras" class="text-sm font-medium text-slate-700 dark:text-slate-300">{$_('setup.cameras.list', { default: 'Cameras (comma-separated)' })}</label>
            <input id="setup-cameras" type="text" placeholder="feeder, nestbox" bind:value={camerasText} onblur={refreshPreview} class="input-base mt-1" />
            <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">{$_('setup.cameras.list_hint', { default: 'Use the exact camera names from your Frigate config.' })}</p>
        </div>

        {#if usingDetected}
            <div class="flex items-center justify-between gap-2 rounded-lg bg-teal-50 px-3 py-2 text-xs text-teal-800 dark:bg-teal-950/30 dark:text-teal-200">
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

        <div>
            <label for="setup-threshold" class="text-sm font-medium text-slate-700 dark:text-slate-300">
                {$_('setup.cameras.threshold', { default: 'Confidence threshold' })}: <span class="font-bold text-teal-600 dark:text-teal-400">{(threshold * 100).toFixed(0)}%</span>
            </label>
            <input id="setup-threshold" type="range" min="0" max="1" step="0.05" bind:value={threshold} class="mt-2 w-full accent-teal-500" />
        </div>

        <div class="flex items-start gap-2 rounded-lg bg-slate-50 p-3 text-xs text-slate-600 dark:bg-slate-800/50 dark:text-slate-300">
            <span aria-hidden="true">💡</span>
            <span>
                {$_('setup.cameras.gates_hint', { default: "Missing detections? Frigate's own min_score / threshold / min_initialized gates decide whether a snapshot ever reaches YA-WAMF." })}
                <a href={DOCS_URL} target="_blank" rel="noopener noreferrer" class="font-semibold text-teal-600 underline dark:text-teal-400">{$_('setup.cameras.gates_link', { default: 'Tuning guide →' })}</a>
            </span>
        </div>
    {/if}
</WizardStepLayout>
