<script lang="ts">
    import { onMount } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { fetchSettings, updateSettings } from '../../api/settings';
    import { setupWizardStore } from '../../stores/setup_wizard.svelte';
    import WizardStepLayout from './WizardStepLayout.svelte';
    import { loadBlockedReason } from './continue-blocked';
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
        default: 'After each visit, YA-WAMF can choose the clearest frame from the recording and the best close-up of the bird.'
    })}
    showSkip
    canContinue={loadState === 'ready'}
    blockedReason={loadBlockedReason(loadState, $_)}
    {busy}
    onContinue={save}
>
    <WizardLoadState state={loadState} onRetry={load}>
        <label class="flex min-h-12 items-start gap-3 rounded-xl border border-line px-4 py-3 text-sm text-ink">
            <input type="checkbox" bind:checked={hqSnapshots} class="mt-0.5 rounded-sm border-line-strong text-accent focus:ring-focus" />
            <span>
                <span class="block font-semibold text-strong">
                    {$_('settings.data.cache_high_quality_event_snapshots', { default: 'Best available event snapshots' })}
                </span>
                <span class="mt-1 block leading-relaxed text-muted">
                    {$_('settings.data.cache_high_quality_event_snapshots_help', { default: 'After an event ends, choose the clearest main-stream frame and best crop available. The full frame is kept when a reliable crop cannot be made.' })}
                </span>
            </span>
        </label>
    </WizardLoadState>
</WizardStepLayout>
