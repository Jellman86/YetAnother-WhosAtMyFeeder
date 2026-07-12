<script lang="ts">
    import { onMount } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { fetchSettings, updateSettings } from '../../api/settings';
    import { testBirdNET } from '../../api/maintenance';
    import { setupWizardStore } from '../../stores/setup_wizard.svelte';
    import WizardStepLayout from './WizardStepLayout.svelte';

    let birdnetEnabled = $state(false);
    let birdnetUrl = $state('');
    let loaded = $state(false);
    let busy = $state(false);
    let testResult = $state<{ ok: boolean; message: string } | null>(null);

    onMount(async () => {
        try {
            const s = await fetchSettings();
            birdnetEnabled = s.birdnet_enabled ?? false;
            birdnetUrl = s.birdnet_url ?? '';
        } catch {
            // Editable defaults remain.
        } finally {
            loaded = true;
        }
    });

    async function testBirdnet() {
        testResult = null;
        try {
            await updateSettings({ birdnet_enabled: true, birdnet_url: birdnetUrl.trim() });
            const r = await testBirdNET();
            testResult = { ok: r.status === 'ok', message: r.message };
        } catch (err) {
            testResult = { ok: false, message: err instanceof Error ? err.message : $_('setup.integrations.birdnet_fail', { default: 'Could not reach BirdNET-Go' }) };
        }
    }

    async function save() {
        busy = true;
        try {
            await updateSettings({ birdnet_enabled: birdnetEnabled, birdnet_url: birdnetUrl.trim() });
            await setupWizardStore.refresh();
            setupWizardStore.next();
        } finally {
            busy = false;
        }
    }
</script>

<WizardStepLayout
    title={$_('setup.integrations.title', { default: 'Integrations' })}
    description={$_('setup.integrations.description', {
        default: 'Optional add-ons. Enable audio confirmation now; notifications, eBird, iNaturalist, and AI analysis can be configured any time in Settings → Integrations.'
    })}
    showSkip
    {busy}
    onContinue={save}
>
    {#if loaded}
        <label class="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
            <input type="checkbox" bind:checked={birdnetEnabled} class="rounded border-slate-300 text-teal-600 focus:ring-teal-500" />
            {$_('setup.integrations.birdnet_enable', { default: 'Enable BirdNET-Go audio confirmation' })}
        </label>

        {#if birdnetEnabled}
            <div>
                <label for="setup-birdnet-url" class="text-sm font-medium text-slate-700 dark:text-slate-300">{$_('setup.integrations.birdnet_url', { default: 'BirdNET-Go URL' })}</label>
                <input id="setup-birdnet-url" type="url" placeholder="http://birdnet-go:8080" bind:value={birdnetUrl} class="input-base mt-1" />
            </div>
            <button type="button" class="btn btn-secondary" onclick={testBirdnet}>{$_('setup.integrations.birdnet_test', { default: 'Test BirdNET-Go' })}</button>
            {#if testResult}
                <div role="status" class="rounded-md p-2 text-sm {testResult.ok ? 'bg-emerald-50 text-emerald-800 dark:bg-emerald-900/20 dark:text-emerald-200' : 'bg-amber-50 text-amber-800 dark:bg-amber-900/20 dark:text-amber-200'}">
                    {testResult.ok ? '✓' : '⚠'} {testResult.message}
                </div>
            {/if}
        {/if}

        <p class="text-xs text-slate-500 dark:text-slate-400">{$_('setup.integrations.more', { default: 'More integrations (Discord/Telegram/Pushover, eBird, iNaturalist, BirdWeather, AI analysis, Home Assistant) live in Settings.' })}</p>
    {/if}
</WizardStepLayout>
