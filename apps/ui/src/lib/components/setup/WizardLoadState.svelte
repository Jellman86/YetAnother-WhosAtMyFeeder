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
    <div role="status" aria-live="polite" class="flex min-h-28 items-center justify-center gap-3 text-sm text-muted">
        <span class="h-5 w-5 animate-spin rounded-full border-2 border-accent-line/30 border-t-accent" aria-hidden="true"></span>
        {$_('setup.load.loading', { default: 'Loading your saved settings…' })}
    </div>
{:else if state === 'error'}
    <div role="alert" class="space-y-3 border-l-2 border-status-fail-line bg-status-fail-soft px-4 py-3 text-sm text-status-fail">
        <p>{$_('setup.load.failed', { default: 'Saved settings could not be loaded. Nothing has been changed.' })}</p>
        <button type="button" class="btn btn-secondary min-h-11 px-4 py-2" onclick={onRetry}>
            {$_('setup.load.retry', { default: 'Retry loading settings' })}
        </button>
    </div>
{:else}
    {@render children()}
{/if}
