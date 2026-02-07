<script lang="ts">
    import { _ } from 'svelte-i18n';

    // Props
    let {
        birdnetEnabled = $bindable(true),
        audioTopic = $bindable('birdnet/text'),
        audioBufferHours = $bindable(24),
        audioCorrelationWindowSeconds = $bindable(300),
        cameraAudioMapping = $bindable<Record<string, string>>({}),
        availableCameras,
        testingBirdNET = $bindable(false),
        birdweatherEnabled = $bindable(false),
        birdweatherStationToken = $bindable(''),
        testingBirdWeather,
        testingLlm,
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
        inaturalistConnectedUser = $bindable<string | null>(null),
        llmEnabled = $bindable(false),
        llmProvider = $bindable('gemini'),
        llmModel = $bindable('gemini-2.5-flash'),
        llmApiKey = $bindable(''),
        availableModels,
        locationAuto = $bindable(true),
        locationLat = $bindable<number | null>(null),
        locationLon = $bindable<number | null>(null),
        locationTemperatureUnit = $bindable<'celsius' | 'fahrenheit'>('celsius'),
        handleTestBirdNET,
        handleTestBirdWeather,
        handleTestLlm,
        initiateInaturalistOAuth,
        disconnectInaturalistOAuth,
        refreshInaturalistStatus,
        exportEbirdCsv
    }: {
        birdnetEnabled: boolean;
        audioTopic: string;
        audioBufferHours: number;
        audioCorrelationWindowSeconds: number;
        cameraAudioMapping: Record<string, string>;
        availableCameras: string[];
        testingBirdNET: boolean;
        birdweatherEnabled: boolean;
        birdweatherStationToken: string;
        testingBirdWeather: boolean;
        testingLlm: boolean;
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
        llmEnabled: boolean;
        llmProvider: string;
        llmModel: string;
        llmApiKey: string;
        availableModels: Array<{ value: string; label: string }>;
        locationAuto: boolean;
        locationLat: number | null;
        locationLon: number | null;
        locationTemperatureUnit: 'celsius' | 'fahrenheit';
        handleTestBirdNET: () => Promise<void>;
        handleTestBirdWeather: () => Promise<void>;
        handleTestLlm: () => Promise<void>;
        initiateInaturalistOAuth: () => Promise<{ authorization_url: string }>;
        disconnectInaturalistOAuth: () => Promise<{ status: string }>;
        refreshInaturalistStatus: () => Promise<void>;
        exportEbirdCsv: () => Promise<void>;
    } = $props();

    let inatDefaultsTouched = $state(false);

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
        if (ebirdApiKeySaved && ebirdApiKey) {
            ebirdApiKeySaved = false;
        }
    });
</script>

