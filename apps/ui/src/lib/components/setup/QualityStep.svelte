<script lang="ts">
    import { onMount } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { fetchSettings, updateSettings } from '../../api/settings';
    import { setupWizardStore } from '../../stores/setup_wizard.svelte';
    import WizardStepLayout from './WizardStepLayout.svelte';
    import WizardLoadState, { type WizardLoadStatus } from './WizardLoadState.svelte';

    let hqSnapshots = $state(true);
    let loadState = $state<WizardLoadStatus>('loading');
    let busy = $state(false);

    async function load(): Promise<void> {
        loadState = 'loading';
        try {
            const s = await fetchSettings();
            hqSnapshots = s.media_cache_high_quality_event_snapshots ?? true;
        } catch {
            loadState = 'error';
            return;
        }
        loadState = 'ready';
    }

    onMount(() => {
        void load();
    });

    async function save() {
        if (loadState !== 'ready') return;
        busy = true;
        try {
            await updateSettings({
                media_cache_high_quality_event_snapshots: hqSnapshots
            });
            await setupWizardStore.refresh();
            setupWizardStore.completeStep();
        } finally {
            busy = false;
        }
    }
</script>

<WizardStepLayout
    title={$_('setup.quality.title', { default: 'Best available snapshots' })}
    description={$_('setup.quality.description', {
        default: 'YA-WAMF can automatically choose the clearest recorded frame and strongest reliable bird crop after each event.'
    })}
    showSkip
    canContinue={loadState === 'ready'}
    {busy}
    onContinue={save}
>
    <WizardLoadState state={loadState} onRetry={load}>
        <label class="flex min-h-12 items-start gap-3 rounded-xl border border-slate-200/80 px-4 py-3 text-sm text-slate-700 dark:border-slate-700 dark:text-slate-300">
            <input type="checkbox" bind:checked={hqSnapshots} class="mt-0.5 rounded border-slate-300 text-brand-600 focus:ring-brand-500" />
            <span>
                <span class="block font-semibold text-slate-900 dark:text-white">
                    {$_('settings.data.cache_high_quality_event_snapshots', { default: 'Best available event snapshots' })}
                </span>
                <span class="mt-1 block leading-relaxed text-slate-500 dark:text-slate-400">
                    {$_('settings.data.cache_high_quality_event_snapshots_help', { default: 'Accurate crop, fast crop, tracked-object hint, then the clear full frame — selected automatically.' })}
                </span>
            </span>
        </label>
    </WizardLoadState>
</WizardStepLayout>
