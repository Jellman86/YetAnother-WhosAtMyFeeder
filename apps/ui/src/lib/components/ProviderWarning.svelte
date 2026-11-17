<script lang="ts">
    import { _ } from 'svelte-i18n';
    import { authStore } from '../stores/auth.svelte';
    import { systemStatusStore } from '../stores/system_status.svelte';

    let { onnavigate }: { onnavigate?: (path: string) => void } = $props();
    // The pushed status carries the model's provider and its accelerator check, so this asks nothing.
    const model = $derived(systemStatusStore.snapshot?.model ?? null);
    const checking = $derived(model?.validation_state === 'running');
    const fallback = $derived(model?.provider_fallback === true);
</script>

{#if authStore.hasOwnerAccess && (checking || fallback)}
    <aside class="card-base border-attention-400/50 p-4" role="status" data-provider-warning>
        <p class="font-semibold text-attention-800 dark:text-attention-200">
            {checking
                ? $_('dashboard.provider_checking', { default: 'Checking your accelerator after a runtime change' })
                : $_('dashboard.provider_fallback', { default: 'Your selected inference provider is not running' })}
        </p>
        <p class="mt-1 text-sm text-slate-600 dark:text-slate-300">
            {checking
                ? $_('dashboard.provider_checking_detail', { default: 'This check runs once. The classifier reloads automatically if the accelerator passes.' })
                : model?.fallback_reason ?? $_('dashboard.provider_review', { default: 'Review model and provider' })}
        </p>
        <button class="btn btn-secondary mt-3 min-h-11" onclick={() => onnavigate?.('/settings/models')}>
            {$_('dashboard.provider_review', { default: 'Review model and provider' })}
        </button>
    </aside>
{/if}
