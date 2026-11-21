<script lang="ts">
    import StatusIcon from '../ui/StatusIcon.svelte';
    import { onMount } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { fetchSettings, updateSettings, type SettingsUpdate } from '../../api/settings';
    import { testFrigateConnection } from '../../api/system';
    import { testMQTTPublish } from '../../api/maintenance';
    import { setupWizardStore } from '../../stores/setup_wizard.svelte';
    import WizardStepLayout from './WizardStepLayout.svelte';
    import { loadBlockedReason } from './continue-blocked';
    import WizardLoadState, { type WizardLoadStatus } from './WizardLoadState.svelte';
    import SettingsToggle from '../settings/_primitives/SettingsToggle.svelte';

    type TestState = { ok: boolean; message: string } | null;

    const TOKEN_DOCS_URL = 'https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/blob/main/docs/setup/environment-variables.md';

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
    // Both links measured working: only then is there nothing left to warn about.
    let connected = $derived(Boolean(frigateResult?.ok && mqttResult?.ok));
    let results = $derived([
        { id: 'frigate', label: $_('setup.connection.check_frigate', { default: 'Frigate API' }), result: frigateResult },
        { id: 'mqtt', label: $_('setup.connection.check_mqtt', { default: 'MQTT broker' }), result: mqttResult }
    ].flatMap((row) => (row.result ? [{ id: row.id, label: row.label, ok: row.result.ok, message: row.result.message }] : [])));
    let blockedReason = $derived(
        loadBlockedReason(loadState, $_)
        || (savedOnce ? '' : $_('setup.connection.blocked', { default: 'Save and test the connection to continue, or choose “Set up later”.' }))
    );

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
        default: 'YA-WAMF hears about each bird from Frigate over MQTT, and fetches its snapshot from Frigate’s API. Enter both addresses, then test.'
    })}
    canContinue={loadState === 'ready' && savedOnce}
    {blockedReason}
    showSkip
    skipLabel={$_('setup.connection.later', { default: 'Set up later' })}
    {busy}
