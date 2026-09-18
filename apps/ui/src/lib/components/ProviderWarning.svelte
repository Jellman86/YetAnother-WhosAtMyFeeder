<script lang="ts">
    import { providerNeedsAttention } from '../utils/provider-warning';
    import { _ } from 'svelte-i18n';
    import { authStore } from '../stores/auth.svelte';
    import { fetchClassifierStatus, fetchProviderValidationStatus, type ClassifierStatus, type ProviderValidationStatus } from '../api/classifier';

    let { onnavigate }: { onnavigate?: (path: string) => void } = $props();
    let classifier = $state<ClassifierStatus | null>(null);
    let validation = $state<ProviderValidationStatus | null>(null);
    const checking = $derived(validation?.state === 'running');
    const fallback = $derived(providerNeedsAttention(classifier));

    $effect(() => {
        if (!authStore.hasOwnerAccess) return;
        let cancelled = false;
        let timer: ReturnType<typeof setTimeout>;
        async function refresh(): Promise<void> {
            try {
                const [nextClassifier, nextValidation] = await Promise.all([fetchClassifierStatus(), fetchProviderValidationStatus()]);
                if (!cancelled) {
                    classifier = nextClassifier;
                    validation = nextValidation;
                }
            } catch {
                // Retain the last measured warning during a transient outage.
            } finally {
                if (!cancelled) timer = setTimeout(() => void refresh(), 15000);
            }
        }
        void refresh();
        return () => { cancelled = true; clearTimeout(timer); };
    });
</script>

{#if authStore.hasOwnerAccess && (checking || fallback)}
    <aside class="card-base border-amber-400/50 p-4" role="status" data-provider-warning>
        <p class="font-semibold text-amber-800 dark:text-amber-200">
            {checking
                ? $_('dashboard.provider_checking', { default: 'Checking your accelerator after a runtime change' })
                : $_('dashboard.provider_fallback', { default: 'Your selected inference provider is not running' })}
        </p>
        <p class="mt-1 text-sm text-slate-600 dark:text-slate-300">
            {checking
                ? $_('dashboard.provider_checking_detail', { default: 'This check runs once. The classifier reloads automatically if the accelerator passes.' })
                : classifier?.fallback_reason ?? $_('dashboard.provider_review', { default: 'Review model and provider' })}
        </p>
        <button class="btn btn-secondary mt-3 min-h-11" onclick={() => onnavigate?.('/settings/detection')}>
            {$_('dashboard.provider_review', { default: 'Review model and provider' })}
        </button>
    </aside>
{/if}
