<script lang="ts">
    import { tick } from 'svelte';
    import { sessionTests } from '../../settings/session-tests.svelte';
    import { _, locale } from 'svelte-i18n';
    import { formatShortDay } from '../../utils/datetime';
    import type { AudioSourceOption } from '../../api/audio';
    import {
        addLinkToken,
        describeLinkToken,
        linkTokens,
        relinkByStreamId,
        renamedLinks,
        sameLinkToken,
        sourceLines,
        sourceLinkLabel
    } from '../../settings/audio-source-links';
    import SettingsCard from './_primitives/SettingsCard.svelte';
    import SettingsRow from './_primitives/SettingsRow.svelte';
    import SettingsToggle from './_primitives/SettingsToggle.svelte';
    import SettingsInput from './_primitives/SettingsInput.svelte';
    import AdvancedSection from './_primitives/AdvancedSection.svelte';
    import DiagnosticDialog from '../DiagnosticDialog.svelte';
    import { serviceState, serviceStateText } from '../../settings/service-state';
    import { formatTime } from '../../utils/datetime';
    import { serviceTests } from '../../settings/service-tests.svelte';
    import { runSequentialDiagnostic, type DiagnosticStage, type DiagnosticResult } from '../../utils/diagnostic-runner';
    import { testBirdNET, testMQTTPublish, checkBirdNetReachability } from '../../api/maintenance';

    // BirdNET-Go is a source of events, like Frigate, so it is set up with the cameras: its address,
    // the MQTT topic it publishes to, and which of its sources hears which camera.
    let {
        birdnetEnabled = $bindable(true),
        birdnetUrl = $bindable(''),
        birdnetExternalUrl = $bindable(''),
        audioTopic = $bindable('birdnet/text'),
        audioBufferHours = $bindable(24),
        audioCorrelationWindowSeconds = $bindable(300),
        cameraAudioMapping = $bindable<Record<string, string>>({}),
        birdnetSourceOptions = [],
        loadingBirdnetSources = false,
        birdnetSourcesError = null,
        availableCameras = []
    }: {
        birdnetEnabled: boolean;
        birdnetUrl: string;
        birdnetExternalUrl: string;
        audioTopic: string;
        audioBufferHours: number;
        audioCorrelationWindowSeconds: number;
        cameraAudioMapping: Record<string, string>;
        birdnetSourceOptions: AudioSourceOption[];
        loadingBirdnetSources: boolean;
        birdnetSourcesError: string | null;
        availableCameras: string[];
    } = $props();

    let bnTestOpen = $state(false);
    let bnRunning = $state(false);
    let bnStages = $state<DiagnosticStage[]>([]);
    let bnResult = $state<DiagnosticResult | null>(null);
    let bnRunId = $state(0);

    async function runBirdNetDiagnostic(): Promise<void> {
        bnTestOpen = true;
        bnRunning = true;
        bnResult = null;
        bnRunId += 1;
        // Reachability first (does BirdNET-Go actually answer?), then the MQTT
        // transport detections travel on, then our own ingest pipeline. The
        // reachability stage only runs when a URL is configured — BirdNET-Go is
        // otherwise reached purely over MQTT, so we don't fabricate a check.
        const steps = [];
        if (birdnetUrl.trim()) {
            steps.push({ id: 'reachable', label: $_('settings.integrations.birdnet.stage_reachable', { default: 'BirdNET-Go reachable' }), run: () => checkBirdNetReachability(birdnetUrl.trim()) });
        }
        steps.push({ id: 'mqtt', label: $_('settings.integrations.birdnet.stage_mqtt', { default: 'MQTT broker publish' }), run: testMQTTPublish });
        steps.push({ id: 'pipeline', label: $_('settings.integrations.birdnet.stage_pipeline', { default: 'Receiving and storing a call' }), run: testBirdNET });
        // Each check stands alone: a missing URL never stops the MQTT or pipeline checks from running.
        bnResult = await runSequentialDiagnostic(steps, (stages) => (bnStages = stages), { independent: true });
        bnRunning = false;
        sessionTests.record('audio', bnResult.ok);
        serviceTests.record('birdnet', { passed: bnResult.ok, message: bnResult.message }, bnSignature);
    }

    // The group's state in words. The test describes the values it ran with, so an edit retires it.
    // Kept for the visit, so the result is still here after another section was opened.
    const bnTest = $derived(serviceTests.last('birdnet'));
    const bnSignature = $derived(`${birdnetUrl}|${audioTopic}`);
    const birdnetState = $derived(serviceStateText(serviceState({
        enabled: birdnetEnabled,
        missing: audioTopic.trim() ? null : $_('settings.integrations.state.needs_audio_topic', { default: 'add the MQTT topic BirdNET-Go publishes to' }),
        signature: bnSignature,
        test: bnTest
    }), $_, formatTime));

    // Offered to the status column while the test is on the page, which is while audio is on.
    $effect(() => {
        if (!birdnetEnabled) return;
        return sessionTests.provide(['audio'], runBirdNetDiagnostic);
    });

    // One entry per stream: the value saved is the stream id where BirdNET-Go sends one, so a
    // rename in BirdNET-Go keeps the camera linked.
    const birdnetMappingOptions = $derived(
        birdnetSourceOptions.map((source) => ({ value: source.mapping_value, label: sourceLinkLabel(source) }))
    );

    function formatRelativeTime(raw: string | null | undefined): string {
        if (!raw) return '';
        const normalized = raw.includes('T') ? raw : raw.replace(' ', 'T');
        const ts = Date.parse(normalized);
        if (Number.isNaN(ts)) return raw;
        const diffSec = Math.max(0, (Date.now() - ts) / 1000);
        // The reader's language words the age: "5 min. ago", "vor 5 Min.".
        const relative = new Intl.RelativeTimeFormat($locale ?? 'en', { numeric: 'auto', style: 'short' });
        if (diffSec < 60) return relative.format(-Math.floor(diffSec), 'second');
        if (diffSec < 3600) return relative.format(-Math.floor(diffSec / 60), 'minute');
        if (diffSec < 86400) return relative.format(-Math.floor(diffSec / 3600), 'hour');
        if (diffSec < 86400 * 7) return relative.format(-Math.floor(diffSec / 86400), 'day');
        return formatShortDay(ts);
    }

    function mappingTokensFor(camera: string): string[] {
        return linkTokens(cameraAudioMapping[camera]);
    }

    function setCameraAudioMapping(camera: string, tokens: string[]) {
        cameraAudioMapping = {
            ...cameraAudioMapping,
            [camera]: tokens.join(', ')
        };
    }

    function addCameraAudioSource(camera: string, value: string) {
        const existing = mappingTokensFor(camera);
        const next = addLinkToken(existing, value);
        if (next !== existing) setCameraAudioMapping(camera, next);
    }

    // The id of a linked source's remove button, so focus can land on a link that was just added.
    function removeButtonId(cameraIndex: number, tokenIndex: number): string {
        return `birdnet-link-remove-${cameraIndex}-${tokenIndex}`;
    }

    async function linkByStreamId(camera: string, cameraIndex: number, token: string, source: AudioSourceOption): Promise<void> {
        const next = relinkByStreamId(mappingTokensFor(camera), token, source);
        setCameraAudioMapping(camera, next);
        // The button goes with the notice, so focus moves to the link it added rather than the page.
        await tick();
        const added = next.findIndex((linked) => sameLinkToken(linked, source.mapping_value));
        document.getElementById(removeButtonId(cameraIndex, added))?.focus();
    }

    function removeCameraAudioSourceToken(camera: string, index: number) {
        setCameraAudioMapping(
            camera,
            mappingTokensFor(camera).filter((_, tokenIndex) => tokenIndex !== index)
        );
    }

    const buttonPrimaryClass = 'btn btn-primary min-h-11 px-4 py-3';
