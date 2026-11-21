<script lang="ts">
    import { _ } from 'svelte-i18n';
    import { setupWizardStore } from '../../stores/setup_wizard.svelte';
    import { onMount } from 'svelte';
    import type { Snippet } from 'svelte';
    import BrandMark from '../BrandMark.svelte';
    import SetupStepIcon from './SetupStepIcon.svelte';

    interface Props {
        title: string;
        description?: string;
        canContinue?: boolean;
        /** Why Continue is disabled, in words. Shown beside it whenever it cannot be pressed. */
        blockedReason?: string;
        continueLabel?: string;
        showBack?: boolean;
        showSkip?: boolean;
        /** What skipping does here, when "Skip step" would not say it. */
        skipLabel?: string;
        busy?: boolean;
        onContinue?: () => void | Promise<void>;
        children: Snippet;
    }

    let {
        title,
        description = '',
        canContinue = true,
        blockedReason = '',
        continueLabel = '',
        showBack = true,
        showSkip = false,
        skipLabel = '',
        busy = false,
        onContinue,
        children
    }: Props = $props();

    let actionError = $state('');
    // A disabled button that does not say why is a dead end; busy says its own reason on the button.
    let blocked = $derived(!busy && !canContinue && blockedReason !== '');
    let heading: HTMLHeadingElement | null = null;

    onMount(() => {
        heading?.focus();
    });

    async function proceed() {
        if (busy || !canContinue) return;
        actionError = '';
        try {
            if (onContinue) {
                await onContinue();
            } else {
                setupWizardStore.completeStep();
            }
        } catch (error) {
            actionError = error instanceof Error && error.message.trim()
                ? error.message
                : $_('setup.action_failed', { default: 'That change could not be saved. Check the details and try again.' });
        }
    }

    function leave(): void {
        if (busy) return;
        actionError = '';
        setupWizardStore.leaveStep();
    }

    function skip(): void {
        if (busy) return;
        actionError = '';
        setupWizardStore.skipStep();
    }
</script>

<!-- The step fills the card: what it says scrolls, and the actions below it never leave the card. -->
<div class="flex min-h-0 flex-1 flex-col">
    <div class="min-h-0 flex-1 space-y-6 overflow-y-auto p-6 short:space-y-4 short:p-4" data-setup-scroll>
        <!-- Setup opens under the app's own mark; each later step has an icon for what it sets up. On a
             screen held sideways the icon gives its room to the step's own controls. -->
        <div class="short:hidden" data-setup-step-icon>
            {#if setupWizardStore.current.id === 'welcome'}
                <BrandMark alt="" class="h-10 w-10 rounded-xl" width={40} height={40} sizes="40px" />
            {:else}
                <SetupStepIcon step={setupWizardStore.current.id} />
            {/if}
        </div>
        <div class="space-y-1">
            <!-- The heading takes focus on each step. On the first one the dialog is still being moved to
                 the body when this mounts, which drops focus, so the focus trap is told to start here too. -->
            <h2 bind:this={heading} tabindex="-1" data-initial-focus class="text-2xl font-bold text-strong outline-hidden short:text-xl">{title}</h2>
            {#if description}
                <p class="text-sm text-muted">{description}</p>
            {/if}
        </div>

        <div class="space-y-4">
            {@render children()}
        </div>

        {#if actionError}
            <div role="alert" class="border-l-2 border-status-fail-line bg-status-fail-soft px-3 py-2 text-sm text-status-fail">
                {actionError}
            </div>
        {/if}
    </div>

    <div class="shrink-0 space-y-2 border-t border-line px-6 py-4 short:space-y-1 short:py-2" data-setup-footer>
        {#if blocked}
            <p id="setup-continue-blocked" class="text-sm text-ink sm:text-right" data-setup-continue-blocked>
                {blockedReason}
            </p>
        {/if}
        <div class="flex flex-wrap items-center justify-between gap-2">
            <div>
                {#if showBack && !setupWizardStore.isFirst}
                    <button type="button" class="btn btn-ghost min-h-11 px-4 py-2.5" disabled={busy} onclick={leave}>
                        {$_('setup.back', { default: 'Back' })}
                    </button>
                {/if}
            </div>
            <div class="flex flex-wrap items-center justify-end gap-2">
                {#if showSkip}
                    <button type="button" class="btn btn-ghost min-h-11 px-4 py-2.5" disabled={busy} onclick={skip} data-setup-skip-step>
                        {skipLabel || $_('setup.skip_step', { default: 'Skip step' })}
                    </button>
                {/if}
                <button
                    type="button"
                    class="btn btn-primary min-h-11 px-6 py-2.5"
                    disabled={busy || !canContinue}
                    aria-describedby={blocked ? 'setup-continue-blocked' : undefined}
                    onclick={proceed}
                >
                    {#if busy}
                        {$_('setup.working', { default: 'Working…' })}
                    {:else}
                        {continueLabel || $_('setup.continue', { default: 'Continue' })}
                    {/if}
                </button>
            </div>
        </div>
    </div>
</div>
