<script lang="ts">
    import { _ } from 'svelte-i18n';
    import { locationTogglePresentation } from '../../settings/location-toggle';
    import SecretSavedBadge from './SecretSavedBadge.svelte';
    import SettingsCard from './_primitives/SettingsCard.svelte';
    import SettingsRow from './_primitives/SettingsRow.svelte';
    import SettingsToggle from './_primitives/SettingsToggle.svelte';
    import SettingsInput from './_primitives/SettingsInput.svelte';
    import SettingsSelect from './_primitives/SettingsSelect.svelte';
    import AdvancedSection from './_primitives/AdvancedSection.svelte';

    let {
        birdnetEnabled = $bindable(true),
        audioTopic = $bindable('birdnet/text'),
        audioBufferHours = $bindable(24),
        audioCorrelationWindowSeconds = $bindable(300),
        cameraAudioMapping = $bindable<Record<string, string>>({}),
        birdnetSourceOptions = [],
        loadingBirdnetSources = false,
        birdnetSourcesError = null,
        availableCameras = [],
        testingBirdNET = $bindable(false),
        birdweatherEnabled = $bindable(false),
        birdweatherStationToken = $bindable(''),
        ebirdEnabled = $bindable(false),
        ebirdApiKey = $bindable(''),
        ebirdApiKeySaved = $bindable(false),
        ebirdDefaultRadiusKm = $bindable(25),
        ebirdDefaultDaysBack = $bindable(14),
        ebirdMaxResults = $bindable(25),
        ebirdLocale = $bindable('en'),
        inaturalistEnabled = $bindable(false),
        inaturalistClientId = $bindable(''),
        inaturalistClientSecret = $bindable(''),
        inaturalistClientIdSaved = $bindable(false),
        inaturalistClientSecretSaved = $bindable(false),
        inaturalistDefaultLat = $bindable<number | null>(null),
        inaturalistDefaultLon = $bindable<number | null>(null),
        inaturalistDefaultPlace = $bindable(''),
        inaturalistConnectedUser = $bindable(null),
        locationAuto = $bindable(true),
        locationLat = $bindable<number | null>(null),
        locationLon = $bindable<number | null>(null),
        locationState = $bindable(''),
        locationCountry = $bindable(''),
        locationWeatherUnitSystem = $bindable<'metric' | 'imperial' | 'british'>('metric'),
        handleTestBirdNET,
        handleTestBirdWeather,
        initiateInaturalistOAuth,
        disconnectInaturalistOAuth,
        refreshInaturalistStatus,
        exportEbirdCsv,
        birdweatherStationTokenSaved = $bindable(false),
        onActionFeedback = (_type: 'success' | 'error', _text: string) => {}
    }: {
        birdnetEnabled: boolean;
        audioTopic: string;
        audioBufferHours: number;
        audioCorrelationWindowSeconds: number;
        cameraAudioMapping: Record<string, string>;
        birdnetSourceOptions: Array<{ source_name: string; last_seen: string; sample_source_id?: string | null; seen_count?: number }>;
        loadingBirdnetSources: boolean;
        birdnetSourcesError: string | null;
        availableCameras: string[];
        testingBirdNET: boolean;
        birdweatherEnabled: boolean;
        birdweatherStationToken: string;
        ebirdEnabled: boolean;
        ebirdApiKey: string;
        ebirdApiKeySaved: boolean;
        ebirdDefaultRadiusKm: number;
        ebirdDefaultDaysBack: number;
        ebirdMaxResults: number;
        ebirdLocale: string;
        inaturalistEnabled: boolean;
        inaturalistClientId: string;
        inaturalistClientSecret: string;
        inaturalistClientIdSaved: boolean;
        inaturalistClientSecretSaved: boolean;
        inaturalistDefaultLat: number | null;
        inaturalistDefaultLon: number | null;
        inaturalistDefaultPlace: string;
        inaturalistConnectedUser: string | null;
        locationAuto: boolean;
        locationLat: number | null;
        locationLon: number | null;
        locationState: string;
        locationCountry: string;
        locationWeatherUnitSystem: 'metric' | 'imperial' | 'british';
        handleTestBirdNET: () => Promise<void>;
        handleTestBirdWeather: () => Promise<void>;
        initiateInaturalistOAuth: () => Promise<{ authorization_url: string }>;
        disconnectInaturalistOAuth: () => Promise<{ status: string }>;
        refreshInaturalistStatus: () => Promise<void>;
        exportEbirdCsv: (range?: { from?: string; to?: string }) => Promise<void>;
        birdweatherStationTokenSaved: boolean;
        onActionFeedback: (type: 'success' | 'error', text: string) => void;
    } = $props();

    let inatDefaultsTouched = $state(false);
    let inatConnecting = $state(false);
    let inatRefreshing = $state(false);
    let inatDisconnecting = $state(false);
    let exportingEbirdCsv = $state(false);
    let testingBirdWeather = $state(false);
    let ebirdExportEverything = $state(true);
    let ebirdExportFrom = $state('');
    let ebirdExportTo = $state('');
    let ebirdExportRangeError = $state('');

    function actionErrorMessage(error: unknown) {
        if (error instanceof Error && error.message.trim().length > 0) return error.message;
        return 'Action failed';
    }

    $effect(() => {
        if (inatDefaultsTouched) return;
        if (inaturalistDefaultLat === null && locationLat !== null && locationLat !== undefined) {
            inaturalistDefaultLat = locationLat;
        }
        if (inaturalistDefaultLon === null && locationLon !== null && locationLon !== undefined) {
            inaturalistDefaultLon = locationLon;
        }
    });

    $effect(() => {
        if (ebirdApiKeySaved && ebirdApiKey) ebirdApiKeySaved = false;
    });

    $effect(() => {
        if (birdweatherStationTokenSaved && birdweatherStationToken) birdweatherStationTokenSaved = false;
    });

    $effect(() => {
        if (ebirdExportEverything) {
            ebirdExportRangeError = '';
            return;
        }
        if (ebirdExportFrom && ebirdExportTo && ebirdExportFrom > ebirdExportTo) {
            ebirdExportRangeError = $_('settings.integrations.ebird.export_range_error');
            return;
        }
        ebirdExportRangeError = '';
    });

    function setEbirdExportEverything(next: boolean) {
        ebirdExportEverything = next;
        if (ebirdExportEverything) {
            ebirdExportFrom = '';
            ebirdExportTo = '';
            ebirdExportRangeError = '';
        }
    }

    let locationToggle = $derived(locationTogglePresentation(locationAuto));

    const buttonPrimaryClass = 'px-4 py-3 text-xs font-black uppercase tracking-widest rounded-2xl bg-teal-500 hover:bg-teal-600 text-white transition-all shadow-lg shadow-teal-500/20 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-teal-400 dark:focus:ring-offset-slate-900 disabled:opacity-50 disabled:cursor-not-allowed';
    const buttonSecondaryClass = 'px-4 py-3 text-xs font-black uppercase tracking-widest rounded-2xl bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 border border-slate-200 dark:border-slate-700 transition-all focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-slate-400 dark:focus:ring-offset-slate-900 disabled:opacity-50 disabled:cursor-not-allowed';
