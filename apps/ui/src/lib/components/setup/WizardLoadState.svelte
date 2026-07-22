<script lang="ts">
    import { _ } from 'svelte-i18n';
    import type { Snippet } from 'svelte';

    export type WizardLoadStatus = 'loading' | 'ready' | 'error';

    let {
        state,
        onRetry,
        children
    }: {
        state: WizardLoadStatus;
        onRetry: () => void | Promise<void>;
        children: Snippet;
    } = $props();
</script>

{#if state === 'loading'}
    <div role="status" aria-live="polite" class="flex min-h-28 items-center justify-center gap-3 text-sm text-slate-500 dark:text-slate-400">
        <span class="h-5 w-5 animate-spin rounded-full border-2 border-brand-200 border-t-brand-600" aria-hidden="true"></span>
        {$_('setup.load.loading', { default: 'Loading your saved settings…' })}
    </div>
{:else if state === 'error'}
    <div role="alert" class="space-y-3 border-l-2 border-rose-500 bg-rose-50/70 px-4 py-3 text-sm text-rose-800 dark:bg-rose-950/20 dark:text-rose-200">
        <p>{$_('setup.load.failed', { default: 'Saved settings could not be loaded. Nothing has been changed.' })}</p>
        <button type="button" class="btn btn-secondary min-h-11 px-4 py-2" onclick={onRetry}>
            {$_('setup.load.retry', { default: 'Retry loading settings' })}
        </button>
    </div>
{:else}
    {@render children()}
{/if}
