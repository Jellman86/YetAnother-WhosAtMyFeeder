<script lang="ts">
    import { onMount } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { fetchSettings, updateSettings, type SettingsUpdate } from '../../api/settings';
    import { testFrigateConnection } from '../../api/system';
    import { testMQTTPublish } from '../../api/maintenance';
    import { setupWizardStore } from '../../stores/setup_wizard.svelte';
    import WizardStepLayout from './WizardStepLayout.svelte';
    import WizardLoadState, { type WizardLoadStatus } from './WizardLoadState.svelte';

    type TestState = { ok: boolean; message: string } | null;

    let frigateUrl = $state('');
    let mqttServer = $state('');
    let mqttPort = $state(1883);
    let mqttAuth = $state(false);
    let mqttUsername = $state('');
    let mqttPassword = $state('');
    let mqttPasswordSaved = $state(false);
    let passwordRevision = $state(0);
    let loadState = $state<WizardLoadStatus>('loading');
    let busy = $state(false);
    let savedSignature = $state('');
    let saveError = $state('');
    let frigateResult = $state<TestState>(null);
    let mqttResult = $state<TestState>(null);
    let formSignature = $derived(JSON.stringify([
        frigateUrl.trim(),
        mqttServer.trim(),
        mqttPort,
        mqttAuth,
        mqttAuth ? mqttUsername.trim() : '',
        mqttAuth ? Boolean(mqttPassword || mqttPasswordSaved) : false,
        passwordRevision
    ]));
    let savedOnce = $derived(savedSignature !== '' && savedSignature === formSignature);

    async function load(): Promise<void> {
        loadState = 'loading';
        try {
            const s = await fetchSettings();
            frigateUrl = s.frigate_url ?? '';
            mqttServer = s.mqtt_server ?? '';
            mqttPort = s.mqtt_port ?? 1883;
            mqttAuth = s.mqtt_auth ?? false;
            mqttUsername = s.mqtt_username ?? '';
            mqttPasswordSaved = s.mqtt_password === '***REDACTED***';
            mqttPassword = '';
        } catch {
            loadState = 'error';
            return;
        }
        savedSignature = '';
        loadState = 'ready';
    }

    onMount(() => {
        void load();
    });

    function updateMqttPassword(value: string): void {
        mqttPassword = value;
        passwordRevision += 1;
    }

    async function saveAndTest() {
        if (loadState !== 'ready') return;
        busy = true;
        saveError = '';
        frigateResult = null;
        mqttResult = null;
        try {
            const payload: SettingsUpdate = {
                frigate_url: frigateUrl.trim(),
                mqtt_server: mqttServer.trim(),
                mqtt_port: mqttPort,
                mqtt_auth: mqttAuth,
                mqtt_username: mqttAuth ? mqttUsername.trim() : ''
            };
            if (mqttAuth && mqttPassword) payload.mqtt_password = mqttPassword;
            await updateSettings(payload);
            if (mqttPassword) {
                mqttPasswordSaved = true;
                mqttPassword = '';
            }
            savedSignature = formSignature;
            try {
                const f = await testFrigateConnection(frigateUrl.trim());
                frigateResult = { ok: true, message: $_('setup.connection.frigate_ok', { values: { version: (f as { version?: string }).version ?? '' }, default: `Connected to Frigate ${(f as { version?: string }).version ?? ''}` }) };
            } catch (err) {
                frigateResult = { ok: false, message: err instanceof Error ? err.message : $_('setup.connection.frigate_fail', { default: 'Could not reach Frigate' }) };
            }
            try {
                const m = await testMQTTPublish({
                    server: mqttServer.trim(),
                    port: mqttPort,
                    auth: mqttAuth,
                    username: mqttAuth ? mqttUsername.trim() : '',
                    password: mqttAuth ? mqttPassword : ''
                });
                mqttResult = { ok: m.status === 'ok', message: m.message };
            } catch (err) {
                mqttResult = { ok: false, message: err instanceof Error ? err.message : $_('setup.connection.mqtt_fail', { default: 'Could not reach the MQTT broker' }) };
            }
        } catch (error) {
            savedSignature = '';
            saveError = error instanceof Error && error.message.trim()
                ? error.message
                : $_('setup.connection.save_failed', { default: 'The connection settings could not be saved. Check the values and try again.' });
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
    canContinue={loadState === 'ready' && savedOnce}
    {busy}
>
    <WizardLoadState state={loadState} onRetry={load}>
        <div>
            <label for="setup-frigate-url" class="text-sm font-medium text-slate-700 dark:text-slate-300">{$_('setup.connection.frigate_url', { default: 'Frigate URL' })}</label>
            <input id="setup-frigate-url" type="url" placeholder="http://frigate:5000" bind:value={frigateUrl} class="input-base mt-1" />
        </div>

        <div class="border-y border-slate-200/80 py-3 dark:border-slate-700/70">
            <label class="flex min-h-11 items-start gap-3">
                <span class="min-w-0 flex-1">
                    <span class="block text-sm font-semibold text-slate-800 dark:text-slate-100">
                        {$_('setup.connection.mqtt_auth', { default: 'MQTT authentication' })}
                    </span>
                    <span class="block text-xs leading-relaxed text-slate-500 dark:text-slate-400">
                        {$_('setup.connection.mqtt_auth_hint', { default: 'Enable this only when your broker requires a username and password.' })}
                    </span>
                </span>
                <input type="checkbox" bind:checked={mqttAuth} class="mt-1 h-5 w-5 shrink-0 rounded border-slate-300 text-brand-600 focus:ring-brand-500" />
            </label>

            {#if mqttAuth}
                <div class="mt-3 grid gap-3 border-l-2 border-brand-100 pl-4 dark:border-brand-900/60 sm:grid-cols-2">
                    <div>
                        <label for="setup-mqtt-username" class="text-sm font-medium text-slate-700 dark:text-slate-300">
                            {$_('setup.connection.mqtt_username', { default: 'Username' })}
                        </label>
                        <input id="setup-mqtt-username" type="text" autocomplete="username" bind:value={mqttUsername} class="input-base mt-1" />
                    </div>
                    <div>
                        <label for="setup-mqtt-password" class="text-sm font-medium text-slate-700 dark:text-slate-300">
                            {$_('setup.connection.mqtt_password', { default: 'Password' })}
                        </label>
                        <input
                            id="setup-mqtt-password"
                            type="password"
                            autocomplete="current-password"
                            value={mqttPassword}
                            placeholder={mqttPasswordSaved ? '***REDACTED***' : ''}
                            oninput={(event) => updateMqttPassword(event.currentTarget.value)}
                            class="input-base mt-1"
                        />
                        {#if mqttPasswordSaved && !mqttPassword}
                            <p class="mt-1 text-xs text-accent-700 dark:text-accent-300">
                                {$_('setup.connection.mqtt_password_saved', { default: 'A saved password will be kept unless you enter a replacement.' })}
                            </p>
                        {/if}
                    </div>
                </div>
            {/if}
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

        <button type="button" class="btn btn-secondary px-5 py-2.5" disabled={busy} onclick={saveAndTest}>
            {$_('setup.connection.save_test', { default: 'Save & test connection' })}
        </button>

        {#if saveError}
            <div role="alert" class="border-l-2 border-rose-500 bg-rose-50/70 px-3 py-2 text-sm text-rose-800 dark:bg-rose-950/20 dark:text-rose-200">{saveError}</div>
        {/if}

        {#each [frigateResult, mqttResult].filter(Boolean) as result}
            <div role="status" class="flex items-start gap-2 rounded-md p-2 text-sm {result?.ok ? 'bg-success-50 text-success-800 dark:bg-success-900/20 dark:text-success-200' : 'bg-amber-50 text-amber-800 dark:bg-amber-900/20 dark:text-amber-200'}">
                {#if result?.ok}
                    <svg class="mt-0.5 h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="m5 12 4 4L19 6" /></svg>
                {:else}
                    <svg class="mt-0.5 h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v4m0 4h.01M10.3 3.7 2.6 17a2 2 0 0 0 1.7 3h15.4a2 2 0 0 0 1.7-3L13.7 3.7a2 2 0 0 0-3.4 0Z" /></svg>
                {/if}
                <span>{result?.message}</span>
            </div>
        {/each}

        {#if savedOnce && !frigateResult?.ok}
            <p class="text-xs text-slate-500 dark:text-slate-400">{$_('setup.connection.continue_hint', { default: "Settings are saved. You can continue and fix the connection later — but detections won't flow until Frigate is reachable." })}</p>
        {/if}
    </WizardLoadState>
</WizardStepLayout>
