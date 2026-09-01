<script lang="ts">
    import { onMount } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { analysisQueueStatusStore } from '../stores/analysis_queue_status.svelte';
    import { authStore } from '../stores/auth.svelte';
    import { resetVideoCircuit } from '../api/maintenance';
    import { formatDateTime } from '../utils/datetime';

    let isOwner = $derived(authStore.showSettings);
    let analysisStatus = $derived(analysisQueueStatusStore.analysisStatus);
    let circuitOpen = $derived(isOwner && Boolean(analysisStatus?.circuit_open));
    let circuitOpenUntil = $derived(analysisStatus?.open_until ?? null);
    let failureCount = $derived(Math.max(0, Math.floor(Number(analysisStatus?.failure_count ?? 0))));
    let queuedJobs = $derived(
        Math.max(0, Math.floor(Number(analysisStatus?.pending ?? analysisQueueStatusStore.queueByKind.reclassify?.queued ?? 0)))
    );

    let resetting = $state(false);
    let resetError = $state<string | null>(null);

    // The status is normally kept current by the event stream. A paused queue that started
    // before this page opened would otherwise stay invisible until the next event arrives.
    onMount(() => {
        if (authStore.showSettings) void analysisQueueStatusStore.refresh();
    });

    async function handleReset() {
        if (resetting) return;
        resetting = true;
        resetError = null;
        try {
            await resetVideoCircuit();
            await analysisQueueStatusStore.refresh();
        } catch {
            resetError = $_('jobs.circuit_reset_failed', {
                default: 'The queue could not be resumed. Try again.'
            });
        } finally {
            resetting = false;
        }
    }
</script>

{#if circuitOpen}
    <div
        class="rounded-2xl border border-amber-200/80 dark:border-amber-800/60 bg-amber-50/80 dark:bg-amber-950/30 px-4 py-3"
        data-job-circuit-banner
    >
        <p class="text-sm font-semibold text-amber-900 dark:text-amber-100">
            {$_('jobs.circuit_open_message', { default: 'Reclassification queue paused by circuit breaker.' })}
        </p>
        <p class="mt-1 text-xs text-amber-700/90 dark:text-amber-200/90">
            {$_('jobs.circuit_open_detail', {
                values: {
                    queued: queuedJobs.toLocaleString(),
                    failures: failureCount.toLocaleString()
                },
                default: '{queued} queued items are waiting. Recent failures: {failures}.'
            })}
            {#if circuitOpenUntil}
                · {$_('jobs.circuit_open_until', { default: 'Until' })}: {formatDateTime(circuitOpenUntil)}
            {/if}
        </p>
        <div class="mt-3">
            <button
                type="button"
                onclick={handleReset}
                disabled={resetting}
                aria-label={$_('jobs.circuit_reset_button', { default: 'Try again' })}
                class="btn btn-secondary min-h-11 px-4 text-sm"
            >
                {#if resetting}
                    <svg class="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                {/if}
                {$_('jobs.circuit_reset_button', { default: 'Try again' })}
            </button>
            <p class="mt-1 text-[10px] text-amber-600/80 dark:text-amber-300/70">
                {$_('jobs.circuit_reset_confirm', { default: 'This will reopen the video classification queue immediately. Queued jobs will retry.' })}
            </p>
            {#if resetError}
                <p class="mt-2 text-xs font-semibold text-rose-700 dark:text-rose-300" role="alert">{resetError}</p>
            {/if}
        </div>
    </div>
{/if}
