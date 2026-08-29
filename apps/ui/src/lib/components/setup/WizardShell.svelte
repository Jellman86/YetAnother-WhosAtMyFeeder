<script lang="ts">
    import { onMount } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { fade } from 'svelte/transition';
    import { trapFocus } from '../../utils/focus-trap';
    import { portal } from '../../utils/portal';
    import { setupWizardStore } from '../../stores/setup_wizard.svelte';
    import { authStore } from '../../stores/auth.svelte';
    import BrandMark from '../BrandMark.svelte';
    import WelcomeStep from './WelcomeStep.svelte';
    import AccountStep from './AccountStep.svelte';
    import ConnectionStep from './ConnectionStep.svelte';
    import CamerasStep from './CamerasStep.svelte';
    import ModelStep from './ModelStep.svelte';
    import QualityStep from './QualityStep.svelte';
    import IntegrationsStep from './IntegrationsStep.svelte';
    import HistoryStep from './HistoryStep.svelte';
    import TelemetryStep from './TelemetryStep.svelte';
    import ReviewStep from './ReviewStep.svelte';
    import SetupStepIcon from './SetupStepIcon.svelte';

    let step = $derived(setupWizardStore.current);
    let index = $derived(setupWizardStore.index);
    let progressPct = $derived(Math.round(setupWizardStore.progress * 100));
    let canExit = $derived(setupWizardStore.mode === 'rerun');
    let steps = $derived(setupWizardStore.steps);
    let modalElement = $state<HTMLElement | null>(null);
    let previouslyFocused: HTMLElement | null = null;
    let skipConfirming = $state(false);
    let skipBusy = $state(false);
    let skipError = $state<string | null>(null);

    // Skipping is honest about its one consequence: leaving first-run before
    // the account step runs the app without a password until one is set in
    // Settings. Everything else the wizard covers is configurable later, and
    // the wizard itself can be re-run from Settings at any time.
    async function skipSetup(): Promise<void> {
        skipBusy = true;
        skipError = null;
        try {
            if (authStore.needsInitialSetup) {
                await authStore.completeInitialSetup({ username: 'admin', password: null, enableAuth: false });
            }
            setupWizardStore.close();
        } catch (err) {
            skipError = err instanceof Error ? err.message : $_('setup.skip_failed', { default: 'Skipping failed — the server could not be reached.' });
        } finally {
            skipBusy = false;
        }
    }

    onMount(() => {
        const previousOverflow = document.body.style.overflow;
        previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null;
        document.body.style.overflow = 'hidden';
        const releaseFocus = modalElement ? trapFocus(modalElement) : () => {};
        return () => {
            releaseFocus();
            document.body.style.overflow = previousOverflow;
            previouslyFocused?.focus();
        };
    });

    function handleKeydown(event: KeyboardEvent): void {
        if (
            event.key === 'Escape'
            && canExit
            && modalElement?.contains(event.target as Node)
        ) {
            event.preventDefault();
            setupWizardStore.close();
        }
    }
</script>

<svelte:window onkeydown={handleKeydown} />

