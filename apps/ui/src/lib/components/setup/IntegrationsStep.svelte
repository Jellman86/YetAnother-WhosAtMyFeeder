<script lang="ts">
    import { onMount } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { fetchSettings, updateSettings, type SettingsUpdate } from '../../api/settings';
    import { testBirdNET } from '../../api/maintenance';
    import { setupWizardStore } from '../../stores/setup_wizard.svelte';
    import WizardStepLayout from './WizardStepLayout.svelte';

    let birdnetEnabled = $state(false);
    let birdnetUrl = $state('');
    let ebirdEnabled = $state(false);
    let inaturalistEnabled = $state(false);
    let birdweatherEnabled = $state(false);
    let llmEnabled = $state(false);
    let loaded = $state(false);
    let busy = $state(false);
    let testResult = $state<{ ok: boolean; message: string } | null>(null);

    let integrations = $derived([
        { icon: '🎵', name: 'BirdNET-Go', get: () => birdnetEnabled, set: (v: boolean) => (birdnetEnabled = v), note: $_('setup.integrations.note_birdnet', { default: 'Audio confirmation of visual detections.' }) },
        { icon: '🦉', name: 'eBird', get: () => ebirdEnabled, set: (v: boolean) => (ebirdEnabled = v), note: $_('setup.integrations.note_ebird', { default: 'Nearby sightings & maps. Add an API key in Settings.' }) },
        { icon: '🌿', name: 'iNaturalist', get: () => inaturalistEnabled, set: (v: boolean) => (inaturalistEnabled = v), note: $_('setup.integrations.note_inat', { default: 'Owner-reviewed submissions. Connect your account in Settings.' }) },
        { icon: '🌦️', name: 'BirdWeather', get: () => birdweatherEnabled, set: (v: boolean) => (birdweatherEnabled = v), note: $_('setup.integrations.note_bw', { default: 'Report to community stations. Add a station token in Settings.' }) },
        { icon: '🧠', name: $_('setup.integrations.ai', { default: 'AI analysis' }), get: () => llmEnabled, set: (v: boolean) => (llmEnabled = v), note: $_('setup.integrations.note_ai', { default: 'LLM behavioural notes. Add a provider key in Settings.' }) }
    ]);

    onMount(async () => {
        try {
            const s = await fetchSettings();
            birdnetEnabled = s.birdnet_enabled ?? false;
            birdnetUrl = s.birdnet_url ?? '';
            ebirdEnabled = s.ebird_enabled ?? false;
            inaturalistEnabled = s.inaturalist_enabled ?? false;
            birdweatherEnabled = s.birdweather_enabled ?? false;
            llmEnabled = s.llm_enabled ?? false;
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
            const payload: SettingsUpdate = {
                birdnet_enabled: birdnetEnabled,
                birdnet_url: birdnetUrl.trim(),
                ebird_enabled: ebirdEnabled,
                inaturalist_enabled: inaturalistEnabled,
                birdweather_enabled: birdweatherEnabled,
                llm_enabled: llmEnabled
            };
            await updateSettings(payload);
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
        default: 'Optional add-ons — flip on what you want now and finish any credentials in Settings later.'
    })}
    showSkip
    {busy}
    onContinue={save}
>
    {#if loaded}
        <div class="space-y-2">
            {#each integrations as item}
                <div class="rounded-xl border border-slate-200 p-3 dark:border-slate-700">
                    <label class="flex items-start gap-3">
                        <span class="mt-0.5 text-xl" aria-hidden="true">{item.icon}</span>
                        <span class="min-w-0 flex-1">
                            <span class="block text-sm font-semibold text-slate-800 dark:text-slate-100">{item.name}</span>
                            <span class="block text-xs text-slate-500 dark:text-slate-400">{item.note}</span>
                        </span>
                        <input type="checkbox" checked={item.get()} onchange={(e) => item.set(e.currentTarget.checked)} class="mt-1 h-4 w-4 shrink-0 rounded border-slate-300 text-brand-600 focus:ring-brand-500" />
                    </label>

                    {#if item.name === 'BirdNET-Go' && birdnetEnabled}
                        <div class="mt-3 space-y-2 border-t border-slate-100 pt-3 dark:border-slate-700/60">
                            <input type="url" placeholder="http://birdnet-go:8080" bind:value={birdnetUrl} class="input-base" aria-label="BirdNET-Go URL" />
                            <button type="button" class="btn btn-secondary px-4 py-2" onclick={testBirdnet}>{$_('setup.integrations.birdnet_test', { default: 'Test BirdNET-Go' })}</button>
                            {#if testResult}
                                <div role="status" class="rounded-md p-2 text-xs {testResult.ok ? 'bg-accent-50 text-accent-800 dark:bg-accent-900/20 dark:text-accent-200' : 'bg-amber-50 text-amber-800 dark:bg-amber-900/20 dark:text-amber-200'}">
                                    {testResult.ok ? '✓' : '⚠'} {testResult.message}
                                </div>
                            {/if}
                        </div>
                    {/if}
                </div>
            {/each}
        </div>

        <p class="flex items-start gap-2 text-xs text-slate-500 dark:text-slate-400">
            <span aria-hidden="true">🔔</span>
            <span>{$_('setup.integrations.notifications_note', { default: 'Notifications (Discord, Telegram, Pushover, Email) and Home Assistant are set up in Settings → Notifications / Integrations.' })}</span>
        </p>
    {/if}
</WizardStepLayout>
