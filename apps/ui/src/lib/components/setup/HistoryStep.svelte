<script lang="ts">
    import { _ } from 'svelte-i18n';
    import { startBackfillJob } from '../../api/backfill';
    import { setupWizardStore } from '../../stores/setup_wizard.svelte';
    import { jobProgressStore } from '../../stores/job_progress.svelte';
    import WizardStepLayout from './WizardStepLayout.svelte';

    let importHistory = $state(false);
    let dateRange = $state<'day' | 'week' | 'month'>('day');
    let busy = $state(false);
    let continueLabel = $derived(importHistory
        ? $_('setup.history.import_continue', { default: 'Import & continue' })
        : $_('setup.history.continue_without', { default: 'Continue without importing' }));

    async function continueSetup(): Promise<void> {
        if (!importHistory) {
            setupWizardStore.completeStep();
            return;
        }

        busy = true;
        try {
            const job = await startBackfillJob({ date_range: dateRange });
            jobProgressStore.upsertRunning({
                id: `backfill:detections:${job.id}`,
                kind: 'backfill',
                title: $_('setup.history.job_title', { default: 'Detection history import' }),
                message: job.message || $_('setup.history.job_starting', { default: 'Scanning Frigate event history' }),
                route: '/jobs',
                current: job.processed,
                total: job.total,
                source: 'ui'
            });
            setupWizardStore.completeStep();
        } finally {
            busy = false;
        }
    }
</script>

<WizardStepLayout
    title={$_('setup.history.title', { default: 'Import existing detections' })}
    description={$_('setup.history.description', {
        default: 'Optionally classify bird events that Frigate still retains. The import runs safely in the background while you finish setup.'
    })}
    {busy}
    {continueLabel}
    onContinue={continueSetup}
>
    <label class="flex min-h-12 items-start gap-3 border-y border-slate-200/80 py-3 text-sm text-slate-700 dark:border-slate-700/70 dark:text-slate-300">
        <input type="checkbox" bind:checked={importHistory} class="mt-0.5 h-5 w-5 rounded border-slate-300 text-brand-600 focus:ring-brand-500" />
        <span>
            <span class="block font-semibold text-slate-900 dark:text-white">
                {$_('setup.history.enable', { default: 'Import retained Frigate bird events' })}
            </span>
            <span class="mt-1 block leading-relaxed text-slate-500 dark:text-slate-400">
                {$_('setup.history.enable_help', { default: 'Existing detections are updated only when classification quality improves; saved audio and weather context is preserved.' })}
            </span>
        </span>
    </label>

    {#if importHistory}
        <fieldset class="space-y-2 border-l-2 border-brand-100 pl-4 dark:border-brand-900/60">
            <legend class="text-sm font-medium text-slate-700 dark:text-slate-300">
                {$_('setup.history.range', { default: 'History window' })}
            </legend>
            <div class="grid grid-cols-3 gap-2">
                {#each [
                    { value: 'day', label: $_('settings.data.backfill_24h', { default: 'Last 24 hours' }) },
                    { value: 'week', label: $_('settings.data.backfill_week', { default: 'Last 7 days' }) },
                    { value: 'month', label: $_('settings.data.backfill_month', { default: 'Last 30 days' }) }
                ] as option}
                    <label class="cursor-pointer">
                        <input class="peer sr-only" type="radio" name="setup-history-range" value={option.value} bind:group={dateRange} />
                        <span class="btn btn-secondary flex min-h-11 items-center justify-center px-3 py-2 text-center peer-checked:border-brand-500 peer-checked:bg-brand-50 peer-checked:text-brand-800 peer-focus-visible:ring-2 peer-focus-visible:ring-brand-500/50 peer-focus-visible:ring-offset-2 peer-focus-visible:ring-offset-white dark:peer-checked:bg-brand-950/30 dark:peer-checked:text-brand-200 dark:peer-focus-visible:ring-offset-surface-dark">
                            {option.label}
                        </span>
                    </label>
                {/each}
            </div>
        </fieldset>
    {/if}

    <p class="flex items-start gap-2 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
        <svg class="mt-0.5 h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v4m0 4h.01M10.3 3.7 2.6 17a2 2 0 0 0 1.7 3h15.4a2 2 0 0 0 1.7-3L13.7 3.7a2 2 0 0 0-3.4 0Z" /></svg>
        <span>{$_('setup.history.audio_note', { default: 'Frigate history can restore visual detections and snapshots, but it cannot recreate BirdNET-Go audio that was not already stored.' })}</span>
    </p>
</WizardStepLayout>
