<script lang="ts">
    import { onMount } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { fetchSettings, updateSettings } from '../../api/settings';
    import { testFrigateConnection } from '../../api/system';
    import { testMQTTPublish } from '../../api/maintenance';
    import { setupWizardStore } from '../../stores/setup_wizard.svelte';
    import WizardStepLayout from './WizardStepLayout.svelte';

    type TestState = { ok: boolean; message: string } | null;

    let frigateUrl = $state('');
    let mqttServer = $state('');
    let mqttPort = $state(1883);
    let loaded = $state(false);
    let busy = $state(false);
    let savedOnce = $state(false);
    let frigateResult = $state<TestState>(null);
    let mqttResult = $state<TestState>(null);

    onMount(async () => {
        try {
            const s = await fetchSettings();
            frigateUrl = s.frigate_url ?? '';
            mqttServer = s.mqtt_server ?? '';
            mqttPort = s.mqtt_port ?? 1883;
        } catch {
            // Leave fields empty; the user can still enter values.
        } finally {
            loaded = true;
        }
    });

    async function saveAndTest() {
        busy = true;
        frigateResult = null;
        mqttResult = null;
        try {
            await updateSettings({ frigate_url: frigateUrl.trim(), mqtt_server: mqttServer.trim(), mqtt_port: mqttPort });
            savedOnce = true;
            try {
                const f = await testFrigateConnection();
                frigateResult = { ok: true, message: $_('setup.connection.frigate_ok', { values: { version: (f as { version?: string }).version ?? '' }, default: `Connected to Frigate ${(f as { version?: string }).version ?? ''}` }) };
            } catch (err) {
                frigateResult = { ok: false, message: err instanceof Error ? err.message : $_('setup.connection.frigate_fail', { default: 'Could not reach Frigate' }) };
            }
            try {
                const m = await testMQTTPublish();
                mqttResult = { ok: m.status === 'ok', message: m.message };
            } catch (err) {
                mqttResult = { ok: false, message: err instanceof Error ? err.message : $_('setup.connection.mqtt_fail', { default: 'Could not reach the MQTT broker' }) };
            }
        } finally {
            busy = false;
        }
    }
</script>

<WizardStepLayout
    title={$_('setup.connection.title', { default: 'Frigate & MQTT connection' })}
    description={$_('setup.connection.description', {
        default: 'YA-WAMF reads detections from Frigate over MQTT and fetches snapshots from its API. Point it at both, then test.'
    })}
    canContinue={savedOnce}
    {busy}
>
    {#if loaded}
        <div>
            <label for="setup-frigate-url" class="text-sm font-medium text-slate-700 dark:text-slate-300">{$_('setup.connection.frigate_url', { default: 'Frigate URL' })}</label>
            <input id="setup-frigate-url" type="url" placeholder="http://frigate:5000" bind:value={frigateUrl} class="input-base mt-1" />
        </div>
        <div class="grid grid-cols-3 gap-3">
            <div class="col-span-2">
                <label for="setup-mqtt-server" class="text-sm font-medium text-slate-700 dark:text-slate-300">{$_('setup.connection.mqtt_server', { default: 'MQTT broker' })}</label>
                <input id="setup-mqtt-server" type="text" placeholder="mqtt" bind:value={mqttServer} class="input-base mt-1" />
            </div>
            <div>
                <label for="setup-mqtt-port" class="text-sm font-medium text-slate-700 dark:text-slate-300">{$_('setup.connection.mqtt_port', { default: 'Port' })}</label>
                <input id="setup-mqtt-port" type="number" bind:value={mqttPort} class="input-base mt-1" />
            </div>
        </div>

        <button type="button" class="btn btn-secondary" disabled={busy} onclick={saveAndTest}>
            {$_('setup.connection.save_test', { default: 'Save & test connection' })}
        </button>

        {#each [frigateResult, mqttResult].filter(Boolean) as result}
            <div role="status" class="rounded-md p-2 text-sm {result?.ok ? 'bg-emerald-50 text-emerald-800 dark:bg-emerald-900/20 dark:text-emerald-200' : 'bg-amber-50 text-amber-800 dark:bg-amber-900/20 dark:text-amber-200'}">
                {result?.ok ? '✓' : '⚠'} {result?.message}
            </div>
        {/each}

        {#if savedOnce && !frigateResult?.ok}
            <p class="text-xs text-slate-500 dark:text-slate-400">{$_('setup.connection.continue_hint', { default: "Settings are saved. You can continue and fix the connection later — but detections won't flow until Frigate is reachable." })}</p>
        {/if}
    {/if}
</WizardStepLayout>
