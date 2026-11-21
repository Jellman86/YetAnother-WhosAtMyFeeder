<script lang="ts">
    import { _ } from 'svelte-i18n';
    import type { ClassifierStatus } from '../api/classifier';
    import { identificationModelName, identificationStatus } from '../settings/identification-models';

    // One sentence of what names the birds right now. Settings › Models, the first-run wizard and
    // About all show this sentence, built from the classifier's own report, so they always agree.
    let {
        classifierStatus,
        context = 'settings',
    }: {
        classifierStatus: ClassifierStatus | null;
        /** Where the next step lives, which is the only part of the sentence that differs. */
        context?: 'settings' | 'wizard' | 'about';
    } = $props();

    const status = $derived(identificationStatus(classifierStatus));
    const translate = (key: string, options?: { default?: string; values?: Record<string, string | number> }): string => $_(key, options);
    const named = $derived(status.kind !== 'checking' && Boolean(status.modelId));
    const model = $derived.by(() => {
        if (status.kind === 'checking' || !status.modelId) return $_('settings.models.status_unnamed_model', { default: 'The chosen model' });
        return identificationModelName({ id: status.modelId, name: status.modelName }, translate).name;
    });
    const needsAttention = $derived(
        status.kind === 'missing' || status.kind === 'failed' || status.kind === 'unavailable'
            || (status.kind === 'running' && status.fallback !== null)
    );
    // The runtime's own words can name paths, so only the owner's pages show them.
    const showDetail = $derived(status.kind === 'failed' && status.detail !== null && context !== 'about');

    const sentence = $derived.by((): string => {
        switch (status.kind) {
            case 'checking':
                return $_('settings.models.status_checking', { default: 'Checking which model names birds…' });
            case 'missing': {
                const next = context === 'wizard'
                    ? $_('settings.models.status_missing_next_wizard', { default: 'Download it here, or choose another model.' })
                    : context === 'about'
                        ? $_('settings.models.status_missing_next_about', { default: 'Download it in Settings › Models.' })
                        : $_('settings.models.status_missing_next_settings', { default: 'Download it below, or choose another model.' });
                // A model is named by its purpose ("Small and quick, birds worldwide"), which reads as a
                // clause unless the sentence says first that it is the chosen model.
                const missing = named
                    ? $_('settings.models.status_missing', { default: 'Nothing is naming birds yet: the chosen model, {model}, is not on this install.', values: { model } })
                    : $_('settings.models.status_missing_unnamed', { default: 'Nothing is naming birds yet: the chosen model is not on this install.' });
                return `${missing} ${next}`;
            }
            case 'failed':
                return status.cause === 'missing_files'
                    ? $_('settings.models.status_failed_files', { default: '{model} is installed but failed to load: its files could not be read. Nothing is naming birds until it loads.', values: { model } })
                    : $_('settings.models.status_failed_runtime', { default: '{model} is installed but failed to load: the runtime could not open it on this machine. Nothing is naming birds until it loads.', values: { model } });
            case 'unavailable':
                return $_('settings.models.status_unavailable', { default: '{model} is installed but not loaded, so nothing is naming birds right now.', values: { model } });
            case 'loading':
                return $_('settings.models.status_loading', { default: '{model} is loading. Nothing is naming birds until it has loaded.', values: { model } });
            case 'unknown':
                return $_('settings.models.status_unknown', { default: 'YA-WAMF could not tell whether {model} is naming birds.', values: { model } });
            case 'planned':
                return status.device
                    ? $_('settings.models.status_planned', { default: '{model} will name birds on {device}. It loads with the first visit.', values: { model, device: status.device } })
                    : $_('settings.models.status_planned_no_device', { default: '{model} will name birds. It loads with the first visit.', values: { model } });
            case 'running': {
                if (status.fallback === 'workers') {
                    return $_('settings.models.status_fallback_workers', { default: 'Naming birds with {model} inside the app, because the isolated workers keep stopping.', values: { model } });
                }
                if (status.fallback === 'device') {
                    return $_('settings.models.status_fallback_device', { default: 'Naming birds with {model} on {device}, because the chosen device failed its check.', values: { model, device: status.device ?? 'CPU' } });
                }
                const running = status.device
                    ? $_('settings.models.status_running', { default: 'Naming birds with {model} on {device}.', values: { model, device: status.device } })
                    : $_('settings.models.status_running_no_device', { default: 'Naming birds with {model}.', values: { model } });
                return status.species
                    ? `${running} ${$_('settings.models.status_species', { default: 'It knows {count, number} species.', values: { count: status.species } })}`
                    : running;
            }
        }
    });
</script>

<p
    role="status"
    class="flex items-start gap-2 text-base leading-relaxed {needsAttention ? 'font-medium text-attention-800 dark:text-attention-200' : 'text-slate-800 dark:text-slate-100'}"
    data-identification-status={status.kind}
>
    {#if needsAttention}
        <svg class="mt-1 h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M10.3 2.9 1.8 17a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 2.9a2 2 0 0 0-3.4 0Z" />
            <path d="M12 9v4M12 17h.01" />
        </svg>
    {/if}
    <span class="min-w-0 wrap-break-word">{sentence}</span>
</p>
{#if showDetail && status.kind === 'failed'}
    <details class="group mt-1 pl-6" data-identification-status-detail>
        <summary class="inline-flex min-h-11 cursor-pointer list-none items-center gap-1.5 rounded-sm text-sm font-medium text-brand-700 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-focus dark:text-brand-300">
            {$_('settings.detection.model_manager_technical_details', { default: 'Technical details' })}
            <svg class="h-4 w-4 transition-transform group-open:rotate-180 motion-reduce:transition-none" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="6 9 12 15 18 9" /></svg>
        </summary>
        <p class="mt-1 break-all font-mono text-xs text-slate-700 dark:text-slate-200">{status.detail}</p>
    </details>
{/if}
