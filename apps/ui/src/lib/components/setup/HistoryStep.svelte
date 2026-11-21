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
                serverJobId: `backfill:detections:${job.id}`,
                kind: 'backfill',
                title: $_('setup.history.job_title', { default: 'Import of visit history' }),
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
    <h3 class="text-sm font-bold text-strong">{$_('setup.history.title', { default: 'Import visits Frigate still has' })}</h3>
    <p class="text-sm text-muted">{$_('setup.history.description', { default: 'Optionally name the bird events Frigate still keeps. The import runs in the background while you finish setup.' })}</p>
    <label class="flex min-h-12 items-start gap-3 border-y border-line py-3 text-sm text-ink">
        <input type="checkbox" bind:checked={importHistory} class="mt-0.5 h-5 w-5 rounded-sm border-line-strong text-accent focus:ring-focus" />
        <span>
            <span class="block font-semibold text-strong">
                {$_('setup.history.enable', { default: 'Import the bird events Frigate still keeps' })}
            </span>
            <span class="mt-1 block leading-relaxed text-muted">
                {$_('setup.history.enable_help', { default: 'A visit already in your history is changed only when the new result is better; its saved audio and weather stay.' })}
            </span>
        </span>
    </label>

    {#if importHistory}
        <fieldset class="space-y-2 border-l-2 border-line-soft pl-4">
            <legend class="text-sm font-medium text-ink">
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
                        <span class="btn btn-secondary flex min-h-11 items-center justify-center px-3 py-2 text-center peer-checked:border-accent-line peer-checked:bg-accent-soft peer-checked:text-accent-ink peer-focus-visible:ring-2 peer-focus-visible:ring-focus peer-focus-visible:ring-offset-2 peer-focus-visible:ring-offset-surface">
                            {option.label}
                        </span>
                    </label>
                {/each}
            </div>
        </fieldset>
    {/if}

    <p class="flex items-start gap-2 text-xs leading-relaxed text-muted">
        <svg class="mt-0.5 h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v4m0 4h.01M10.3 3.7 2.6 17a2 2 0 0 0 1.7 3h15.4a2 2 0 0 0 1.7-3L13.7 3.7a2 2 0 0 0-3.4 0Z" /></svg>
        <span>{$_('setup.history.audio_note', { default: 'Frigate’s history can bring back visits and their photos, but not BirdNET-Go audio that was never stored.' })}</span>
    </p>

    <h3 class="border-t border-line pt-4 text-sm font-bold text-strong">{$_('telemetry_banner.title', { default: 'Share anonymous usage stats?' })}</h3>
    <p class="text-sm text-muted">{$_('telemetry_banner.body', { default: 'They show which features actually get used, so time goes to the parts people rely on. Opt-in, no personal data, off by default.' })}</p>
    <WizardLoadState state={usageLoad} onRetry={loadUsageChoice}>
        <label class="flex min-h-12 items-start gap-3 border-y border-line py-3 text-sm text-ink">
            <input type="checkbox" bind:checked={shareUsage} class="mt-0.5 h-5 w-5 rounded-sm border-line-strong text-accent focus:ring-focus" />
            <span>
                <span class="block font-semibold text-strong">{$_('setup.telemetry.opt_in', { default: 'Yes, share anonymous usage stats to help guide development.' })}</span>
                <span class="mt-1 block leading-relaxed text-muted">
                    {$_('setup.telemetry.note', { default: 'No personal data is collected, and you can change this any time in Settings.' })}
                </span>
            </span>
        </label>
        <a
            href="https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/blob/main/docs/TELEMETRY_SPEC.md"
            target="_blank"
            rel="noopener noreferrer"
            class="inline-flex min-h-6 items-center rounded-sm text-xs font-semibold text-accent-ink underline underline-offset-2 focus-ring"
        >
            {$_('telemetry_banner.learn_more', { default: 'Learn more' })}
        </a>
    </WizardLoadState>
</WizardStepLayout>
