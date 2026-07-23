<script lang="ts">
    import { _ } from 'svelte-i18n';
    import { setupWizardStore } from '../../stores/setup_wizard.svelte';
    import { onMount } from 'svelte';
    import type { Snippet } from 'svelte';

    interface Props {
        title: string;
        description?: string;
        canContinue?: boolean;
        continueLabel?: string;
        showBack?: boolean;
        showSkip?: boolean;
        busy?: boolean;
        onContinue?: () => void | Promise<void>;
        children: Snippet;
    }

    let {
        title,
        description = '',
        canContinue = true,
        continueLabel = '',
        showBack = true,
        showSkip = false,
        busy = false,
        onContinue,
        children
    }: Props = $props();

    let actionError = $state('');
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
        actionError = '';
        setupWizardStore.leaveStep();
    }

    function skip(): void {
        actionError = '';
        setupWizardStore.skipStep();
    }
</script>

<div class="space-y-6">
    <div class="space-y-1">
        <h2 bind:this={heading} tabindex="-1" class="text-2xl font-bold text-slate-900 outline-none dark:text-white">{title}</h2>
        {#if description}
            <p class="text-sm text-slate-600 dark:text-slate-300">{description}</p>
        {/if}
    </div>

    <div class="space-y-4">
        {@render children()}
    </div>

    {#if actionError}
        <div role="alert" class="border-l-2 border-rose-500 bg-rose-50/70 px-3 py-2 text-sm text-rose-800 dark:bg-rose-950/20 dark:text-rose-200">
            {actionError}
        </div>
    {/if}

    <div class="flex items-center justify-between border-t border-slate-200 pt-4 dark:border-slate-700">
        <div>
            {#if showBack && !setupWizardStore.isFirst}
                <button type="button" class="btn btn-ghost min-h-11 px-4 py-2.5" onclick={leave}>
                    {$_('setup.back', { default: 'Back' })}
                </button>
            {/if}
        </div>
        <div class="flex items-center gap-2">
            {#if showSkip}
                <button type="button" class="btn btn-ghost min-h-11 px-4 py-2.5" onclick={skip}>
                    {$_('setup.skip', { default: 'Skip' })}
                </button>
            {/if}
            <button
                type="button"
                class="btn btn-primary min-h-11 px-6 py-2.5"
                disabled={busy || !canContinue}
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
