<script lang="ts">
    import { onMount } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { fetchSettings, updateSettings } from '../../api/settings';
    import { setupWizardStore } from '../../stores/setup_wizard.svelte';
    import WizardStepLayout from './WizardStepLayout.svelte';

    let hqSnapshots = $state(true);
    let hqBirdCrop = $state(true);
    let cropTier = $state<'fast' | 'accurate'>('fast');
    let loaded = $state(false);
    let busy = $state(false);

    onMount(async () => {
        try {
            const s = await fetchSettings();
            hqSnapshots = s.media_cache_high_quality_event_snapshots ?? true;
            hqBirdCrop = s.media_cache_high_quality_event_snapshot_bird_crop ?? true;
            cropTier = s.bird_crop_detector_tier === 'accurate' ? 'accurate' : 'fast';
        } catch {
            // Editable defaults remain.
        } finally {
            loaded = true;
        }
    });

    async function save() {
        busy = true;
        try {
            await updateSettings({
                media_cache_high_quality_event_snapshots: hqSnapshots,
                media_cache_high_quality_event_snapshot_bird_crop: hqBirdCrop,
                bird_crop_detector_tier: cropTier
            });
            await setupWizardStore.refresh();
            setupWizardStore.next();
        } finally {
            busy = false;
        }
    }
</script>

<WizardStepLayout
    title={$_('setup.quality.title', { default: 'Snapshot & crop quality' })}
    description={$_('setup.quality.description', {
        default: 'Higher-quality snapshots and bird crops improve classification and the gallery. These have sensible defaults — tune only if you want.'
    })}
    showSkip
    {busy}
    onContinue={save}
>
    {#if loaded}
        <label class="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
            <input type="checkbox" bind:checked={hqSnapshots} class="rounded border-slate-300 text-teal-600 focus:ring-teal-500" />
            {$_('setup.quality.hq_snapshots', { default: 'Fetch high-quality event snapshots' })}
        </label>
        <label class="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
            <input type="checkbox" bind:checked={hqBirdCrop} class="rounded border-slate-300 text-teal-600 focus:ring-teal-500" />
            {$_('setup.quality.hq_crop', { default: 'Generate a high-quality bird crop per detection' })}
        </label>
        <div>
            <label for="setup-crop-tier" class="text-sm font-medium text-slate-700 dark:text-slate-300">{$_('setup.quality.crop_tier', { default: 'Crop detector' })}</label>
            <select id="setup-crop-tier" bind:value={cropTier} class="select-base mt-1">
                <option value="fast">{$_('setup.quality.crop_fast', { default: 'Fast (default, CPU-friendly)' })}</option>
                <option value="accurate">{$_('setup.quality.crop_accurate', { default: 'Accurate (YOLOX-Tiny, optional)' })}</option>
            </select>
        </div>
    {/if}
</WizardStepLayout>
