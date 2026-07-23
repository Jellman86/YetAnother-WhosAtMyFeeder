<script lang="ts">
    import { onMount } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { fetchSettings, updateSettings, type SettingsUpdate } from '../../api/settings';
    import { checkBirdNetReachability, testBirdNET, testMQTTPublish } from '../../api/maintenance';
    import { setupWizardStore } from '../../stores/setup_wizard.svelte';
    import { runSequentialDiagnostic, type DiagnosticResult, type DiagnosticStage, type DiagnosticStep } from '../../utils/diagnostic-runner';
    import DiagnosticDialog from '../DiagnosticDialog.svelte';
    import WizardStepLayout from './WizardStepLayout.svelte';
    import WizardLoadState, { type WizardLoadStatus } from './WizardLoadState.svelte';

    type IntegrationId = 'birdnet' | 'ebird' | 'inaturalist' | 'birdweather' | 'ai';

    let birdnetEnabled = $state(false);
    let birdnetUrl = $state('');
    let ebirdEnabled = $state(false);
    let inaturalistEnabled = $state(false);
    let birdweatherEnabled = $state(false);
    let llmEnabled = $state(false);
    let loadState = $state<WizardLoadStatus>('loading');
    let busy = $state(false);
    let diagnosticOpen = $state(false);
    let diagnosticRunning = $state(false);
    let diagnosticStages = $state<DiagnosticStage[]>([]);
    let diagnosticResult = $state<DiagnosticResult | null>(null);
    let diagnosticRunId = $state(0);

    let integrations = $derived([
        { id: 'birdnet' as const, name: 'BirdNET-Go', get: () => birdnetEnabled, set: (value: boolean) => (birdnetEnabled = value), note: $_('setup.integrations.note_birdnet', { default: 'Audio confirmation of visual detections.' }) },
        { id: 'ebird' as const, name: 'eBird', get: () => ebirdEnabled, set: (value: boolean) => (ebirdEnabled = value), note: $_('setup.integrations.note_ebird', { default: 'Nearby sightings and maps. Add an API key in Settings.' }) },
        { id: 'inaturalist' as const, name: 'iNaturalist', get: () => inaturalistEnabled, set: (value: boolean) => (inaturalistEnabled = value), note: $_('setup.integrations.note_inat', { default: 'Owner-reviewed submissions. Connect your account in Settings.' }) },
        { id: 'birdweather' as const, name: 'BirdWeather', get: () => birdweatherEnabled, set: (value: boolean) => (birdweatherEnabled = value), note: $_('setup.integrations.note_bw', { default: 'Report to community stations. Add a station token in Settings.' }) },
        { id: 'ai' as const, name: $_('setup.integrations.ai', { default: 'AI analysis' }), get: () => llmEnabled, set: (value: boolean) => (llmEnabled = value), note: $_('setup.integrations.note_ai', { default: 'Behavioural notes. Add a provider key in Settings.' }) }
    ]);

    async function load(): Promise<void> {
        loadState = 'loading';
        try {
            const settings = await fetchSettings();
            birdnetEnabled = settings.birdnet_enabled ?? false;
            birdnetUrl = settings.birdnet_url ?? '';
            ebirdEnabled = settings.ebird_enabled ?? false;
            inaturalistEnabled = settings.inaturalist_enabled ?? false;
            birdweatherEnabled = settings.birdweather_enabled ?? false;
            llmEnabled = settings.llm_enabled ?? false;
        } catch {
            loadState = 'error';
            return;
        }
        loadState = 'ready';
    }

    onMount(() => {
        void load();
    });

    async function testBirdnet(): Promise<void> {
        diagnosticOpen = true;
        diagnosticRunning = true;
        diagnosticResult = null;
        diagnosticRunId += 1;
        const steps: DiagnosticStep[] = [];
        if (birdnetUrl.trim()) {
            steps.push({
                id: 'reachable',
                label: $_('settings.integrations.birdnet.stage_reachable', { default: 'BirdNET-Go reachable' }),
                run: () => checkBirdNetReachability(birdnetUrl.trim())
            });
        }
        steps.push({
            id: 'mqtt',
            label: $_('settings.integrations.birdnet.stage_mqtt', { default: 'MQTT broker publish' }),
            run: testMQTTPublish
        });
        steps.push({
            id: 'pipeline',
            label: $_('settings.integrations.birdnet.stage_pipeline', { default: 'Detection ingest and storage' }),
            run: testBirdNET
        });
        try {
            diagnosticResult = await runSequentialDiagnostic(steps, (stages) => (diagnosticStages = stages));
        } finally {
            diagnosticRunning = false;
        }
    }

    async function save(): Promise<void> {
        if (loadState !== 'ready') return;
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
            setupWizardStore.completeStep();
        } finally {
            busy = false;
        }
    }
</script>

