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
    const model = $derived.by(() => {
        if (status.kind === 'checking' || !status.modelId) return $_('settings.models.status_unnamed_model', { default: 'The chosen model' });
        return identificationModelName({ id: status.modelId, name: status.modelName }, translate).name;
    });
    const needsAttention = $derived(status.kind === 'missing' || (status.kind === 'running' && status.fallback !== null));

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
                return `${$_('settings.models.status_missing', { default: 'Nothing is naming birds yet: {model} is not on this install.', values: { model } })} ${next}`;
            }
            case 'planned':
                return status.device
                    ? $_('settings.models.status_planned', { default: '{model} will name birds on {device}. It loads with the first detection.', values: { model, device: status.device } })
                    : $_('settings.models.status_planned_no_device', { default: '{model} will name birds. It loads with the first detection.', values: { model } });
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