<div class="grid grid-cols-1 md:grid-cols-2 gap-6 items-start">
    <!-- BirdNET-Go -->
    <section class="card-base rounded-3xl p-8 backdrop-blur-md">
        <div class="flex items-center justify-between mb-6">
            <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-2xl bg-amber-500/10 flex items-center justify-center text-amber-600 dark:text-amber-400">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" /></svg>
                </div>
                <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">{$_('settings.integrations.birdnet.title')}</h3>
            </div>
            <button
                role="switch"
                aria-checked={birdnetEnabled}
                aria-label={$_('settings.integrations.birdnet.toggle_label')}
                onclick={() => birdnetEnabled = !birdnetEnabled}
                onkeydown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        birdnetEnabled = !birdnetEnabled;
                    }
                }}
                class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none {birdnetEnabled ? 'bg-teal-500' : 'bg-slate-300 dark:bg-slate-600'}"
            >
                <span class="sr-only">BirdNET-Go</span>
                <span class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 {birdnetEnabled ? 'translate-x-5' : 'translate-x-0'}"></span>
            </button>
        </div>

        <div class="space-y-6">
            <div>
                <label for="audio-topic" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.integrations.birdnet.mqtt_topic')}</label>
                <input
                    id="audio-topic"
                    type="text"
                    bind:value={audioTopic}
                    placeholder="birdnet/text"
                    aria-label={$_('settings.integrations.birdnet.mqtt_topic_label')}
                    class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm focus:ring-2 focus:ring-teal-500 outline-none"
                />
            </div>

            <div class="grid grid-cols-2 gap-4">
                <div>
                    <label for="audio-buffer" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.integrations.birdnet.audio_buffer_hours')}</label>
                    <input
                        id="audio-buffer"
                        type="number"
                        bind:value={audioBufferHours}
                        min="1"
                        max="168"
                        aria-label={$_('settings.integrations.birdnet.audio_buffer_label')}
                        class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm focus:ring-2 focus:ring-teal-500 outline-none"
                    />
                    <p class="mt-1 text-[10px] text-slate-400 font-bold italic">{$_('settings.integrations.birdnet.audio_buffer_help')}</p>
                </div>
                <div>
                    <label for="correlation-window" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.integrations.birdnet.match_window_seconds')}</label>
                    <input
                        id="correlation-window"
                        type="number"
                        bind:value={audioCorrelationWindowSeconds}
                        min="5"
                        max="3600"
                        aria-label={$_('settings.integrations.birdnet.match_window_label')}
                        class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm focus:ring-2 focus:ring-teal-500 outline-none"
                    />
                    <p class="mt-1 text-[10px] text-slate-400 font-bold italic">{$_('settings.integrations.birdnet.match_window_help')}</p>
                </div>
            </div>

            <button
                onclick={handleTestBirdNET}
                disabled={testingBirdNET}
                aria-label={$_('settings.integrations.birdnet.test_button')}
                class="w-full px-4 py-3 text-xs font-black uppercase tracking-widest rounded-2xl bg-amber-500 hover:bg-amber-600 text-white transition-all shadow-lg shadow-amber-500/20 disabled:opacity-50"
            >
                {testingBirdNET ? $_('settings.integrations.birdnet.test_loading') : $_('settings.integrations.birdnet.test_button')}
            </button>

            <div class="pt-4 border-t border-slate-100 dark:border-slate-700/50">
                <div id="sensor-mapping-label" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-4">{$_('settings.integrations.birdnet.sensor_mapping_title')}</div>
                <div class="space-y-3" role="group" aria-labelledby="sensor-mapping-label">
                    {#each availableCameras as camera}
                        <div class="flex items-center gap-3">
                            <span class="text-[10px] font-black text-slate-400 w-24 truncate uppercase">{camera}</span>
                            <input
                                type="text"
                                bind:value={cameraAudioMapping[camera]}
                                placeholder={$_('settings.integrations.birdnet.sensor_id_placeholder')}
                                aria-label={$_('settings.integrations.birdnet.sensor_id_label', { values: { camera } })}
                                class="flex-1 px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-xs font-bold"
                            />
                        </div>
                    {/each}
                    {#if availableCameras.length === 0}
                        <p class="text-[10px] text-slate-400 font-bold italic">{$_('settings.integrations.birdnet.sensor_mapping_empty')}</p>
                    {:else}
                        <p class="text-[10px] text-slate-400 font-bold italic">{$_('settings.integrations.birdnet.sensor_mapping_help')}</p>
                    {/if}
                </div>
            </div>
        </div>
    </section>

    <!-- iNaturalist -->
    <section class="card-base rounded-3xl p-8 backdrop-blur-md">
        <div class="flex items-center justify-between mb-6">
            <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-2xl bg-emerald-500/10 flex items-center justify-center text-emerald-600 dark:text-emerald-400">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v4m0 0a4 4 0 110 8m0-8a4 4 0 10-4 4m4-4v4m0 0a4 4 0 010 8m0-8a4 4 0 10-4 4" /></svg>
                </div>
                <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">{$_('settings.integrations.inaturalist.title')}</h3>
            </div>
            <button
                role="switch"
                aria-checked={inaturalistEnabled}
                aria-label={$_('settings.integrations.inaturalist.toggle_label')}
                onclick={() => inaturalistEnabled = !inaturalistEnabled}
                onkeydown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        inaturalistEnabled = !inaturalistEnabled;
                    }
                }}
                class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none {inaturalistEnabled ? 'bg-teal-500' : 'bg-slate-300 dark:bg-slate-600'}"
            >
                <span class="sr-only">iNaturalist</span>
                <span class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 {inaturalistEnabled ? 'translate-x-5' : 'translate-x-0'}"></span>
            </button>
        </div>

        <div class="space-y-5">
            <div class="grid grid-cols-1 gap-3">
                <div>
                    <label for="inat-client-id" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.integrations.inaturalist.client_id')}</label>
                    <input
                        id="inat-client-id"
                        type="text"
                        bind:value={inaturalistClientId}
                        placeholder={inaturalistClientIdSaved ? $_('settings.integrations.inaturalist.saved_placeholder') : $_('settings.integrations.inaturalist.client_id_placeholder')}
                        aria-label={$_('settings.integrations.inaturalist.client_id_label')}
                        class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm"
                    />
                </div>
                <div>
                    <label for="inat-client-secret" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.integrations.inaturalist.client_secret')}</label>
                    <input
                        id="inat-client-secret"
                        type="password"
                        bind:value={inaturalistClientSecret}
                        placeholder={inaturalistClientSecretSaved ? $_('settings.integrations.inaturalist.saved_placeholder') : $_('settings.integrations.inaturalist.client_secret_placeholder')}
                        aria-label={$_('settings.integrations.inaturalist.client_secret_label')}
                        class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm"
                    />
                </div>
            </div>

            <div class="grid grid-cols-2 gap-3">
                <div>
                    <label for="inat-lat" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.integrations.inaturalist.default_latitude')}</label>
                    <input
                        id="inat-lat"
                        type="number"
                        bind:value={inaturalistDefaultLat}
                        step="0.0001"
                        oninput={() => inatDefaultsTouched = true}
                        aria-label={$_('settings.integrations.inaturalist.default_latitude_label')}
                        class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm"
                    />
                </div>
                <div>
                    <label for="inat-lon" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.integrations.inaturalist.default_longitude')}</label>
                    <input
                        id="inat-lon"
                        type="number"
                        bind:value={inaturalistDefaultLon}
                        step="0.0001"
                        oninput={() => inatDefaultsTouched = true}
                        aria-label={$_('settings.integrations.inaturalist.default_longitude_label')}
                        class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm"
                    />
                </div>
            </div>

            <div>
                <label for="inat-place" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.integrations.inaturalist.default_place_guess')}</label>
                <input
                    id="inat-place"
                    type="text"
                    bind:value={inaturalistDefaultPlace}
                    oninput={() => inatDefaultsTouched = true}
                    placeholder={$_('settings.integrations.inaturalist.default_place_guess_placeholder')}
                    aria-label={$_('settings.integrations.inaturalist.default_place_guess_label')}
                    class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm"
                />
            </div>

            <div class="p-4 rounded-2xl bg-emerald-500/5 border border-emerald-500/10 space-y-3">
                <p class="text-xs text-emerald-700 dark:text-emerald-300">{$_('settings.integrations.inaturalist.oauth_desc')}</p>
                <p class="text-[10px] text-emerald-700/80 dark:text-emerald-300/80 font-semibold">
                    {$_('settings.integrations.inaturalist.app_owner_note')}
                </p>
                <div class="flex flex-wrap gap-2">
                    <button
                        onclick={async () => {
                            try {
                                const response = await initiateInaturalistOAuth();
                                window.open(response.authorization_url, '_blank', 'width=600,height=700');
                            } catch (error) {
                                console.error('iNaturalist OAuth error:', error);
                            }
                        }}
                        aria-label={$_('settings.integrations.inaturalist.connect_label')}
                        class="flex-1 min-w-[150px] px-4 py-2 rounded-xl bg-white dark:bg-slate-800 border-2 border-emerald-200 dark:border-emerald-700 hover:border-emerald-500 dark:hover:border-emerald-500 text-sm font-bold transition-all"
                    >
                        {$_('settings.integrations.inaturalist.connect')}
                    </button>
                    <button
                        onclick={async () => {
                            try {
                                await refreshInaturalistStatus();
                            } catch (error) {
                                console.error('iNaturalist refresh error:', error);
                            }
                        }}
                        aria-label={$_('settings.integrations.inaturalist.refresh_label')}
                        class="flex-1 min-w-[150px] px-4 py-2 rounded-xl bg-white dark:bg-slate-800 border-2 border-slate-200 dark:border-slate-700 hover:border-emerald-500 dark:hover:border-emerald-500 text-sm font-bold transition-all"
                    >
                        {$_('settings.integrations.inaturalist.refresh')}
                    </button>
                </div>
                {#if inaturalistConnectedUser}
                    <div class="flex items-center justify-between gap-2 p-3 bg-emerald-50 dark:bg-emerald-900/20 rounded-xl">
                        <span class="text-sm text-emerald-700 dark:text-emerald-300">{$_('settings.integrations.inaturalist.connected', { values: { user: inaturalistConnectedUser } })}</span>
                        <button
                            onclick={async () => {
                                try {
                                    await disconnectInaturalistOAuth();
                                    await refreshInaturalistStatus();
                                } catch (error) {
                                    console.error('iNaturalist disconnect error:', error);
                                }
                            }}
                            aria-label={$_('settings.integrations.inaturalist.disconnect_label')}
                            class="text-xs text-rose-600 dark:text-rose-400 hover:underline"
                        >
                            {$_('settings.integrations.inaturalist.disconnect')}
                        </button>
                    </div>
                {/if}
            </div>
        </div>
    </section>

    <!-- eBird -->
    <section class="card-base rounded-3xl p-8 backdrop-blur-md">
        <div class="flex items-center justify-between mb-6">
            <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-2xl bg-sky-500/10 flex items-center justify-center text-sky-600 dark:text-sky-400">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3c-3.314 0-6 2.686-6 6 0 2.673 1.74 4.94 4.143 5.716L9 21l3-2 3 2-1.143-6.284C16.26 13.94 18 11.673 18 9c0-3.314-2.686-6-6-6z" />
                    </svg>
                </div>
                <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">{$_('settings.integrations.ebird.title')}</h3>
            </div>
            <button
                role="switch"
                aria-checked={ebirdEnabled}
                aria-label={$_('settings.integrations.ebird.toggle_label')}
                onclick={() => ebirdEnabled = !ebirdEnabled}
                onkeydown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        ebirdEnabled = !ebirdEnabled;
                    }
                }}
                class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none {ebirdEnabled ? 'bg-teal-500' : 'bg-slate-300 dark:bg-slate-600'}"
            >
                <span class="sr-only">eBird</span>
                <span class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 {ebirdEnabled ? 'translate-x-5' : 'translate-x-0'}"></span>
            </button>
        </div>

        <div class="space-y-5">
            <div>
                <label for="ebird-api-key" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">
                    {$_('settings.integrations.ebird.api_key')}
                </label>
                <input
                    id="ebird-api-key"
                    type="password"
                    bind:value={ebirdApiKey}
                    placeholder={ebirdApiKeySaved ? $_('settings.integrations.ebird.saved_placeholder') : $_('settings.integrations.ebird.api_key_placeholder')}
                    aria-label={$_('settings.integrations.ebird.api_key_label')}
                    class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm focus:ring-2 focus:ring-teal-500 outline-none"
                />
                <p class="text-xs text-slate-500 mt-2">{$_('settings.integrations.ebird.api_key_desc')}</p>
            </div>

            <div class="grid grid-cols-2 gap-4">
                <div>
                    <label for="ebird-radius" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.integrations.ebird.radius')}</label>
                    <input
                        id="ebird-radius"
                        type="number"
                        min="1"
                        max="50"
                        bind:value={ebirdDefaultRadiusKm}
                        class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm focus:ring-2 focus:ring-teal-500 outline-none"
                    />
                </div>
                <div>
                    <label for="ebird-days" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.integrations.ebird.days_back')}</label>
                    <input
                        id="ebird-days"
                        type="number"
                        min="1"
                        max="30"
                        bind:value={ebirdDefaultDaysBack}
                        class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm focus:ring-2 focus:ring-teal-500 outline-none"
                    />
                </div>
            </div>

            <div class="grid grid-cols-2 gap-4">
                <div>
                    <label for="ebird-max-results" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.integrations.ebird.max_results')}</label>
                    <input
                        id="ebird-max-results"
                        type="number"
                        min="1"
                        max="200"
                        bind:value={ebirdMaxResults}
                        class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm focus:ring-2 focus:ring-teal-500 outline-none"
                    />
                </div>
                <div>
                    <label for="ebird-locale" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.integrations.ebird.locale')}</label>
                    <input
                        id="ebird-locale"
                        type="text"
                        bind:value={ebirdLocale}
                        class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm focus:ring-2 focus:ring-teal-500 outline-none"
                    />
                </div>
            </div>

            <div class="pt-4 border-t border-slate-100 dark:border-slate-700/50">
                <button
                    onclick={async () => {
                        try {
                            await exportEbirdCsv();
                        } catch (e) {
                            console.error('Failed to export CSV', e);
                            alert($_('settings.integrations.ebird.export_csv_error'));
                        }
                    }}
                    class="flex items-center gap-2 px-4 py-3 rounded-2xl bg-sky-50 dark:bg-sky-900/20 text-sky-600 dark:text-sky-400 font-bold text-xs uppercase tracking-widest hover:bg-sky-100 dark:hover:bg-sky-900/40 transition-colors w-full justify-center"
                >
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>
                    {$_('settings.integrations.ebird.export_csv')}
                </button>
                <p class="mt-2 text-[10px] text-slate-400 font-bold italic text-center">{$_('settings.integrations.ebird.export_csv_desc')}</p>
            </div>
        </div>
    </section>

    <!-- BirdWeather -->
    <section class="card-base rounded-3xl p-8 backdrop-blur-md">
        <div class="flex items-center justify-between mb-6">
            <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-2xl bg-indigo-500/10 flex items-center justify-center text-indigo-600 dark:text-indigo-400">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 10-9.78 2.096A4.001 4.001 0 003 15z" /></svg>
                </div>
                <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">{$_('settings.integrations.birdweather.title')}</h3>
            </div>
            <button
                role="switch"
                aria-checked={birdweatherEnabled}
                aria-label={$_('settings.integrations.birdweather.toggle_label')}
                onclick={() => birdweatherEnabled = !birdweatherEnabled}
                onkeydown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        birdweatherEnabled = !birdweatherEnabled;
                    }
                }}
                class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none {birdweatherEnabled ? 'bg-teal-500' : 'bg-slate-300 dark:bg-slate-600'}"
            >
                <span class="sr-only">BirdWeather</span>
                <span class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 {birdweatherEnabled ? 'translate-x-5' : 'translate-x-0'}"></span>
            </button>
        </div>

        <div class="space-y-6">
            <div>
                <label for="birdweather-token" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.integrations.birdweather.token')}</label>
                <input
                    id="birdweather-token"
                    type="password"
                    bind:value={birdweatherStationToken}
                    placeholder={$_('settings.integrations.birdweather.token_placeholder')}
                    aria-label={$_('settings.integrations.birdweather.token_label')}
                    class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm"
                />
                <p class="mt-2 text-[10px] text-slate-500 font-bold italic">{$_('settings.integrations.birdweather.token_desc')}</p>
            </div>
            <button
                onclick={handleTestBirdWeather}
                disabled={testingBirdWeather || !birdweatherStationToken}
                aria-label={$_('settings.integrations.birdweather.test_button')}
                class="w-full px-4 py-3 text-xs font-black uppercase tracking-widest rounded-2xl bg-indigo-500 hover:bg-indigo-600 text-white transition-all shadow-lg shadow-indigo-500/20 disabled:opacity-50"
            >
                {testingBirdWeather ? $_('settings.integrations.birdweather.test_loading') : $_('settings.integrations.birdweather.test_button')}
            </button>
        </div>
    </section>

    <!-- AI Intelligence -->
    <section class="card-base rounded-3xl p-8 backdrop-blur-md">
        <div class="flex items-center justify-between mb-6">
            <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-2xl bg-brand-500/10 flex items-center justify-center text-brand-500">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                </div>
                <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">{$_('settings.integrations.llm.title')}</h3>
            </div>
            <button
                role="switch"
                aria-checked={llmEnabled}
                aria-label={$_('settings.integrations.llm.toggle_label')}
                onclick={() => llmEnabled = !llmEnabled}
                onkeydown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        llmEnabled = !llmEnabled;
                    }
                }}
                class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none {llmEnabled ? 'bg-teal-500' : 'bg-slate-300 dark:bg-slate-600'}"
            >
                <span class="sr-only">AI Insights</span>
                <span class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 {llmEnabled ? 'translate-x-5' : 'translate-x-0'}"></span>
            </button>
        </div>

        <div class="space-y-6">
            <div class="grid grid-cols-2 gap-4">
                <div>
                    <label for="llm-provider" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.integrations.llm.provider')}</label>
                    <select
                        id="llm-provider"
                        bind:value={llmProvider}
                        aria-label={$_('settings.integrations.llm.provider_label')}
                        class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm"
                    >
                        <option value="gemini">{$_('settings.integrations.llm.providers.gemini')}</option>
                        <option value="openai">{$_('settings.integrations.llm.providers.openai')}</option>
                        <option value="claude">{$_('settings.integrations.llm.providers.claude')}</option>
                    </select>
                </div>
                <div>
                    <label for="llm-model" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.integrations.llm.model')}</label>
                    <select
                        id="llm-model"
                        bind:value={llmModel}
                        aria-label={$_('settings.integrations.llm.model_label')}
                        class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm"
                    >
                        {#each availableModels as model}
                            <option value={model.value}>{model.label}</option>
                        {/each}
                    </select>
                    <p class="mt-2 text-[10px] text-slate-500 font-bold italic">{$_('settings.integrations.llm.model_hint')}</p>
                </div>
            </div>
            <div>
                <label for="llm-api-key" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.integrations.llm.api_key')}</label>
                <input
                    id="llm-api-key"
                    type="password"
                    bind:value={llmApiKey}
                    aria-label={$_('settings.integrations.llm.api_key_label')}
                    class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm"
                />
            </div>
            <button
                onclick={handleTestLlm}
                disabled={testingLlm || !llmEnabled || !llmApiKey}
                aria-label={$_('settings.integrations.llm.test_label')}
                class="w-full px-4 py-3 text-xs font-black uppercase tracking-widest rounded-2xl bg-brand-500 hover:bg-brand-600 text-white transition-all shadow-lg shadow-brand-500/20 disabled:opacity-50"
            >
                {testingLlm ? $_('settings.integrations.llm.test_loading') : $_('settings.integrations.llm.test_button')}
            </button>
            <p class="text-[10px] text-slate-500 font-bold italic">{$_('settings.integrations.llm.test_hint')}</p>
        </div>
    </section>

    <!-- Location & Weather -->
    <section class="card-base rounded-3xl p-8 backdrop-blur-md">
        <div class="flex items-center justify-between mb-6">
            <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-2xl bg-orange-500/10 flex items-center justify-center text-orange-600 dark:text-orange-400">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" /></svg>
                </div>
                <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">{$_('settings.location.title')}</h3>
            </div>

            <div class="flex items-center gap-3">
                <span class="text-[10px] font-black uppercase tracking-widest {locationAuto ? 'text-teal-500' : 'text-slate-400'}">{$_('settings.location.auto')}</span>
                <button
                    role="switch"
                    aria-checked={locationAuto}
                    aria-label="Toggle location auto-detect"
                    onclick={() => locationAuto = !locationAuto}
                    onkeydown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            locationAuto = !locationAuto;
                        }
                    }}
                    class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none {locationAuto ? 'bg-teal-500' : 'bg-slate-300 dark:bg-slate-600'}"
                >
                    <span class="sr-only">Location auto-detect</span>
                    <span class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 {locationAuto ? 'translate-x-5' : 'translate-x-0'}"></span>
                </button>
                <span class="text-[10px] font-black uppercase tracking-widest {!locationAuto ? 'text-orange-500' : 'text-slate-400'}">{$_('settings.location.manual')}</span>
            </div>
        </div>

        <div class="space-y-6">
            <p class="text-xs font-bold text-slate-500 leading-relaxed uppercase tracking-wider">{$_('settings.location.desc')}</p>
            {#if !locationAuto}
                <div class="grid grid-cols-2 gap-4 animate-in fade-in slide-in-from-top-2">
                    <div>
                        <label for="location-lat" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.location.latitude')}</label>
                        <input
                            id="location-lat"
                            type="number"
                            step="any"
                            bind:value={locationLat}
                            aria-label="{$_('settings.location.latitude')}"
                            class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm"
                        />
                    </div>
                    <div>
                        <label for="location-lon" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.location.longitude')}</label>
                        <input
                            id="location-lon"
                            type="number"
                            step="any"
                            bind:value={locationLon}
                            aria-label="{$_('settings.location.longitude')}"
                            class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm"
                        />
                    </div>
                </div>
            {:else}
                <div class="p-4 rounded-2xl bg-teal-500/5 border border-teal-500/10 text-teal-600 dark:text-teal-400 text-xs font-black uppercase tracking-widest text-center">{$_('settings.location.auto_detect_enabled')}</div>
            {/if}

            <div>
                <label for="temperature-unit" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.location.temperature_unit')}</label>
                <select
                    id="temperature-unit"
                    bind:value={locationTemperatureUnit}
                    aria-label="{$_('settings.location.temperature_unit')}"
                    class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm focus:ring-2 focus:ring-teal-500 outline-none"
                >
                    <option value="celsius">{$_('settings.location.celsius')}</option>
                    <option value="fahrenheit">{$_('settings.location.fahrenheit')}</option>
                </select>
                <p class="mt-1 text-[10px] text-slate-400 font-bold italic">{$_('settings.location.temperature_unit_desc')}</p>
            </div>
        </div>
    </section>
</div>