</script>

<SettingsCard id="settings-group-integrations-birdnet" title={$_('settings.integrations.birdnet.title')} description={$_('settings.integrations.birdnet.toggle_label')} status={birdnetState} titleId="integration-birdnet-title">
    <!-- The card's own switch, named by its title, so the title is not repeated as a row below it. -->
    {#snippet actions()}
        <SettingsToggle
            checked={birdnetEnabled}
            labelledBy="integration-birdnet-title"
            srLabel={$_('settings.integrations.birdnet.title')}
            onchange={(v) => (birdnetEnabled = v)}
        />
    {/snippet}

    {#if birdnetEnabled}
    <SettingsRow
        labelId="setting-birdnet-url"
        label={$_('settings.integrations.birdnet.internal_url_label', { default: 'BirdNET-Go internal URL' })}
        description={$_('settings.integrations.birdnet.internal_url_help', { default: 'Backend-only URL used to fetch spectrograms, such as the Docker network address. Leave empty to disable spectrogram backgrounds.' })}
        layout="stacked"
    >
        <SettingsInput
            id="birdnet-url"
            field="birdnet_url"
            type="text"
            value={birdnetUrl}
            placeholder="http://birdnet-go:8080"
            ariaLabel={$_('settings.integrations.birdnet.internal_url_label', { default: 'BirdNET-Go internal URL' })}
            oninput={(v) => (birdnetUrl = v)}
        />
    </SettingsRow>

    <SettingsRow
        labelId="setting-birdnet-external-url"
        label={$_('settings.integrations.birdnet.external_url_label', { default: 'BirdNET-Go browser URL' })}
        description={$_('settings.integrations.birdnet.external_url_help', { default: 'Public HTTPS URL opened by dashboard links. Falls back to the internal URL when empty.' })}
        layout="stacked"
    >
        <SettingsInput
            id="birdnet-external-url"
            field="birdnet_external_url"
            type="text"
            value={birdnetExternalUrl}
            placeholder="https://birdnet.example.com"
            ariaLabel={$_('settings.integrations.birdnet.external_url_label', { default: 'BirdNET-Go browser URL' })}
            oninput={(v) => (birdnetExternalUrl = v)}
        />
    </SettingsRow>

    <SettingsRow
        labelId="setting-audio-topic"
        label={$_('settings.integrations.birdnet.mqtt_topic')}
        layout="stacked"
    >
        <SettingsInput
            id="audio-topic"
            field="audio_topic"
            type="text"
            value={audioTopic}
            placeholder={$_('settings.integrations.birdnet.mqtt_topic_placeholder')}
            ariaLabel={$_('settings.integrations.birdnet.mqtt_topic_label')}
            oninput={(v) => (audioTopic = v)}
        />
    </SettingsRow>

    <div>
        <button
            type="button"
            onclick={runBirdNetDiagnostic}
            disabled={bnRunning}
            data-settings-test="audio"
            aria-label={$_('settings.integrations.birdnet.test_button')}
            class="w-full sm:w-auto {buttonPrimaryClass}"
        >
            {bnRunning ? $_('settings.integrations.birdnet.test_loading') : $_('settings.integrations.birdnet.test_button')}
        </button>
    </div>

    <AdvancedSection
        id="integrations-birdnet-advanced"
        title={$_('settings.integrations.birdnet.advanced_title', { default: 'Audio buffer & sensor mapping' })}
    >
        <div class="space-y-4">
            <SettingsRow
                labelId="setting-audio-buffer"
                label={$_('settings.integrations.birdnet.audio_buffer_hours')}
                description={$_('settings.integrations.birdnet.audio_buffer_help')}
                layout="stacked"
            >
                <SettingsInput
                    id="audio-buffer"
                    field="audio_buffer_hours"
                    type="number"
                    min={1}
                    max={168}
                    value={audioBufferHours}
                    ariaLabel={$_('settings.integrations.birdnet.audio_buffer_label')}
                    oninput={(v) => (audioBufferHours = Number(v) || 0)}
                />
            </SettingsRow>
            <SettingsRow
                labelId="setting-correlation-window"
                label={$_('settings.integrations.birdnet.match_window_seconds')}
                description={$_('settings.integrations.birdnet.match_window_help')}
                layout="stacked"
            >
                <SettingsInput
                    id="correlation-window"
                    field="audio_correlation_window_seconds"
                    type="number"
                    min={5}
                    max={3600}
                    value={audioCorrelationWindowSeconds}
                    ariaLabel={$_('settings.integrations.birdnet.match_window_label')}
                    oninput={(v) => (audioCorrelationWindowSeconds = Number(v) || 0)}
                />
            </SettingsRow>
        </div>

        <SettingsRow
            labelId="setting-sensor-mapping"
            label={$_('settings.integrations.birdnet.sensor_mapping_title')}
            description={availableCameras.length === 0
                ? $_('settings.integrations.birdnet.sensor_mapping_empty')
                : $_('settings.integrations.birdnet.sensor_mapping_help')}
            layout="stacked"
        >
            <div class="divide-y divide-line-soft" role="group">
                {#each availableCameras as camera, cameraIndex}
                    {@const cameraRenames = renamedLinks(mappingTokensFor(camera), birdnetSourceOptions)}
                    <div class="py-3 first:pt-0 space-y-2">
                        <div class="flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
                            <span class="inline-flex max-w-full items-center break-all rounded-md bg-surface-sunken px-2 py-0.5 text-xs font-semibold text-muted">{camera}</span>
                            {#if mappingTokensFor(camera).length > 0}
                                <span class="text-xs text-muted">{$_('settings.integrations.birdnet.sensor_mapped_count', { values: { count: mappingTokensFor(camera).length }, default: '{count, plural, one {# mapped} other {# mapped}}' })}</span>
                            {/if}
                        </div>
                        <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
                            <input
                                type="text"
                                list="birdnet-source-options"
                                bind:value={cameraAudioMapping[camera]}
                                placeholder={$_('settings.integrations.birdnet.sensor_id_placeholder')}
                                aria-label={$_('settings.integrations.birdnet.sensor_id_label', { values: { camera } })}
                                class="input-base min-h-11 w-full"
                            />
                            <select
                                aria-label={$_('settings.integrations.birdnet.add_detected_source_label', { values: { camera } })}
                                class="select-base min-h-11 w-full"
                                disabled={birdnetMappingOptions.length === 0}
                                onchange={(event) => {
                                    const select = event.currentTarget;
                                    addCameraAudioSource(camera, select.value);
                                    select.value = '';
                                }}
                            >
                                <option value="">{$_('settings.integrations.birdnet.add_detected_source')}</option>
                                {#each birdnetMappingOptions as source}
                                    <option value={source.value}>{source.label}</option>
                                {/each}
                            </select>
                        </div>
                        {#if mappingTokensFor(camera).length > 0}
                            <ul
                                class="space-y-1.5"
                                aria-label={$_('settings.integrations.birdnet.source_token_list_label', { values: { camera } })}
                            >
                                {#each mappingTokensFor(camera) as sourceToken, sourceTokenIndex}
                                    {@const linked = describeLinkToken(sourceToken, birdnetSourceOptions)}
                                    {@const renamed = cameraRenames.find((rename) => rename.token === sourceToken)}
                                    <li class="text-xs" data-audio-link-token>
                                        <div class="flex items-start justify-between gap-2">
                                            <div class="min-w-0">
                                                <div class="flex items-center gap-2">
                                                    <span class="min-w-0 break-words text-accent-ink">{linked.name}</span>
                                                    <button
                                                        type="button"
                                                        id={removeButtonId(cameraIndex, sourceTokenIndex)}
                                                        class="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-accent-ink hover:text-status-fail focus:outline-hidden focus:ring-2 focus:ring-focus"
                                                        aria-label={$_('settings.integrations.birdnet.source_token_remove', { values: { source: linked.name, camera } })}
                                                        onclick={() => removeCameraAudioSourceToken(camera, sourceTokenIndex)}
                                                    >
                                                        <span aria-hidden="true">&times;</span>
                                                    </button>
                                                </div>
                                                {#if linked.id}
                                                    <span class="block font-mono text-muted break-all">{linked.id}</span>
                                                {/if}
                                                {#if linked.install}
                                                    <span class="block text-muted break-words">{linked.install}</span>
                                                {/if}
                                            </div>
                                            {#if linked.lastHeard}
                                                <span class="shrink-0 whitespace-nowrap pt-1 text-muted">{$_('settings.integrations.birdnet.source_last_heard', { values: { time: formatRelativeTime(linked.lastHeard) }, default: 'Last heard {time}' })}</span>
                                            {/if}
                                        </div>
                                        {#if renamed}
                                            <div class="mt-1 ml-3 flex flex-wrap items-center gap-x-3 gap-y-1 border-l border-line-soft pl-3" data-audio-link-renamed>
                                                <p class="text-ink">{$_('settings.integrations.birdnet.source_renamed', { values: { old: renamed.token, new: renamed.source.source_name }, default: '{old} is now called {new}.' })}</p>
                                                <button
                                                    type="button"
                                                    class="btn btn-secondary min-h-11 px-3 py-1.5 text-xs"
                                                    aria-label={$_('settings.integrations.birdnet.source_link_by_id_label', { values: { camera, id: renamed.source.mapping_value }, default: 'Link by stream ID {id} for {camera}' })}
                                                    onclick={() => linkByStreamId(camera, cameraIndex, renamed.token, renamed.source)}
                                                >
                                                    {$_('settings.integrations.birdnet.source_link_by_id', { default: 'Link by stream ID' })}
                                                </button>
                                            </div>
                                        {/if}
                                    </li>
                                {/each}
                            </ul>
                        {/if}
                    </div>
                {/each}
                <datalist id="birdnet-source-options">
                    {#each birdnetMappingOptions as source}
                        <option value={source.value} label={source.label}></option>
                    {/each}
                </datalist>

                <div class="pt-3">
                    <div class="flex items-center justify-between mb-1.5">
                        <div class="text-sm font-semibold text-ink">
                            {$_('settings.integrations.birdnet.source_discovery_title')}
                        </div>
                        {#if !loadingBirdnetSources && !birdnetSourcesError && birdnetSourceOptions.length > 0 && availableCameras.length > 0}
                            <div class="text-sm font-semibold text-ink">{$_('settings.integrations.birdnet.source_discovery_add', { default: 'Select one to add it' })}</div>
                        {/if}
                    </div>
                    {#if loadingBirdnetSources}
                        <p class="text-xs text-muted">{$_('settings.integrations.birdnet.source_discovery_loading')}</p>
                    {:else if birdnetSourcesError}
                        <p class="text-xs text-status-fail">{$_('settings.integrations.birdnet.source_discovery_error')}</p>
                    {:else if birdnetSourceOptions.length === 0}
                        <p class="text-xs text-muted">{$_('settings.integrations.birdnet.source_discovery_empty')}</p>
                    {:else}
                        <ul class="max-h-56 overflow-y-auto">
                            {#each birdnetSourceOptions.slice(0, 12) as source, sourceIndex}
                                {@const fade = Math.max(0.45, 1 - sourceIndex * 0.06)}
                                {@const sourceValue = source.mapping_value}
                                {@const lines = sourceLines(source)}
                                <li>
                                    <button
                                        type="button"
                                        class="focus-ring group w-full flex items-center gap-2 px-2 py-1.5 text-left rounded-md hover:bg-accent-soft active:bg-accent-soft focus:outline-hidden focus-visible:bg-accent-soft focus-visible:ring-inset transition-colors cursor-pointer disabled:cursor-not-allowed disabled:hover:bg-transparent"
                                        style="opacity: {fade};"
                                        onclick={() => {
                                            if (availableCameras.length > 0) {
                                                addCameraAudioSource(availableCameras[0], sourceValue);
                                            }
                                        }}
                                        disabled={availableCameras.length === 0}
                                        title={availableCameras[0]
                                            ? $_('settings.integrations.birdnet.source_discovery_add_to', {
                                                  values: { source: sourceLinkLabel(source), time: formatRelativeTime(source.last_seen), camera: availableCameras[0] },
                                                  default: '{source}, heard {time}. Select it to add it to {camera}.'
                                              })
                                            : sourceLinkLabel(source)}
                                    >
                                        <span class="shrink-0 inline-flex h-5 w-5 items-center justify-center rounded-full bg-surface-sunken text-muted group-hover:bg-accent group-hover:text-accent-fg group-hover:group-disabled:bg-surface-sunken transition-colors text-xs font-semibold leading-none" aria-hidden="true">+</span>
                                        <span class="min-w-0 flex-1 leading-tight">
                                            <span class="block text-xs font-mono font-semibold text-strong break-words">{source.source_name}</span>
                                            {#if lines.id}
                                                <span class="block text-xs font-mono text-muted break-all">{lines.id}</span>
                                            {/if}
                                            {#if lines.install}
                                                <span class="block text-xs text-muted break-words">{lines.install}</span>
                                            {/if}
                                        </span>
                                        <span class="shrink-0 text-sm font-semibold text-ink whitespace-nowrap tabular-nums">{formatRelativeTime(source.last_seen)}</span>
                                    </button>
                                </li>
                            {/each}
                        </ul>
                    {/if}
                </div>
            </div>
        </SettingsRow>
    </AdvancedSection>
    {/if}
</SettingsCard>

{#if bnTestOpen}
    <DiagnosticDialog
        title={$_('settings.integrations.birdnet.test_title', { default: 'BirdNET-Go connection test' })}
        subtitle={$_('settings.integrations.birdnet.test_subtitle', { default: 'Confirms BirdNET-Go can be reached, the MQTT broker accepts a message, and a test call is received and stored.' })}
        stages={bnStages}
        busy={bnRunning}
        result={bnResult}
        runId={bnRunId}
        retryLabel={$_('settings.integrations.birdnet.test_button')}
        onClose={() => (bnTestOpen = false)}
        onRetry={runBirdNetDiagnostic}
    />
{/if}
