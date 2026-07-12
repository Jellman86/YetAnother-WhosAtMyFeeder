<script lang="ts">
    import { _ } from 'svelte-i18n';
    import { setupWizardStore } from '../../stores/setup_wizard.svelte';
    import WelcomeStep from './WelcomeStep.svelte';
    import AccountStep from './AccountStep.svelte';
    import ConnectionStep from './ConnectionStep.svelte';
    import CamerasStep from './CamerasStep.svelte';
    import ModelStep from './ModelStep.svelte';
    import QualityStep from './QualityStep.svelte';
    import IntegrationsStep from './IntegrationsStep.svelte';
    import ReviewStep from './ReviewStep.svelte';

    let step = $derived(setupWizardStore.current);
    let progressPct = $derived(Math.round(setupWizardStore.progress * 100));
    let canExit = $derived(setupWizardStore.mode === 'rerun');
</script>

<div class="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-slate-900/50 p-4 backdrop-blur-sm">
    <div class="my-8 w-full max-w-2xl rounded-2xl border border-slate-200 bg-white shadow-xl dark:border-slate-700 dark:bg-slate-900">
        <div class="space-y-3 border-b border-slate-200 p-6 pb-4 dark:border-slate-700">
            <div class="flex items-center justify-between">
                <span class="text-sm font-black uppercase tracking-wider text-teal-600 dark:text-teal-400">YA-WAMF</span>
                <div class="flex items-center gap-3">
                    <span class="text-xs font-medium text-slate-500 dark:text-slate-400">
                        {$_('setup.step_of', { values: { n: setupWizardStore.position, total: setupWizardStore.total }, default: `Step ${setupWizardStore.position} of ${setupWizardStore.total}` })}
                    </span>
                    {#if canExit}
                        <button type="button" class="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200" aria-label={$_('setup.exit', { default: 'Exit setup' })} onclick={() => setupWizardStore.close()}>
                            <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
                        </button>
                    {/if}
                </div>
            </div>
            <div class="h-1.5 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700" role="progressbar" aria-valuenow={progressPct} aria-valuemin="0" aria-valuemax="100">
                <div class="h-full rounded-full bg-teal-500 transition-all duration-300" style="width: {progressPct}%"></div>
            </div>
        </div>

        <div class="p-6" aria-live="polite">
            {#if step.id === 'welcome'}
                <WelcomeStep />
            {:else if step.id === 'account'}
                <AccountStep />
            {:else if step.id === 'connection'}
                <ConnectionStep />
            {:else if step.id === 'cameras'}
                <CamerasStep />
            {:else if step.id === 'model'}
                <ModelStep />
            {:else if step.id === 'quality'}
                <QualityStep />
            {:else if step.id === 'integrations'}
                <IntegrationsStep />
            {:else if step.id === 'review'}
                <ReviewStep />
            {/if}
        </div>
    </div>
</div>
