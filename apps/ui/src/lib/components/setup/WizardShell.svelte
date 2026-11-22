<script lang="ts">
    import DialogCloseButton from '../DialogCloseButton.svelte';
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
    import ReviewStep from './ReviewStep.svelte';

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

    function stepName(id: string): string {
        return $_(`setup.step_names.${id}`, { default: id });
    }

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
            skipError = err instanceof Error ? err.message : $_('setup.skip_failed', { default: 'Setup could not be skipped because YA-WAMF did not answer. Check that it is running, then try again.' });
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

<div use:portal role="presentation" class="fixed inset-0 z-70 flex items-center justify-center bg-media/60 p-4 backdrop-blur-xs short:p-2">
    <div
        bind:this={modalElement}
        role="dialog"
        aria-modal="true"
        aria-label={$_('nav.setup_wizard', { default: 'Setup wizard' })}
        tabindex="-1"
        class="flex max-h-full w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-line bg-surface shadow-2xl"
    >
        <!-- Header -->
        <div class="space-y-3 bg-surface-raised px-6 py-4 short:space-y-1.5 short:py-2">
            <!-- Wraps: at a large text size the step name takes a line of its own under the brand. -->
            <div class="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
                <span class="flex items-center gap-1.5 text-sm font-bold tracking-tight text-accent-ink">
                    <BrandMark alt="" class="h-6 w-6" width={24} height={24} sizes="24px" /> YA-WAMF
                </span>
                <div class="flex min-w-0 items-center gap-3">
                    <span class="min-w-0 text-xs font-semibold text-muted wrap-break-word">
                        {$_('setup.step_of', { values: { n: setupWizardStore.position, total: setupWizardStore.total }, default: `Step ${setupWizardStore.position} of ${setupWizardStore.total}` })}
                        <span class="text-ink">· {stepName(step.id)}</span>
                    </span>
                    {#if canExit}
                        <DialogCloseButton label={$_('setup.exit', { default: 'Exit setup' })} onclick={() => setupWizardStore.close()} />
                    {:else}
                        <button
                            type="button"
                            class="min-h-11 rounded-full px-3 text-xs font-bold text-muted hover:bg-line hover:text-ink focus-ring"
                            onclick={() => (skipConfirming = true)}
                        >
                            {$_('setup.skip', { default: 'Skip setup' })}
                        </button>
                    {/if}
                </div>
            </div>

            <!-- The step bar is a list a screen reader can walk; the bars themselves are drawn, the names are read. -->
            <ol class="flex items-center gap-1.5" aria-label={$_('setup.step_list', { default: 'Setup steps' })}>
                {#each steps as s, i (s.id)}
                    <li
                        class="h-1.5 flex-1 rounded-full transition-colors duration-300 motion-reduce:transition-none {i < index ? 'bg-accent-line' : i === index ? 'bg-accent' : 'bg-track'}"
                        aria-current={i === index ? 'step' : undefined}
                    >
                        <span class="sr-only">{stepName(s.id)}</span>
                    </li>
                {/each}
            </ol>
            <span class="sr-only" role="progressbar" aria-label={$_('setup.progress', { default: 'Setup progress' })} aria-valuenow={progressPct} aria-valuemin="0" aria-valuemax="100">{progressPct}%</span>
        </div>

        {#if skipConfirming}
            <!-- At most half the card: its words scroll inside it and its two buttons stay put, so on a short
                 screen the step's own Back and Continue are never pushed out of the card either. -->
            <div class="flex max-h-half-screen shrink-0 flex-col border-b border-line bg-status-attention-soft" role="alertdialog" aria-labelledby="skip-setup-title" aria-describedby="skip-setup-body">
                <!-- A tab stop of its own, so the keyboard can scroll the words in every browser (Safari
                     does not focus a scrolling box that holds no control). -->
                <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
                <div class="min-h-0 overflow-y-auto px-6 pt-4 focus-ring short:pt-2" role="group" tabindex="0" aria-labelledby="skip-setup-title" data-skip-setup-text>
                    <p id="skip-setup-title" class="text-sm font-bold text-strong">
                        {$_('setup.skip_confirm_title', { default: 'Skip setup and open the app?' })}
                    </p>
                    <p id="skip-setup-body" class="mt-1 text-sm leading-relaxed text-muted">
                        {#if authStore.needsInitialSetup}
                            {$_('setup.skip_confirm_body_no_account', { default: 'The app will run without a password until you set one under Settings → Access & privacy. Everything this wizard covers can be configured later, and you can re-run it any time from Settings → Setup wizard.' })}
                        {:else}
                            {$_('setup.skip_confirm_body', { default: 'Everything this wizard covers can be configured later, and you can re-run it any time from Settings → Setup wizard.' })}
                        {/if}
                    </p>
                </div>
                <!-- Outside the scrolling words, just above the buttons, so a failed skip is seen where it was pressed. -->
                {#if skipError}
                    <p role="alert" class="shrink-0 px-6 pt-2 text-sm font-semibold text-status-fail" data-skip-setup-error>{skipError}</p>
                {/if}
                <div class="flex shrink-0 flex-wrap gap-2 px-6 pb-4 pt-3 short:pb-2 short:pt-2">
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
        <!-- Not a live region: each step focuses its own heading, which is what is announced. -->
        <!-- The card is as tall as the window allows and the step lays itself out inside it: its
             content scrolls and its Back / Continue row stays in view (WizardStepLayout). -->
        <div class="flex min-h-0 flex-1 flex-col">
            {#key step.id}
                <div class="flex min-h-0 flex-1 flex-col" in:fade={{ duration: 180 }}>
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
                    {:else if step.id === 'review'}
                        <ReviewStep />
                    {/if}
                </div>
            {/key}
        </div>
    </div>
</div>
