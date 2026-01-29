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
        llmEnabled = $bindable(false),
        llmProvider = $bindable('gemini'),
        llmModel = $bindable('gemini-3-flash-preview'),
        llmApiKey = $bindable(''),
        availableModels,
        locationAuto = $bindable(true),
        locationLat = $bindable<number | null>(null),
        locationLon = $bindable<number | null>(null),
        locationTemperatureUnit = $bindable<'celsius' | 'fahrenheit'>('celsius'),
        handleTestBirdNET,
        handleTestBirdWeather
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
    } = $props();
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

    <!-- BirdWeather -->
    <section class="card-base rounded-3xl p-8 backdrop-blur-md">
        <div class="flex items-center justify-between mb-6">
            <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-2xl bg-indigo-500/10 flex items-center justify-center text-indigo-600 dark:text-indigo-400">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 10-9.78 2.096A4.001 4.001 0 003 15z" /></svg>
                </div>
                <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">BirdWeather</h3>
            </div>
            <button
                role="switch"
                aria-checked={birdweatherEnabled}
                aria-label="Toggle BirdWeather integration"
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
                <label for="birdweather-token" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">Station Token</label>
                <input
                    id="birdweather-token"
                    type="password"
                    bind:value={birdweatherStationToken}
                    placeholder="Your BirdWeather token"
                    aria-label="BirdWeather station token"
                    class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm"
                />
                <p class="mt-2 text-[10px] text-slate-500 font-bold italic">Available in your station settings under "BirdWeather Token".</p>
            </div>
            <button
                onclick={handleTestBirdWeather}
                disabled={testingBirdWeather || !birdweatherStationToken}
                aria-label="Test BirdWeather connection"
                class="w-full px-4 py-3 text-xs font-black uppercase tracking-widest rounded-2xl bg-indigo-500 hover:bg-indigo-600 text-white transition-all shadow-lg shadow-indigo-500/20 disabled:opacity-50"
            >
                {testingBirdWeather ? 'Verifying...' : 'Test Connection'}
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
                <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">AI Insights</h3>
            </div>
            <button
                role="switch"
                aria-checked={llmEnabled}
                aria-label="Toggle AI insights"
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
                    <label for="llm-provider" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">Provider</label>
                    <select
                        id="llm-provider"
                        bind:value={llmProvider}
                        aria-label="LLM provider"
                        class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm"
                    >
                        <option value="gemini">Google Gemini</option>
                        <option value="openai">OpenAI</option>
                        <option value="claude">Anthropic Claude</option>
                    </select>
                </div>
                <div>
                    <label for="llm-model" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">Model</label>
                    <select
                        id="llm-model"
                        bind:value={llmModel}
                        aria-label="LLM model"
                        class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm"
                    >
                        {#each availableModels as model}
                            <option value={model.value}>{model.label}</option>
                        {/each}
                    </select>
                </div>
            </div>
            <div>
                <label for="llm-api-key" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">API Key</label>
                <input
                    id="llm-api-key"
                    type="password"
                    bind:value={llmApiKey}
                    aria-label="LLM API key"
                    class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm"
                />
            </div>
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
