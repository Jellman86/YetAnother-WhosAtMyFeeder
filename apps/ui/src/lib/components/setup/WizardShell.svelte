<script lang="ts">
    import { onMount } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { fade } from 'svelte/transition';
    import { setupWizardStore } from '../../stores/setup_wizard.svelte';
    import WelcomeStep from './WelcomeStep.svelte';
    import AccountStep from './AccountStep.svelte';
    import ConnectionStep from './ConnectionStep.svelte';
    import CamerasStep from './CamerasStep.svelte';
    import ModelStep from './ModelStep.svelte';
    import QualityStep from './QualityStep.svelte';
    import IntegrationsStep from './IntegrationsStep.svelte';
    import ReviewStep from './ReviewStep.svelte';

    const STEP_ICONS: Record<string, string> = {
        welcome: '👋',
        account: '🔐',
        connection: '🔗',
        cameras: '📷',
        model: '🧠',
        quality: '✨',
        integrations: '🧩',
        review: '✅'
    };

    let step = $derived(setupWizardStore.current);
    let index = $derived(setupWizardStore.index);
    let progressPct = $derived(Math.round(setupWizardStore.progress * 100));
    let canExit = $derived(setupWizardStore.mode === 'rerun');
    let steps = $derived(setupWizardStore.steps);

    onMount(() => {
        const previousOverflow = document.body.style.overflow;
        document.body.style.overflow = 'hidden';
        return () => {
            document.body.style.overflow = previousOverflow;
        };
    });
</script>

<div class="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-gradient-to-br from-slate-900/60 to-teal-950/50 p-4 backdrop-blur-sm">
    <div class="my-8 w-full max-w-2xl overflow-hidden rounded-3xl border border-white/10 bg-white shadow-2xl ring-1 ring-black/5 dark:bg-slate-900">
        <!-- Header -->
        <div class="space-y-3 bg-gradient-to-r from-teal-50 via-emerald-50 to-white px-6 py-4 dark:from-teal-950/40 dark:via-emerald-950/20 dark:to-slate-900">
            <div class="flex items-center justify-between">
                <span class="flex items-center gap-1.5 text-sm font-black tracking-tight text-teal-700 dark:text-teal-300">
                    <span aria-hidden="true">🐦</span> YA-WAMF
                </span>
                <div class="flex items-center gap-3">
                    <span class="text-xs font-semibold text-slate-500 dark:text-slate-400">
                        {$_('setup.step_of', { values: { n: setupWizardStore.position, total: setupWizardStore.total }, default: `Step ${setupWizardStore.position} of ${setupWizardStore.total}` })}
                    </span>
                    {#if canExit}
                        <button type="button" class="rounded-lg p-1 text-slate-400 hover:bg-slate-200/60 hover:text-slate-600 dark:hover:bg-slate-700/60 dark:hover:text-slate-200" aria-label={$_('setup.exit', { default: 'Exit setup' })} onclick={() => setupWizardStore.close()}>
                            <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
                        </button>
                    {/if}
                </div>
            </div>

            <!-- Step dots -->
            <div class="flex items-center gap-1.5">
                {#each steps as s, i}
                    <div
                        class="h-1.5 flex-1 rounded-full transition-colors duration-300 {i < index ? 'bg-teal-500' : i === index ? 'bg-teal-400' : 'bg-slate-200 dark:bg-slate-700'}"
                        title={s.id}
                    ></div>
                {/each}
            </div>
            <span class="sr-only" role="progressbar" aria-valuenow={progressPct} aria-valuemin="0" aria-valuemax="100">{progressPct}%</span>
        </div>

        <!-- Body -->
        <div class="max-h-[70vh] overflow-y-auto p-6" aria-live="polite">
            {#key step.id}
                <div in:fade={{ duration: 180 }}>
                    <div class="mb-4 flex items-center gap-2 text-3xl" aria-hidden="true">{STEP_ICONS[step.id]}</div>
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
            {/key}
        </div>
    </div>
</div>
