<script lang="ts">
    import { sessionTests } from '../../settings/session-tests.svelte';
    import { _, locale } from 'svelte-i18n';
    import { formatDate } from '../../utils/datetime';
    import SettingsCard from './_primitives/SettingsCard.svelte';
    import SettingsRow from './_primitives/SettingsRow.svelte';
    import SettingsToggle from './_primitives/SettingsToggle.svelte';
    import SettingsInput from './_primitives/SettingsInput.svelte';
    import AdvancedSection from './_primitives/AdvancedSection.svelte';
    import DiagnosticDialog from '../DiagnosticDialog.svelte';
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
        birdnetSourceOptions: Array<{
            source_name: string;
            mapping_value?: string;
            last_seen: string;
            sample_source_id?: string | null;
            seen_count?: number;
        }>;
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
    }

    // Offered to the status column while the test is on the page, which is while audio is on.
    $effect(() => {
        if (!birdnetEnabled) return;
        return sessionTests.provide(['audio'], runBirdNetDiagnostic);
    });

    let birdnetMappingOptions = $derived.by(() => {
        const seen = new Set<string>();
        return birdnetSourceOptions
            .flatMap((source) => {
                const value = (source.mapping_value || source.source_name || '').trim();
                if (!value) return [];
                const key = value.toLocaleLowerCase();
                if (seen.has(key)) return [];
                seen.add(key);
                return [{
                    value,
                    label: source.source_name && source.source_name !== value
                        ? `${source.source_name} (${value})`
                        : value,
                    sampleSourceId: source.sample_source_id
                }];
            });
    });

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
        return formatDate(ts);
    }

    function mappingTokensFor(camera: string): string[] {
        return (cameraAudioMapping[camera] || '')
            .split(/[,\n;|]+/)
            .map((token) => token.trim())
            .filter(Boolean);
    }

    function setCameraAudioMapping(camera: string, tokens: string[]) {
        cameraAudioMapping = {
            ...cameraAudioMapping,
            [camera]: tokens.join(', ')
        };
    }

    function addCameraAudioSource(camera: string, value: string) {
        const nextSource = value.trim();
        if (!nextSource) return;

        const existing = mappingTokensFor(camera);
        const nextKey = nextSource.toLocaleLowerCase();
        if (existing.some((token) => token.toLocaleLowerCase() === nextKey)) return;

        setCameraAudioMapping(camera, [...existing, nextSource]);
    }

    function removeCameraAudioSourceToken(camera: string, index: number) {
        setCameraAudioMapping(
            camera,
            mappingTokensFor(camera).filter((_, tokenIndex) => tokenIndex !== index)
        );
    }

    const buttonPrimaryClass = 'btn btn-primary min-h-11 px-4 py-3';
</script>

<SettingsCard id="settings-group-integrations-birdnet" title={$_('settings.integrations.birdnet.title')} description={$_('settings.integrations.birdnet.toggle_label')} titleId="integration-birdnet-title" nested>
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
                {#each availableCameras as camera}
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
                                    <option value={source.value}>
                                        {source.label}{source.sampleSourceId ? ` - ${source.sampleSourceId}` : ''}
                                    </option>
                                {/each}
                            </select>
                        </div>
                        {#if mappingTokensFor(camera).length > 0}
                            <div
                                class="flex flex-wrap gap-1.5"
                                aria-label={$_('settings.integrations.birdnet.source_token_list_label', { values: { camera } })}
                            >
                                {#each mappingTokensFor(camera) as sourceToken, sourceTokenIndex}
                                    <span class="inline-flex max-w-full items-center gap-1.5 text-xs text-accent-ink">
                                        <span class="break-all">{sourceToken}</span>
                                        <button
                                            type="button"
                                            class="shrink-0 rounded-full text-accent-ink hover:text-status-fail focus:outline-hidden focus:ring-2 focus:ring-focus"
                                            aria-label={$_('settings.integrations.birdnet.source_token_remove', { values: { source: sourceToken, camera } })}
                                            onclick={() => removeCameraAudioSourceToken(camera, sourceTokenIndex)}
                                        >
                                            &times;
                                        </button>
                                    </span>
                                {/each}
                            </div>
                        {/if}
                    </div>
                {/each}
                <datalist id="birdnet-source-options">
                    {#each birdnetMappingOptions as source}
                        <option value={source.value}></option>
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
                                {@const sourceValue = source.mapping_value || source.source_name}
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
                                                  values: { source: sourceValue, time: formatRelativeTime(source.last_seen), camera: availableCameras[0] },
                                                  default: '{source}, heard {time}. Select it to add it to {camera}.'
                                              })
                                            : sourceValue}
                                    >
                                        <span class="shrink-0 inline-flex h-5 w-5 items-center justify-center rounded-full bg-surface-sunken text-muted group-hover:bg-accent group-hover:text-accent-fg group-hover:group-disabled:bg-surface-sunken transition-colors text-xs font-semibold leading-none" aria-hidden="true">+</span>
                                        <span class="min-w-0 flex-1 text-xs font-mono font-semibold text-strong break-all leading-tight">{sourceValue}</span>
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