<div use:portal role="presentation" class="fixed inset-0 z-[70] flex items-center justify-center overflow-y-auto bg-gradient-to-br from-slate-900/60 to-brand-950/50 p-4 backdrop-blur-sm">
    <div
        bind:this={modalElement}
        role="dialog"
        aria-modal="true"
        aria-label={$_('nav.setup_wizard', { default: 'Setup wizard' })}
        tabindex="-1"
        class="my-8 w-full max-w-2xl overflow-hidden rounded-3xl border border-white/10 bg-white shadow-2xl ring-1 ring-black/5 dark:bg-slate-900"
    >
        <!-- Header -->
        <div class="space-y-3 bg-gradient-to-r from-brand-50 via-accent-50 to-white px-6 py-4 dark:from-brand-950/40 dark:via-accent-950/20 dark:to-slate-900">
            <div class="flex items-center justify-between">
                <span class="flex items-center gap-1.5 text-sm font-black tracking-tight text-brand-700 dark:text-brand-300">
                    <BrandMark alt="" class="h-6 w-6" width={24} height={24} sizes="24px" /> YA-WAMF
                </span>
                <div class="flex items-center gap-3">
                    <span class="text-xs font-semibold text-slate-500 dark:text-slate-400">
                        {$_('setup.step_of', { values: { n: setupWizardStore.position, total: setupWizardStore.total }, default: `Step ${setupWizardStore.position} of ${setupWizardStore.total}` })}
                    </span>
                    {#if canExit}
                        <button type="button" class="flex h-11 w-11 items-center justify-center rounded-full text-slate-400 hover:bg-slate-200/60 hover:text-slate-600 focus:outline-none focus:ring-2 focus:ring-brand-500 dark:hover:bg-slate-700/60 dark:hover:text-slate-200" aria-label={$_('setup.exit', { default: 'Exit setup' })} onclick={() => setupWizardStore.close()}>
                            <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
                        </button>
                    {:else}
                        <button
                            type="button"
                            class="min-h-11 rounded-full px-3 text-xs font-bold text-slate-500 hover:bg-slate-200/60 hover:text-slate-700 focus:outline-none focus:ring-2 focus:ring-brand-500 dark:text-slate-400 dark:hover:bg-slate-700/60 dark:hover:text-slate-200"
                            onclick={() => (skipConfirming = true)}
                        >
                            {$_('setup.skip', { default: 'Skip setup' })}
                        </button>
                    {/if}
                </div>
            </div>

            <!-- Step dots -->
            <div class="flex items-center gap-1.5" aria-hidden="true">
                {#each steps as s, i}
                    <div
                        class="h-1.5 flex-1 rounded-full transition-colors duration-300 {i < index ? 'bg-brand-500' : i === index ? 'bg-brand-400' : 'bg-slate-200 dark:bg-slate-700'}"
                        title={s.id}
                    ></div>
                {/each}
            </div>
            <span class="sr-only" role="progressbar" aria-valuenow={progressPct} aria-valuemin="0" aria-valuemax="100">{progressPct}%</span>
        </div>

        {#if skipConfirming}
            <div class="border-b border-slate-200 bg-amber-50/70 px-6 py-4 dark:border-slate-700 dark:bg-amber-950/20" role="alertdialog" aria-labelledby="skip-setup-title" aria-describedby="skip-setup-body">
                <p id="skip-setup-title" class="text-sm font-bold text-slate-900 dark:text-white">
                    {$_('setup.skip_confirm_title', { default: 'Skip setup and open the app?' })}
                </p>
                <p id="skip-setup-body" class="mt-1 text-sm leading-relaxed text-slate-600 dark:text-slate-300">
                    {#if authStore.needsInitialSetup}
                        {$_('setup.skip_confirm_body_no_account', { default: 'The app will run without a password until you set one under Settings → Security. Everything this wizard covers can be configured later, and you can re-run it any time from Settings → Setup wizard.' })}
                    {:else}
                        {$_('setup.skip_confirm_body', { default: 'Everything this wizard covers can be configured later, and you can re-run it any time from Settings → Setup wizard.' })}
                    {/if}
                </p>
                {#if skipError}
                    <p role="alert" class="mt-2 text-sm font-semibold text-red-600 dark:text-red-400">{skipError}</p>
                {/if}
                <div class="mt-3 flex flex-wrap gap-2">
                    <button type="button" class="btn btn-secondary min-h-11 px-4" disabled={skipBusy} onclick={() => { skipConfirming = false; skipError = null; }}>
                        {$_('common.cancel', { default: 'Cancel' })}
                    </button>
                    <button type="button" class="btn btn-primary min-h-11 px-4" disabled={skipBusy} onclick={skipSetup}>
                        {skipBusy ? $_('common.working', { default: 'Working…' }) : $_('setup.skip_confirm_action', { default: 'Skip and open the app' })}
                    </button>
                </div>
            </div>
        {/if}

        <!-- Body -->
        <div class="max-h-[70vh] overflow-y-auto p-6" aria-live="polite">
            {#key step.id}
                <div in:fade={{ duration: 180 }}>
                    <div class="mb-4"><SetupStepIcon step={step.id} /></div>
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
                    {:else if step.id === 'history'}
                        <HistoryStep />
                    {:else if step.id === 'telemetry'}
                        <TelemetryStep />
                    {:else if step.id === 'review'}
                        <ReviewStep />
                    {/if}
                </div>
            {/key}
        </div>
    </div>
</div>