{#snippet integrationIcon(id: IntegrationId)}
    {#if id === 'birdnet'}
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><path d="M3 12h2m2-4v8m4-11v14m4-11v8m4-6v4m2-2h-2" /></svg>
    {:else if id === 'ebird'}
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 19c5-1 9-5 10-10 2 0 4-1 5-3-4-1-7 0-9 2-2-1-5-1-7 1 2 1 3 3 3 5 0 2-1 4-2 5Z" /><path d="M14 10h.01" /></svg>
    {:else if id === 'inaturalist'}
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.5 19 2c1 2 2 4.2 2 8 0 5.5-4.5 10-10 10Z" /><path d="M2 21c0-3 1.9-5.4 5.1-6" /></svg>
    {:else if id === 'birdweather'}
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17.5 19a4.5 4.5 0 0 0 0-9 6 6 0 0 0-11.6-1.6A3.5 3.5 0 0 0 6 19Z" /></svg>
    {:else}
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 18h6M10 22h4M8.5 14.5A7 7 0 1 1 15.5 14.5C14.5 15.2 14 16 14 17h-4c0-1-.5-1.8-1.5-2.5Z" /></svg>
    {/if}
{/snippet}

<WizardStepLayout
    title={$_('setup.integrations.title', { default: 'Integrations' })}
    description={$_('setup.integrations.description', {
        default: 'Optional add-ons. Enable what you want now; sections that still need credentials are clearly marked in the final review.'
    })}
    showSkip
    canContinue={loadState === 'ready'}
    {busy}
    onContinue={save}
>
    <WizardLoadState state={loadState} onRetry={load}>
        <div class="divide-y divide-slate-200/80 border-y border-slate-200/80 dark:divide-slate-700/70 dark:border-slate-700/70">
            {#each integrations as item}
                <div class="py-3.5">
                    <label class="flex min-h-11 items-start gap-3">
                        <span class="mt-0.5 h-5 w-5 shrink-0 text-brand-600 dark:text-brand-300">{@render integrationIcon(item.id)}</span>
                        <span class="min-w-0 flex-1">
                            <span class="block text-sm font-semibold text-slate-800 dark:text-slate-100">{item.name}</span>
                            <span class="block text-xs leading-relaxed text-slate-500 dark:text-slate-400">{item.note}</span>
                        </span>
                        <input type="checkbox" checked={item.get()} onchange={(event) => item.set(event.currentTarget.checked)} class="mt-1 h-5 w-5 shrink-0 rounded border-slate-300 text-brand-600 focus:ring-brand-500" />
                    </label>

                    {#if item.id === 'birdnet' && birdnetEnabled}
                        <div class="ml-8 mt-3 space-y-2 border-l-2 border-brand-100 pl-4 dark:border-brand-900/60">
                            <label for="setup-birdnet-url" class="block text-xs font-semibold text-slate-600 dark:text-slate-300">
                                {$_('settings.integrations.birdnet.internal_url_label', { default: 'BirdNET-Go internal URL' })}
                            </label>
                            <input id="setup-birdnet-url" type="url" placeholder="http://birdnet-go:8080" bind:value={birdnetUrl} class="input-base" />
                            <p class="text-xs leading-relaxed text-slate-500 dark:text-slate-400">
                                {$_('setup.integrations.birdnet_test_subtitle', { default: 'The staged test uses this URL, then verifies the saved MQTT broker and local detection storage.' })}
                            </p>
                            <button type="button" class="btn btn-secondary px-4 py-2.5" onclick={testBirdnet} disabled={diagnosticRunning}>
                                {$_('setup.integrations.birdnet_test', { default: 'Test BirdNET-Go path' })}
                            </button>
                        </div>
                    {/if}
                </div>
            {/each}
        </div>

        <p class="flex items-start gap-2 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
            <svg class="mt-0.5 h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v4m0 4h.01M10.3 3.7 2.6 17a2 2 0 0 0 1.7 3h15.4a2 2 0 0 0 1.7-3L13.7 3.7a2 2 0 0 0-3.4 0Z" /></svg>
            <span>{$_('setup.integrations.notifications_note', { default: 'Notification channels are configured under Settings → Notifications. Home Assistant is installed and configured externally; see the integration guide.' })}</span>
        </p>
    </WizardLoadState>
</WizardStepLayout>

{#if diagnosticOpen}
    <DiagnosticDialog
        title={$_('settings.integrations.birdnet.test_title', { default: 'BirdNET-Go path test' })}
        subtitle={$_('setup.integrations.birdnet_test_subtitle', { default: 'Checks this URL, the saved MQTT broker, and local detection storage.' })}
        stages={diagnosticStages}
        result={diagnosticResult}
        busy={diagnosticRunning}
        runId={diagnosticRunId}
        onClose={() => (diagnosticOpen = false)}
        onRetry={testBirdnet}
    />
{/if}
