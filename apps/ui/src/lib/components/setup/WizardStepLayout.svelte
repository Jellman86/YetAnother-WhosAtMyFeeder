<script lang="ts">
    import { _ } from 'svelte-i18n';
    import { setupWizardStore } from '../../stores/setup_wizard.svelte';
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

    async function proceed() {
        if (busy || !canContinue) return;
        if (onContinue) {
            await onContinue();
        } else {
            setupWizardStore.next();
        }
    }
</script>

<div class="space-y-6">
    <div class="space-y-1">
        <h2 class="text-2xl font-bold text-slate-900 dark:text-white">{title}</h2>
        {#if description}
            <p class="text-sm text-slate-600 dark:text-slate-300">{description}</p>
        {/if}
    </div>

    <div class="space-y-4">
        {@render children()}
    </div>

    <div class="flex items-center justify-between border-t border-slate-200 pt-4 dark:border-slate-700">
        <div>
            {#if showBack && !setupWizardStore.isFirst}
                <button type="button" class="btn btn-ghost" onclick={() => setupWizardStore.back()}>
                    {$_('setup.back', { default: 'Back' })}
                </button>
            {/if}
        </div>
        <div class="flex items-center gap-2">
            {#if showSkip}
                <button type="button" class="btn btn-ghost" onclick={() => setupWizardStore.next()}>
                    {$_('setup.skip', { default: 'Skip' })}
                </button>
            {/if}
            <button
                type="button"
                class="btn btn-primary"
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
