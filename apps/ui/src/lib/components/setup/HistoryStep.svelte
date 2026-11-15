<script lang="ts">
    /**
     * The two optional choices that end setup, on one screen: importing what Frigate still
     * holds, and sharing anonymous usage stats. Neither is needed to see a bird.
     */
    import { onMount } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { fetchSettings, updateSettings } from '../../api/settings';
    import WizardLoadState, { type WizardLoadStatus } from './WizardLoadState.svelte';
    import { startBackfillJob } from '../../api/backfill';
    import { setupWizardStore } from '../../stores/setup_wizard.svelte';
    import { jobProgressStore } from '../../stores/job_progress.svelte';
    import WizardStepLayout from './WizardStepLayout.svelte';

    let importHistory = $state(false);
    let dateRange = $state<'day' | 'week' | 'month'>('day');
    let busy = $state(false);
    // Opt-in, off by default. This is the only place first run asks.
    let shareUsage = $state(false);
    let usageLoad = $state<WizardLoadStatus>('loading');
    let continueLabel = $derived(importHistory ? $_('setup.history.import_continue', { default: 'Import & continue' }) : '');

    async function loadUsageChoice(): Promise<void> {
        usageLoad = 'loading';
        try {
            shareUsage = (await fetchSettings()).telemetry_enabled ?? false;
            usageLoad = 'ready';
        } catch {
            usageLoad = 'error';
        }
    }

    onMount(() => {
        void loadUsageChoice();
    });

    async function continueSetup(): Promise<void> {
        busy = true;
        try {
            // A choice that never loaded is not saved: writing it would overwrite what is stored.
            if (usageLoad === 'ready') {
                await updateSettings({ telemetry_enabled: shareUsage });
                await setupWizardStore.refresh();
            }
            if (!importHistory) {
                setupWizardStore.completeStep();
                return;
            }
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
    title={$_('setup.extras.title', { default: 'Optional extras' })}
    description={$_('setup.extras.description', {
        default: 'Two choices before you finish. Both are off unless you turn them on, and both can be changed later in Settings.'
    })}
    canContinue={usageLoad !== 'loading'}
    blockedReason={$_('setup.blocked.loading', { default: 'Continue is available once the current settings have loaded.' })}
    {busy}
    {continueLabel}
    onContinue={continueSetup}
>
    <h3 class="text-sm font-bold text-slate-900 dark:text-white">{$_('setup.history.title', { default: 'Import existing detections' })}</h3>
    <p class="text-sm text-slate-600 dark:text-slate-300">{$_('setup.history.description', { default: 'Optionally classify bird events that Frigate still retains. The import runs safely in the background while you finish setup.' })}</p>
    <label class="flex min-h-12 items-start gap-3 border-y border-slate-200/80 py-3 text-sm text-slate-700 dark:border-slate-700/70 dark:text-slate-300">
        <input type="checkbox" bind:checked={importHistory} class="mt-0.5 h-5 w-5 rounded-sm border-slate-300 text-brand-600 focus:ring-focus" />
        <span>
            <span class="block font-semibold text-slate-900 dark:text-white">
                {$_('setup.history.enable', { default: 'Import retained Frigate bird events' })}
            </span>
            <span class="mt-1 block leading-relaxed text-slate-600 dark:text-slate-400">
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
                        <span class="btn btn-secondary flex min-h-11 items-center justify-center px-3 py-2 text-center peer-checked:border-brand-500 peer-checked:bg-brand-50 peer-checked:text-brand-800 peer-focus-visible:ring-2 peer-focus-visible:ring-focus peer-focus-visible:ring-offset-2 peer-focus-visible:ring-offset-white dark:peer-checked:bg-brand-950/30 dark:peer-checked:text-brand-200 dark:peer-focus-visible:ring-offset-surface-dark">
                            {option.label}
                        </span>
                    </label>
                {/each}
            </div>
        </fieldset>
    {/if}

    <p class="flex items-start gap-2 text-xs leading-relaxed text-slate-600 dark:text-slate-400">
        <svg class="mt-0.5 h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v4m0 4h.01M10.3 3.7 2.6 17a2 2 0 0 0 1.7 3h15.4a2 2 0 0 0 1.7-3L13.7 3.7a2 2 0 0 0-3.4 0Z" /></svg>
        <span>{$_('setup.history.audio_note', { default: 'Frigate history can restore visual detections and snapshots, but it cannot recreate BirdNET-Go audio that was not already stored.' })}</span>
    </p>

    <h3 class="border-t border-slate-200 pt-4 text-sm font-bold text-slate-900 dark:border-slate-700 dark:text-white">{$_('telemetry_banner.title', { default: 'Share anonymous usage stats?' })}</h3>
    <p class="text-sm text-slate-600 dark:text-slate-300">{$_('telemetry_banner.body', { default: 'They show which features actually get used, so time goes to the parts people rely on. Opt-in, no personal data, off by default.' })}</p>
    <WizardLoadState state={usageLoad} onRetry={loadUsageChoice}>
        <label class="flex min-h-12 items-start gap-3 border-y border-slate-200/80 py-3 text-sm text-slate-700 dark:border-slate-700/70 dark:text-slate-300">
            <input type="checkbox" bind:checked={shareUsage} class="mt-0.5 h-5 w-5 rounded-sm border-slate-300 text-brand-600 focus:ring-focus" />
            <span>
                <span class="block font-semibold text-slate-900 dark:text-white">{$_('setup.telemetry.opt_in', { default: 'Yes, share anonymous usage stats to help guide development.' })}</span>
                <span class="mt-1 block leading-relaxed text-slate-600 dark:text-slate-400">
                    {$_('setup.telemetry.note', { default: 'No personal data is collected, and you can change this any time in Settings.' })}
                </span>
            </span>
        </label>
        <a
            href="https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/blob/main/docs/TELEMETRY_SPEC.md"
            target="_blank"
            rel="noopener noreferrer"
            class="inline-flex min-h-6 items-center rounded-sm text-xs font-semibold text-brand-700 underline underline-offset-2 focus-ring dark:text-brand-300"
        >
            {$_('telemetry_banner.learn_more', { default: 'Learn more' })}
        </a>
    </WizardLoadState>
</WizardStepLayout>
