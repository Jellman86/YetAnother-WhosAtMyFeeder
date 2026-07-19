<script lang="ts">
    import { onMount } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { setupWizardStore, WIZARD_STEPS } from '../../stores/setup_wizard.svelte';
    import type { SetupSectionId, SetupSectionStatus } from '../../api/setup';
    import WizardStepLayout from './WizardStepLayout.svelte';

    const SECTION_LABELS: Record<string, string> = {
        account: 'Admin account & access',
        connection: 'Frigate & MQTT',
        cameras: 'Cameras & detection',
        model: 'Model & hardware',
        quality: 'Best available snapshots',
        integrations: 'Integrations'
    };

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
        if (status === 'ok') return $_('setup.status.ok', { default: 'Ready' });
        if (status === 'attention') return $_('setup.status.attention', { default: 'Needs attention' });
        return $_('setup.status.optional', { default: 'Optional' });
    }
</script>

<WizardStepLayout
    title={$_('setup.review.title', { default: 'Review setup' })}
    description={$_('setup.review.description', {
        default: 'Here is where each section stands. Jump into any one to change it — nothing else is affected.'
    })}
    showBack={setupWizardStore.mode === 'first_run'}
    continueLabel={setupWizardStore.mode === 'first_run'
        ? $_('setup.review.finish', { default: 'Finish' })
        : $_('setup.review.done', { default: 'Done' })}
    onContinue={() => setupWizardStore.close()}
>
    <ul class="divide-y divide-slate-200 rounded-lg border border-slate-200 dark:divide-slate-700 dark:border-slate-700">
        {#each sections as section}
            <li class="flex items-center justify-between gap-3 p-3">
                <div class="min-w-0">
                    <p class="text-sm font-medium text-slate-800 dark:text-slate-100">{SECTION_LABELS[section.id] ?? section.id}</p>
                    {#if section.detail}
                        <p class="truncate text-xs text-slate-500 dark:text-slate-400">{section.detail}</p>
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
</WizardStepLayout>