>
    <WizardLoadState state={loadState} onRetry={load}>
        <div>
            <label for="setup-frigate-url" class="text-sm font-medium text-ink">{$_('setup.connection.frigate_url', { default: 'Frigate URL' })}</label>
            <input id="setup-frigate-url" type="url" placeholder="http://frigate:5000" bind:value={frigateUrl} class="input-base mt-1" />
        </div>

        <div class="border-y border-line py-3">
            <!-- The same switch Settings uses for this choice. -->
            <div class="flex min-h-11 items-start gap-3">
                <span id="setup-mqtt-auth-label" class="min-w-0 flex-1">
                    <span class="block text-sm font-semibold text-strong">
                        {$_('setup.connection.mqtt_auth', { default: 'MQTT authentication' })}
                    </span>
                    <span class="block text-xs leading-relaxed text-muted">
                        {$_('setup.connection.mqtt_auth_hint', { default: 'Enable this only when your broker requires a username and password.' })}
                    </span>
                </span>
                <SettingsToggle
                    checked={mqttAuth}
                    labelledBy="setup-mqtt-auth-label"
                    srLabel={$_('setup.connection.mqtt_auth', { default: 'MQTT authentication' })}
                    disabled={busy}
                    onchange={(next) => (mqttAuth = next)}
                />
            </div>

            {#if mqttAuth}
                <div class="mt-3 grid gap-3 border-l-2 border-line-soft pl-4 sm:grid-cols-2">
                    <div>
                        <label for="setup-mqtt-username" class="text-sm font-medium text-ink">
                            {$_('setup.connection.mqtt_username', { default: 'Username' })}
                        </label>
                        <input id="setup-mqtt-username" type="text" autocomplete="off" bind:value={mqttUsername} class="input-base mt-1" />
                    </div>
                    <div>
                        <label for="setup-mqtt-password" class="text-sm font-medium text-ink">
                            {$_('setup.connection.mqtt_password', { default: 'Password' })}
                        </label>
                        <input
                            id="setup-mqtt-password"
                            type="password"
                            autocomplete="new-password"
                            value={mqttPassword}
                            placeholder={mqttPasswordSaved ? '***REDACTED***' : ''}
                            oninput={(event) => updateMqttPassword(event.currentTarget.value)}
                            class="input-base mt-1"
                        />
                        {#if mqttPasswordSaved && !mqttPassword}
                            <p class="mt-1 text-xs text-muted">
                                {$_('setup.connection.mqtt_password_saved', { default: 'A saved password will be kept unless you enter a replacement.' })}
                            </p>
                        {/if}
                    </div>
                </div>
            {/if}
        </div>
        <div class="grid grid-cols-3 gap-3">
            <div class="col-span-2">
                <label for="setup-mqtt-server" class="text-sm font-medium text-ink">{$_('setup.connection.mqtt_server', { default: 'MQTT broker' })}</label>
                <input id="setup-mqtt-server" type="text" placeholder="mqtt" bind:value={mqttServer} class="input-base mt-1" />
            </div>
            <div>
                <label for="setup-mqtt-port" class="text-sm font-medium text-ink">{$_('setup.connection.mqtt_port', { default: 'Port' })}</label>
                <input id="setup-mqtt-port" type="number" bind:value={mqttPort} class="input-base mt-1" />
            </div>
        </div>

        <button type="button" class="btn btn-secondary px-5 py-2.5" disabled={busy} onclick={saveAndTest}>
            {savedOnce && results.length > 0 ? $_('common.test_again', { default: 'Test again' }) : $_('setup.connection.save_test', { default: 'Save & test connection' })}
        </button>

        {#if saveError}
            <div role="alert" class="border-l-2 border-status-fail-line bg-status-fail-soft px-3 py-2 text-sm text-status-fail">{saveError}</div>
        {/if}

        {#if results.length > 0}
            <!-- The checklist shape every connection test uses: one bordered list, a row per check,
                 the outcome in a word and then the cause. A failure is red, like its row elsewhere. -->
            <ol class="divide-y divide-line-soft overflow-hidden rounded-2xl border border-line" role="status" data-setup-connection-results>
                {#each results as row (row.id)}
                    <li class="flex items-start gap-3 p-3.5 {row.ok ? '' : 'bg-status-fail-soft'}" data-setup-connection-result={row.ok ? 'passed' : 'failed'}>
                        <span class="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center {row.ok ? 'text-status-ok' : 'text-status-fail'}"><StatusIcon tone={row.ok ? 'ok' : 'fail'} class="h-5 w-5" /></span>
                        <div class="min-w-0 flex-1 space-y-0.5">
                            <div class="flex flex-wrap items-center gap-2">
                                <h3 class="text-sm font-bold text-strong">{row.label}</h3>
                                <span class="text-xs font-semibold {row.ok ? 'text-muted' : 'text-status-fail'}">
                                    {row.ok ? $_('common.diagnostic_state_passed', { default: 'Passed' }) : $_('common.diagnostic_state_failed', { default: 'Failed' })}
                                </span>
                            </div>
                            <p class="text-xs leading-relaxed text-muted wrap-anywhere">{row.message}</p>
                        </div>
                    </li>
                {/each}
            </ol>
        {/if}

        {#if frigateResult && !frigateResult.ok}
            <p class="text-xs leading-relaxed text-muted" data-setup-frigate-auth-hint>
                {$_('setup.connection.frigate_auth_hint', { default: 'If your Frigate requires a sign-in, set FRIGATE_AUTH_TOKEN in the environment YA-WAMF starts with, restart it, then test again.' })}
                <a href={TOKEN_DOCS_URL} target="_blank" rel="noopener noreferrer" class="font-semibold text-accent-ink underline">{$_('setup.connection.frigate_auth_link', { default: 'Environment variables' })}</a>
            </p>
        {/if}

        {#if !connected}
            <!-- The way past a Frigate or broker that is not up yet, with exactly what waits on it. -->
            <p class="text-xs leading-relaxed text-muted" data-setup-connection-later>
                {$_('setup.connection.later_note', { default: 'No Frigate or broker to hand? Choose “Set up later”. Until both are connected under Settings → Cameras & connection, no visits arrive, no photos or clips can be fetched, and the cameras step cannot list your cameras.' })}
            </p>
        {/if}
    </WizardLoadState>
</WizardStepLayout>
