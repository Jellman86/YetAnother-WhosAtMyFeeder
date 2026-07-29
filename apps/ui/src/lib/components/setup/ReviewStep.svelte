<script lang="ts">
    import { onMount } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { setupWizardStore, WIZARD_STEPS } from '../../stores/setup_wizard.svelte';
    import type { SetupSectionId, SetupSectionState, SetupSectionStatus } from '../../api/setup';
    import WizardStepLayout from './WizardStepLayout.svelte';

    const STATUS_BADGE: Record<SetupSectionStatus, string> = {
        ok: 'bg-accent-100 text-accent-800 dark:bg-accent-900/30 dark:text-accent-200',
        attention: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-200',
        optional: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'
    };

    let sections = $derived(setupWizardStore.setupState?.sections ?? []);

    onMount(() => {
        void setupWizardStore.refresh();
    });

    function stepIndexForSection(section: SetupSectionId): number {
        return WIZARD_STEPS.findIndex((s) => s.section === section);
    }

    function statusLabel(status: SetupSectionStatus): string {
        if (status === 'ok') return $_('setup.status.ok', { default: 'Configured' });
        if (status === 'attention') return $_('setup.status.attention', { default: 'Needs attention' });
        return $_('setup.status.optional', { default: 'Optional' });
    }

    function sectionLabel(section: SetupSectionId): string {
        const labels: Record<SetupSectionId, string> = {
            account: $_('setup.account.title', { default: 'Admin account & access' }),
            connection: $_('setup.connection.title', { default: 'Frigate & MQTT connection' }),
            cameras: $_('setup.cameras.title', { default: 'Cameras & detection' }),
            model: $_('setup.model.title', { default: 'Classifier model & hardware' }),
            quality: $_('setup.quality.title', { default: 'Best available snapshots' }),
            integrations: $_('setup.integrations.title', { default: 'Integrations' })
        };
        return labels[section];
    }

    function sectionDetail(section: SetupSectionState): string {
        const values = section.detail_values ?? {};
        const text = (key: string): string => String(values[key] ?? '');
        switch (section.detail_code) {
            case 'account_password_protected':
                return $_('setup.review.detail.account_password_protected', { default: 'Password protected' });
            case 'account_auth_disabled':
                return $_('setup.review.detail.account_auth_disabled', { default: 'Authentication disabled' });
            case 'account_not_configured':
                return $_('setup.review.detail.account_not_configured', { default: 'Not configured' });
            case 'connection_ready':
                return text('url');
            case 'connection_missing': {
                const itemLabels: Record<string, string> = {
                    frigate_url: $_('setup.review.detail.frigate_url', { default: 'Frigate URL' }),
                    mqtt_broker: $_('setup.review.detail.mqtt_broker', { default: 'MQTT broker' }),
                    mqtt_username: $_('setup.review.detail.mqtt_username', { default: 'MQTT username' }),
                    mqtt_password: $_('setup.review.detail.mqtt_password', { default: 'MQTT password' })
                };
                const items = text('items').split(',').filter(Boolean).map((item) => itemLabels[item] ?? item);
                return $_('setup.review.detail.connection_missing', { values: { items: items.join(', ') }, default: `Set ${items.join(', ')}` });
            }
            case 'cameras_count':
                return $_('setup.review.detail.cameras_count', { values: { count: Number(values.count ?? 0) }, default: `${values.count ?? 0} cameras` });
            case 'cameras_all':
                return $_('setup.review.detail.cameras_all', { default: 'All cameras' });
            case 'model_wrong_kind':
                return $_('setup.review.detail.model_wrong_kind', { default: 'A crop detector is selected as the classifier' });
            case 'model_retired':
                return $_('setup.review.detail.model_retired', { default: 'The saved classifier has been retired' });
            case 'model_selected':
                return text('model');
            case 'model_fallback':
                return $_('setup.review.detail.model_fallback', { default: 'Bundled fallback' });
            case 'quality_best':
                return $_('setup.review.detail.quality_best', { default: 'Best available snapshots' });
            case 'quality_standard':
                return $_('setup.review.detail.quality_standard', { default: 'Standard snapshots' });
            case 'integrations_incomplete': {
                const incomplete = text('incomplete');
                const configured = text('configured');
                const needs = $_('setup.review.detail.integrations_needs', { values: { integrations: incomplete }, default: `Needs setup: ${incomplete}` });
                return configured
                    ? `${needs} · ${$_('setup.review.detail.integrations_configured', { values: { integrations: configured }, default: `Configured: ${configured}` })}`
                    : needs;
            }
            case 'integrations_configured':
                return $_('setup.review.detail.integrations_configured', { values: { integrations: text('configured') }, default: `Configured: ${text('configured')}` });
            case 'integrations_none':
                return $_('setup.review.detail.integrations_none', { default: 'None enabled' });
            default:
                return section.detail ?? '';
        }
    }