</script>

<div class="grid grid-cols-1 md:grid-cols-2 gap-6 items-stretch">
    <SettingsCard icon="🎤" title={$_('settings.integrations.birdnet.title')}>
        <SettingsRow
            labelId="setting-birdnet-enabled"
            label={$_('settings.integrations.birdnet.title')}
            description={$_('settings.integrations.birdnet.toggle_label')}
        >
            <SettingsToggle
                checked={birdnetEnabled}
                labelledBy="setting-birdnet-enabled"
                srLabel={$_('settings.integrations.birdnet.title')}
                onchange={(v) => (birdnetEnabled = v)}
            />
        </SettingsRow>

        <SettingsRow
            labelId="setting-audio-topic"
            label={$_('settings.integrations.birdnet.mqtt_topic')}
            layout="stacked"
        >
            <SettingsInput
                id="audio-topic"
                type="text"
                value={audioTopic}
                placeholder={$_('settings.integrations.birdnet.mqtt_topic_placeholder')}
                ariaLabel={$_('settings.integrations.birdnet.mqtt_topic_label')}
                oninput={(v) => (audioTopic = v)}
            />
        </SettingsRow>

        <button
            type="button"
            onclick={handleTestBirdNET}
            disabled={testingBirdNET}
            aria-label={$_('settings.integrations.birdnet.test_button')}
            class="w-full {buttonPrimaryClass}"
        >
            {testingBirdNET ? $_('settings.integrations.birdnet.test_loading') : $_('settings.integrations.birdnet.test_button')}
        </button>

        <AdvancedSection
            id="integrations-birdnet-advanced"
            title={$_('settings.integrations.birdnet.advanced_title', { default: 'Audio buffer & sensor mapping' })}
        >
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <SettingsRow
                    labelId="setting-audio-buffer"
                    label={$_('settings.integrations.birdnet.audio_buffer_hours')}
                    description={$_('settings.integrations.birdnet.audio_buffer_help')}
                    layout="stacked"
                >
                    <SettingsInput
                        id="audio-buffer"
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
                <div class="space-y-2" role="group">
                    {#each availableCameras as camera}
                        <div class="flex items-center gap-3">
                            <span class="text-[10px] font-black text-slate-400 w-24 truncate uppercase">{camera}</span>
                            <input
                                type="text"
                                list="birdnet-source-options"
                                bind:value={cameraAudioMapping[camera]}
                                placeholder={$_('settings.integrations.birdnet.sensor_id_placeholder')}
                                aria-label={$_('settings.integrations.birdnet.sensor_id_label', { values: { camera } })}
                                class="flex-1 px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-xs font-bold focus:ring-2 focus:ring-teal-500 outline-none"
                            />
                        </div>
                    {/each}
                    <datalist id="birdnet-source-options">
                        {#each birdnetSourceOptions as source}
                            <option value={source.source_name}></option>
                        {/each}
                    </datalist>
                    <div class="rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50/70 dark:bg-slate-900/30 p-3">
                        <div class="text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">
                            {$_('settings.integrations.birdnet.source_discovery_title')}
                        </div>
                        {#if loadingBirdnetSources}
                            <p class="text-[10px] text-slate-400 font-bold italic">{$_('settings.integrations.birdnet.source_discovery_loading')}</p>
                        {:else if birdnetSourcesError}
                            <p class="text-[10px] text-rose-500 font-bold italic">{$_('settings.integrations.birdnet.source_discovery_error')}</p>
                        {:else if birdnetSourceOptions.length === 0}
                            <p class="text-[10px] text-slate-400 font-bold italic">{$_('settings.integrations.birdnet.source_discovery_empty')}</p>
                        {:else}
                            <p class="text-[10px] text-slate-400 font-bold italic mb-2">{$_('settings.integrations.birdnet.source_discovery_help')}</p>
                            <div class="space-y-2">
                                {#each birdnetSourceOptions as source}
                                    <div class="flex items-center justify-between gap-3 rounded-lg bg-white/80 dark:bg-slate-950/40 border border-slate-200/70 dark:border-slate-700/70 px-2 py-1.5">
                                        <div class="min-w-0">
                                            <div class="text-xs font-black text-slate-800 dark:text-slate-100 truncate">{source.source_name}</div>
                                            <div class="text-[10px] text-slate-500 truncate">
                                                {#if source.sample_source_id}ID: {source.sample_source_id}{/if}
                                                {#if source.seen_count}{#if source.sample_source_id} · {/if}Seen: {source.seen_count}{/if}
                                            </div>
                                        </div>
                                        <div class="text-[10px] font-bold text-slate-500 whitespace-nowrap">{source.last_seen}</div>
                                    </div>
                                {/each}
                            </div>
                        {/if}
                    </div>
                </div>
            </SettingsRow>
        </AdvancedSection>
    </SettingsCard>

    <SettingsCard icon="🌿" title={$_('settings.integrations.inaturalist.title')}>
        <SettingsRow
            labelId="setting-inat-enabled"
            label={$_('settings.integrations.inaturalist.title')}
            description={$_('settings.integrations.inaturalist.toggle_label')}
        >
            <SettingsToggle
                checked={inaturalistEnabled}
                labelledBy="setting-inat-enabled"
                srLabel={$_('settings.integrations.inaturalist.title')}
                onchange={(v) => (inaturalistEnabled = v)}
            />
        </SettingsRow>

        <SettingsRow
            labelId="setting-inat-client-id"
            label={$_('settings.integrations.inaturalist.client_id')}
            layout="stacked"
        >
            <div class="space-y-2">
                {#if inaturalistClientIdSaved}<div class="flex justify-end"><SecretSavedBadge /></div>{/if}
                <SettingsInput
                    id="inat-client-id"
                    type="text"
                    value={inaturalistClientId}
                    placeholder={$_('settings.integrations.inaturalist.client_id_placeholder')}
                    ariaLabel={$_('settings.integrations.inaturalist.client_id_label')}
                    oninput={(v) => (inaturalistClientId = v)}
                />
            </div>
        </SettingsRow>

        <SettingsRow
            labelId="setting-inat-client-secret"
            label={$_('settings.integrations.inaturalist.client_secret')}
            layout="stacked"
        >
            <div class="space-y-2">
                {#if inaturalistClientSecretSaved}<div class="flex justify-end"><SecretSavedBadge /></div>{/if}
                <SettingsInput
                    id="inat-client-secret"
                    type="password"
                    autocomplete="off"
                    value={inaturalistClientSecret}
                    placeholder={$_('settings.integrations.inaturalist.client_secret_placeholder')}
                    ariaLabel={$_('settings.integrations.inaturalist.client_secret_label')}
                    oninput={(v) => (inaturalistClientSecret = v)}
                />
            </div>
        </SettingsRow>

        <div class="rounded-2xl bg-slate-50 dark:bg-slate-900/50 border border-slate-100 dark:border-slate-700/50 p-4 space-y-3">
            <p class="text-xs text-slate-700 dark:text-slate-200">{$_('settings.integrations.inaturalist.oauth_desc')}</p>
            <p class="text-[10px] text-slate-500 font-semibold">{$_('settings.integrations.inaturalist.app_owner_note')}</p>
            <div class="flex flex-wrap gap-2">
                <button
                    type="button"
                    onclick={async () => {
                        try {
                            inatConnecting = true;
                            const response = await initiateInaturalistOAuth();
                            window.open(response.authorization_url, '_blank', 'width=600,height=700');
                            onActionFeedback('success', $_('settings.integrations.inaturalist.connect'));
                        } catch (error) {
                            onActionFeedback('error', actionErrorMessage(error));
                        } finally {
                            inatConnecting = false;
                        }
                    }}
                    aria-label={$_('settings.integrations.inaturalist.connect_label')}
                    disabled={inatConnecting || inatRefreshing || inatDisconnecting}
                    class="flex-1 min-w-[150px] {buttonPrimaryClass}"
                >
                    {inatConnecting ? $_('common.testing') : $_('settings.integrations.inaturalist.connect')}
                </button>
                <button
                    type="button"
                    onclick={async () => {
                        try {
                            inatRefreshing = true;
                            await refreshInaturalistStatus();
                            onActionFeedback('success', $_('settings.integrations.inaturalist.refresh'));
                        } catch (error) {
                            onActionFeedback('error', actionErrorMessage(error));
                        } finally {
                            inatRefreshing = false;
                        }
                    }}
                    aria-label={$_('settings.integrations.inaturalist.refresh_label')}
                    disabled={inatRefreshing || inatConnecting || inatDisconnecting}
                    class="flex-1 min-w-[150px] {buttonSecondaryClass}"
                >
                    {inatRefreshing ? $_('common.testing') : $_('settings.integrations.inaturalist.refresh')}
                </button>
            </div>
            {#if inaturalistConnectedUser}
                <div class="flex items-center justify-between gap-2 p-3 bg-emerald-50 dark:bg-emerald-900/20 rounded-xl">
                    <span class="text-sm text-emerald-700 dark:text-emerald-300">{$_('settings.integrations.inaturalist.connected', { values: { user: inaturalistConnectedUser } })}</span>
                    <button
                        type="button"
                        onclick={async () => {
                            try {
                                inatDisconnecting = true;
                                await disconnectInaturalistOAuth();
                                await refreshInaturalistStatus();
                                onActionFeedback('success', $_('settings.integrations.inaturalist.disconnect'));
                            } catch (error) {
                                onActionFeedback('error', actionErrorMessage(error));
                            } finally {
                                inatDisconnecting = false;
                            }
                        }}
                        aria-label={$_('settings.integrations.inaturalist.disconnect_label')}
                        disabled={inatDisconnecting}
                        class="text-xs text-rose-600 dark:text-rose-400 hover:underline"
                    >
                        {inatDisconnecting ? $_('common.testing') : $_('settings.integrations.inaturalist.disconnect')}
                    </button>
                </div>
            {/if}
        </div>

        <AdvancedSection
            id="integrations-inat-advanced"
            title={$_('settings.integrations.inaturalist.advanced_title', { default: 'Default location' })}
        >
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <SettingsRow
                    labelId="setting-inat-lat"
                    label={$_('settings.integrations.inaturalist.default_latitude')}
                    layout="stacked"
                >
                    <SettingsInput
                        id="inat-lat"
                        type="number"
                        step={0.0001}
                        value={inaturalistDefaultLat ?? ''}
                        ariaLabel={$_('settings.integrations.inaturalist.default_latitude_label')}
                        oninput={(v) => { inatDefaultsTouched = true; inaturalistDefaultLat = v === '' ? null : Number(v); }}
                    />
                </SettingsRow>
                <SettingsRow
                    labelId="setting-inat-lon"
                    label={$_('settings.integrations.inaturalist.default_longitude')}
                    layout="stacked"
                >
                    <SettingsInput
                        id="inat-lon"
                        type="number"
                        step={0.0001}
                        value={inaturalistDefaultLon ?? ''}
                        ariaLabel={$_('settings.integrations.inaturalist.default_longitude_label')}
                        oninput={(v) => { inatDefaultsTouched = true; inaturalistDefaultLon = v === '' ? null : Number(v); }}
                    />
                </SettingsRow>
            </div>
            <SettingsRow
                labelId="setting-inat-place"
                label={$_('settings.integrations.inaturalist.default_place_guess')}
                layout="stacked"
            >
                <SettingsInput
                    id="inat-place"
                    type="text"
                    value={inaturalistDefaultPlace}
                    placeholder={$_('settings.integrations.inaturalist.default_place_guess_placeholder')}
                    ariaLabel={$_('settings.integrations.inaturalist.default_place_guess_label')}
                    oninput={(v) => { inatDefaultsTouched = true; inaturalistDefaultPlace = v; }}
                />
            </SettingsRow>
        </AdvancedSection>
    </SettingsCard>

    <SettingsCard icon="🐦" title={$_('settings.integrations.ebird.title')}>
        <SettingsRow
            labelId="setting-ebird-enabled"
            label={$_('settings.integrations.ebird.title')}
            description={$_('settings.integrations.ebird.toggle_label')}
        >
            <SettingsToggle
                checked={ebirdEnabled}
                labelledBy="setting-ebird-enabled"
                srLabel={$_('settings.integrations.ebird.title')}
                onchange={(v) => (ebirdEnabled = v)}
            />
        </SettingsRow>

        <SettingsRow
            labelId="setting-ebird-api-key"
            label={$_('settings.integrations.ebird.api_key')}
            description={$_('settings.integrations.ebird.api_key_desc')}
            layout="stacked"
        >
            <div class="space-y-2">
                {#if ebirdApiKeySaved}<div class="flex justify-end"><SecretSavedBadge /></div>{/if}
                <SettingsInput
                    id="ebird-api-key"
                    type="password"
                    autocomplete="off"
                    value={ebirdApiKey}
                    placeholder={$_('settings.integrations.ebird.api_key_placeholder')}
                    ariaLabel={$_('settings.integrations.ebird.api_key_label')}
                    oninput={(v) => (ebirdApiKey = v)}
                />
            </div>
        </SettingsRow>

        <SettingsRow
            labelId="setting-ebird-export-mode"
            label={$_('settings.integrations.ebird.export_everything')}
            description={$_('settings.integrations.ebird.export_everything_help')}
        >
            <SettingsToggle
                checked={ebirdExportEverything}
                labelledBy="setting-ebird-export-mode"
                srLabel={$_('settings.integrations.ebird.export_everything_label')}
                onchange={(v) => setEbirdExportEverything(v)}
            />
        </SettingsRow>

        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <SettingsRow
                labelId="setting-ebird-export-from"
                label={$_('settings.integrations.ebird.export_from')}
                layout="stacked"
            >
                <input
                    id="ebird-export-from"
                    type="date"
                    bind:value={ebirdExportFrom}
                    disabled={ebirdExportEverything}
                    aria-label={$_('settings.integrations.ebird.export_from_label')}
                    class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm focus:ring-2 focus:ring-teal-500 outline-none disabled:opacity-50 disabled:cursor-not-allowed"
                />
            </SettingsRow>
            <SettingsRow
                labelId="setting-ebird-export-to"
                label={$_('settings.integrations.ebird.export_to')}
                layout="stacked"
            >
                <input
                    id="ebird-export-to"
                    type="date"
                    bind:value={ebirdExportTo}
                    disabled={ebirdExportEverything}
                    aria-label={$_('settings.integrations.ebird.export_to_label')}
                    class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm focus:ring-2 focus:ring-teal-500 outline-none disabled:opacity-50 disabled:cursor-not-allowed"
                />
            </SettingsRow>
        </div>
        <p class="text-[10px] text-slate-400 font-bold italic">{$_('settings.integrations.ebird.export_range_help')}</p>
        {#if ebirdExportRangeError}
            <p class="text-[10px] text-rose-500 font-bold">{ebirdExportRangeError}</p>
        {/if}
        <button
            type="button"
            onclick={async () => {
                try {
                    exportingEbirdCsv = true;
                    await exportEbirdCsv({
                        from: ebirdExportEverything ? undefined : ebirdExportFrom || undefined,
                        to: ebirdExportEverything ? undefined : ebirdExportTo || undefined
                    });
                    onActionFeedback('success', $_('settings.integrations.ebird.export_csv'));
                } catch (e) {
                    onActionFeedback('error', $_('settings.integrations.ebird.export_csv_error'));
                } finally {
                    exportingEbirdCsv = false;
                }
            }}
            disabled={exportingEbirdCsv || !!ebirdExportRangeError}
            class="w-full {buttonPrimaryClass}"
        >
            {exportingEbirdCsv ? $_('common.testing') : $_('settings.integrations.ebird.export_csv')}
        </button>
        <p class="text-[10px] text-slate-400 font-bold italic text-center">{$_('settings.integrations.ebird.export_csv_desc')}</p>

        <AdvancedSection
            id="integrations-ebird-advanced"
            title={$_('settings.integrations.ebird.advanced_title', { default: 'Hotspot search defaults' })}
        >
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <SettingsRow
                    labelId="setting-ebird-radius"
                    label={$_('settings.integrations.ebird.radius')}
                    layout="stacked"
                >
                    <SettingsInput
                        id="ebird-radius"
                        type="number"
                        min={1}
                        max={50}
                        value={ebirdDefaultRadiusKm}
                        ariaLabel={$_('settings.integrations.ebird.radius')}
                        oninput={(v) => (ebirdDefaultRadiusKm = Number(v) || 0)}
                    />
                </SettingsRow>
                <SettingsRow
                    labelId="setting-ebird-days"
                    label={$_('settings.integrations.ebird.days_back')}
                    layout="stacked"
                >
                    <SettingsInput
                        id="ebird-days"
                        type="number"
                        min={1}
                        max={30}
                        value={ebirdDefaultDaysBack}
                        ariaLabel={$_('settings.integrations.ebird.days_back')}
                        oninput={(v) => (ebirdDefaultDaysBack = Number(v) || 0)}
                    />
                </SettingsRow>
                <SettingsRow
                    labelId="setting-ebird-max-results"
                    label={$_('settings.integrations.ebird.max_results')}
                    layout="stacked"
                >
                    <SettingsInput
                        id="ebird-max-results"
                        type="number"
                        min={1}
                        max={200}
                        value={ebirdMaxResults}
                        ariaLabel={$_('settings.integrations.ebird.max_results')}
                        oninput={(v) => (ebirdMaxResults = Number(v) || 0)}
                    />
                </SettingsRow>
                <SettingsRow
                    labelId="setting-ebird-locale"
                    label={$_('settings.integrations.ebird.locale')}
                    layout="stacked"
                >
                    <SettingsInput
                        id="ebird-locale"
                        type="text"
                        value={ebirdLocale}
                        ariaLabel={$_('settings.integrations.ebird.locale')}
                        oninput={(v) => (ebirdLocale = v)}
                    />
                </SettingsRow>
            </div>
        </AdvancedSection>
    </SettingsCard>

    <SettingsCard icon="🌦️" title={$_('settings.integrations.birdweather.title')}>
        <SettingsRow
            labelId="setting-birdweather-enabled"
            label={$_('settings.integrations.birdweather.title')}
            description={$_('settings.integrations.birdweather.toggle_label')}
        >
            <SettingsToggle
                checked={birdweatherEnabled}
                labelledBy="setting-birdweather-enabled"
                srLabel={$_('settings.integrations.birdweather.title')}
                onchange={(v) => (birdweatherEnabled = v)}
            />
        </SettingsRow>

        <SettingsRow
            labelId="setting-birdweather-token"
            label={$_('settings.integrations.birdweather.token')}
            description={$_('settings.integrations.birdweather.token_desc')}
            layout="stacked"
        >
            <div class="space-y-2">
                {#if birdweatherStationTokenSaved}<div class="flex justify-end"><SecretSavedBadge /></div>{/if}
                <SettingsInput
                    id="birdweather-token"
                    type="password"
                    autocomplete="off"
                    value={birdweatherStationToken}
                    placeholder={$_('settings.integrations.birdweather.token_placeholder')}
                    ariaLabel={$_('settings.integrations.birdweather.token_label')}
                    oninput={(v) => (birdweatherStationToken = v)}
                />
            </div>
        </SettingsRow>

        <button
            type="button"
            onclick={handleTestBirdWeather}
            disabled={testingBirdWeather || !birdweatherStationToken}
            aria-label={$_('settings.integrations.birdweather.test_button')}
            class="w-full {buttonPrimaryClass}"
        >
            {testingBirdWeather ? $_('settings.integrations.birdweather.test_loading') : $_('settings.integrations.birdweather.test_button')}
        </button>
    </SettingsCard>

    <div class="md:col-span-2">
        <SettingsCard
            icon="📍"
            title={$_('settings.location.title')}
            description={$_('settings.location.desc')}
        >
            <SettingsRow
                labelId="setting-location-mode"
                label={$_('settings.location.auto')}
                description={locationToggle.autoActive ? $_('settings.location.auto_detect_enabled') : $_('settings.location.manual')}
            >
                <SettingsToggle
                    checked={locationAuto}
                    labelledBy="setting-location-mode"
                    srLabel={$_('settings.location.auto')}
                    onchange={(v) => (locationAuto = v)}
                />
            </SettingsRow>

            {#if !locationAuto}
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 animate-in fade-in slide-in-from-top-2">
                    <SettingsRow
                        labelId="setting-location-lat"
                        label={$_('settings.location.latitude')}
                        layout="stacked"
                    >
                        <SettingsInput
                            id="location-lat"
                            type="number"
                            value={locationLat ?? ''}
                            ariaLabel={$_('settings.location.latitude')}
                            oninput={(v) => (locationLat = v === '' ? null : Number(v))}
                        />
                    </SettingsRow>
                    <SettingsRow
                        labelId="setting-location-lon"
                        label={$_('settings.location.longitude')}
                        layout="stacked"
                    >
                        <SettingsInput
                            id="location-lon"
                            type="number"
                            value={locationLon ?? ''}
                            ariaLabel={$_('settings.location.longitude')}
                            oninput={(v) => (locationLon = v === '' ? null : Number(v))}
                        />
                    </SettingsRow>
                    <SettingsRow
                        labelId="setting-location-state"
                        label={$_('settings.location.state')}
                        layout="stacked"
                    >
                        <SettingsInput
                            id="location-state"
                            type="text"
                            value={locationState}
                            ariaLabel={$_('settings.location.state')}
                            oninput={(v) => (locationState = v)}
                        />
                    </SettingsRow>
                    <SettingsRow
                        labelId="setting-location-country"
                        label={$_('settings.location.country')}
                        layout="stacked"
                    >
                        <SettingsInput
                            id="location-country"
                            type="text"
                            value={locationCountry}
                            ariaLabel={$_('settings.location.country')}
                            oninput={(v) => (locationCountry = v)}
                        />
                    </SettingsRow>
                </div>
            {/if}

            <SettingsRow
                labelId="setting-weather-units"
                label={$_('settings.location.weather_unit_system')}
                description={$_('settings.location.weather_unit_system_desc')}
                layout="stacked"
            >
                <SettingsSelect
                    id="weather-unit-system"
                    value={locationWeatherUnitSystem}
                    ariaLabel={$_('settings.location.weather_unit_system')}
                    options={[
                        { value: 'metric', label: $_('settings.location.metric') },
                        { value: 'imperial', label: $_('settings.location.imperial') },
                        { value: 'british', label: $_('settings.location.british') }
                    ]}
                    onchange={(v) => (locationWeatherUnitSystem = v as 'metric' | 'imperial' | 'british')}
                />
            </SettingsRow>
        </SettingsCard>
    </div>
</div>
