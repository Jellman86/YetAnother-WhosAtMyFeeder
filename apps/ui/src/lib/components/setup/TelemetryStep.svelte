<script lang="ts">
    import { onMount } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { fetchSettings, updateSettings } from '../../api/settings';
    import { setupWizardStore } from '../../stores/setup_wizard.svelte';
    import WizardStepLayout from './WizardStepLayout.svelte';
    import WizardLoadState, { type WizardLoadStatus } from './WizardLoadState.svelte';

    // Opt-in, off by default. This is the only place first-run asks; existing
    // installs that predate the step just turn it on in Settings.
    let enabled = $state(false);
    let loadState = $state<WizardLoadStatus>('loading');
    let busy = $state(false);

    async function load(): Promise<void> {
        loadState = 'loading';
        try {
            const s = await fetchSettings();
            enabled = s.telemetry_enabled ?? false;
        } catch {
            loadState = 'error';
            return;
        }
        loadState = 'ready';
    }

    onMount(() => {
        void load();
    });

    async function save() {
        if (loadState !== 'ready') return;
        busy = true;
        try {
            await updateSettings({ telemetry_enabled: enabled });
            await setupWizardStore.refresh();
            setupWizardStore.completeStep();
        } finally {
            busy = false;
        }
    }
</script>

<WizardStepLayout
    title={$_('telemetry_banner.title', { default: 'Share anonymous usage stats?' })}
    description={$_('telemetry_banner.body', {
        default: "They show which features actually get used, so time goes to the parts people rely on. Opt-in, no personal data, off by default."
    })}
    showSkip
    canContinue={loadState === 'ready'}
    {busy}
    onContinue={save}
>
    <WizardLoadState state={loadState} onRetry={load}>
        <label class="flex items-start gap-3 rounded-2xl border border-slate-200 p-4 text-sm text-slate-700 dark:border-slate-700 dark:text-slate-300">
            <input type="checkbox" bind:checked={enabled} class="mt-0.5 rounded border-slate-300 text-brand-600 focus:ring-brand-500" />
            <span>
                {$_('setup.telemetry.opt_in', { default: 'Yes, share anonymous usage stats to help guide development.' })}
                <span class="mt-1 block text-xs text-slate-500 dark:text-slate-400">
                    {$_('setup.telemetry.note', { default: 'No personal data is collected, and you can change this any time in Settings.' })}
                </span>
            </span>
        </label>
        <a
            href="https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/blob/main/docs/TELEMETRY_SPEC.md"
            target="_blank"
            rel="noopener noreferrer"
            class="inline-block text-xs font-semibold text-brand-700 hover:underline dark:text-brand-300"
        >
            {$_('telemetry_banner.learn_more', { default: 'Learn more' })}
        </a>
    </WizardLoadState>
</WizardStepLayout>