</script>

<WizardStepLayout
    title={$_('setup.review.title', { default: 'Review setup' })}
    description={$_('setup.review.description', {
        default: 'Here is where each section stands. Jump into any one to change it — nothing else is affected.'
    })}
    showBack={setupWizardStore.mode === 'first_run'}
    canContinue={sections.length > 0}
    continueLabel={setupWizardStore.mode === 'first_run'
        ? $_('setup.review.finish', { default: 'Finish' })
        : $_('setup.review.done', { default: 'Done' })}
    onContinue={() => setupWizardStore.close()}
>
    {#if setupWizardStore.refreshing && sections.length === 0}
        <div role="status" class="flex min-h-28 items-center justify-center gap-3 text-sm text-slate-500 dark:text-slate-400">
            <span class="h-5 w-5 animate-spin rounded-full border-2 border-brand-200 border-t-brand-600" aria-hidden="true"></span>
            {$_('setup.review.loading', { default: 'Checking the saved setup…' })}
        </div>
    {:else if setupWizardStore.refreshFailed && sections.length === 0}
        <div role="alert" class="space-y-3 border-l-2 border-rose-500 bg-rose-50/70 px-4 py-3 text-sm text-rose-800 dark:bg-rose-950/20 dark:text-rose-200">
            <p>{$_('setup.review.load_failed', { default: 'The setup summary could not be loaded. Your saved settings were not changed.' })}</p>
            <button type="button" class="btn btn-secondary min-h-11 px-4 py-2" onclick={() => setupWizardStore.refresh()}>
                {$_('setup.review.retry', { default: 'Retry summary' })}
            </button>
        </div>
    {:else}
    {#if setupWizardStore.refreshFailed}
        <div role="alert" class="flex flex-wrap items-center justify-between gap-2 border-l-2 border-amber-500 bg-amber-50/70 px-3 py-2 text-sm text-amber-800 dark:bg-amber-950/20 dark:text-amber-200">
            <span>{$_('setup.review.stale', { default: 'Showing the last setup summary because the latest refresh failed.' })}</span>
            <button type="button" class="btn btn-ghost min-h-11 px-3 py-2" onclick={() => setupWizardStore.refresh()}>{$_('common.retry', { default: 'Retry' })}</button>
        </div>
    {/if}
    <ul class="divide-y divide-slate-200 border-y border-slate-200 dark:divide-slate-700 dark:border-slate-700">
        {#each sections as section}
            <li class="flex items-center justify-between gap-3 p-3">
                <div class="min-w-0">
                    <p class="text-sm font-medium text-slate-800 dark:text-slate-100">{sectionLabel(section.id)}</p>
                    {#if sectionDetail(section)}
                        <p class="break-words text-xs leading-relaxed text-slate-500 dark:text-slate-400">{sectionDetail(section)}</p>
                    {/if}
                </div>
                <div class="flex shrink-0 items-center gap-2">
                    <span class="rounded-full px-2 py-0.5 text-xs font-semibold {STATUS_BADGE[section.status]}">{statusLabel(section.status)}</span>
                    <button type="button" class="btn btn-ghost px-3 py-1.5 text-xs" onclick={() => setupWizardStore.goto(stepIndexForSection(section.id))}>
                        {$_('setup.review.edit', { default: 'Review' })}
                    </button>
                </div>
            </li>
        {/each}
    </ul>
    {/if}
</WizardStepLayout>
